"""Durable, optimistic-concurrency job models for document processing."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class JobConflictError(RuntimeError):
    """A persisted job changed after the caller read its revision."""


class ParseJobStatus(StrEnum):
    QUEUED = "queued"
    PREFLIGHT = "preflight"
    PARSING = "parsing"
    NORMALIZING = "normalizing"
    QUALITY_CHECKING = "quality_checking"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_REVIEW = "needs_review"

    @property
    def terminal(self) -> bool:
        return self in {
            ParseJobStatus.SUCCEEDED,
            ParseJobStatus.FAILED,
            ParseJobStatus.CANCELLED,
            ParseJobStatus.NEEDS_REVIEW,
        }


class ParseFailureKind(StrEnum):
    POLICY = "policy"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"
    TRANSIENT = "transient"
    PARSER = "parser"
    NORMALIZATION = "normalization"
    QUALITY = "quality"
    INTEGRITY = "integrity"
    CANCELLED = "cancelled"
    INTERNAL = "internal"


class ParseAttemptRecord(BaseModel):
    """One immutable execution observation, including failed fallback attempts."""

    attempt_id: str = Field(default_factory=lambda: uuid4().hex)
    parser_id: str
    status: str
    reason: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int = Field(default=0, ge=0)
    parser_version: str | None = None
    parameters_fingerprint: str | None = None
    failure_kind: ParseFailureKind | None = None
    retryable: bool | None = None
    metrics: dict[str, int | float] = Field(default_factory=dict)


class ParseJobEvent(BaseModel):
    """Append-only control-plane event; its contents must be safe for clients."""

    event_id: str = Field(default_factory=lambda: uuid4().hex)
    previous_status: ParseJobStatus | None = None
    status: ParseJobStatus
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    message: str
    data: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


_RETRY_FORBIDDEN_FAILURE_KINDS = frozenset(
    {
        ParseFailureKind.POLICY,
        ParseFailureKind.UNSUPPORTED,
        ParseFailureKind.INTEGRITY,
    }
)


_ALLOWED_TRANSITIONS: dict[ParseJobStatus, set[ParseJobStatus]] = {
    ParseJobStatus.QUEUED: {
        ParseJobStatus.PREFLIGHT,
        ParseJobStatus.CANCELLED,
        ParseJobStatus.FAILED,
    },
    ParseJobStatus.PREFLIGHT: {
        ParseJobStatus.PARSING,
        ParseJobStatus.CANCELLED,
        ParseJobStatus.FAILED,
    },
    ParseJobStatus.PARSING: {
        ParseJobStatus.NORMALIZING,
        ParseJobStatus.CANCELLED,
        ParseJobStatus.FAILED,
    },
    ParseJobStatus.NORMALIZING: {
        ParseJobStatus.QUALITY_CHECKING,
        ParseJobStatus.CANCELLED,
        ParseJobStatus.FAILED,
    },
    ParseJobStatus.QUALITY_CHECKING: {
        ParseJobStatus.SUCCEEDED,
        ParseJobStatus.NEEDS_REVIEW,
        ParseJobStatus.CANCELLED,
        ParseJobStatus.FAILED,
    },
}


class ParseJob(BaseModel):
    """Control-plane record; source bytes and artifacts remain outside the JSON record."""

    schema_name: str = "ParseJob"
    schema_version: str = "1.1"
    parse_id: str
    source_sha256: str
    source_filename: str
    source_file_type: str
    source_size_bytes: int = Field(ge=0)
    requested_parser_id: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    parent_parse_id: str | None = None
    status: ParseJobStatus = ParseJobStatus.QUEUED
    revision: int = Field(
        default=0,
        ge=0,
        description=(
            "Optimistic-concurrency control-record counter (CAS); not a business "
            "document revision."
        ),
    )
    attempts: list[ParseAttemptRecord] = Field(default_factory=list)
    events: list[ParseJobEvent] = Field(default_factory=list)
    document_id: UUID | None = None
    quality_run_id: str | None = None
    quality_state: str | None = None
    package_path: str | None = None
    error: str | None = None
    error_reference: str | None = None
    failure_kind: ParseFailureKind | None = None
    retryable: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_terminal_state(self) -> "ParseJob":
        if self.status in {ParseJobStatus.SUCCEEDED, ParseJobStatus.NEEDS_REVIEW}:
            if self.document_id is None or self.package_path is None:
                raise ValueError("completed document job must include document_id and package_path")
        if self.status == ParseJobStatus.FAILED and not self.error:
            raise ValueError("failed job must include a safe error message")
        if self.status.terminal and self.completed_at is None:
            raise ValueError("terminal job must include completed_at")
        return self

    def retry_rejection_reason(self) -> str | None:
        """Return a stable policy reason when this job cannot create a retry child."""

        if self.status != ParseJobStatus.FAILED:
            return "Only failed jobs can be retried."
        if self.failure_kind in _RETRY_FORBIDDEN_FAILURE_KINDS:
            return f"Jobs that failed due to {self.failure_kind.value} cannot be retried."
        if not self.retryable:
            return "This failed job is not retryable."
        return None

    def require_retryable(self) -> None:
        """Raise a safe validation error unless this terminal failure may be retried."""

        if reason := self.retry_rejection_reason():
            raise ValueError(reason)

    def transition(
        self,
        status: ParseJobStatus,
        *,
        message: str | None = None,
        **updates: Any,
    ) -> "ParseJob":
        """Return a validated next state and append a safe, durable event."""

        if self.status.terminal:
            if status != self.status:
                raise ValueError(
                    f"Cannot transition terminal job {self.parse_id} from {self.status}"
                )
            raise ValueError(f"Terminal job {self.parse_id} cannot receive a new transition")
        allowed = _ALLOWED_TRANSITIONS.get(self.status, set())
        if status not in allowed:
            raise ValueError(
                f"Illegal job transition for {self.parse_id}: {self.status} -> {status}"
            )
        now = datetime.now(UTC)
        event_data: dict[str, str | int | float | bool | None] = {
            "attempt_count": len(updates.get("attempts", self.attempts)),
            "failure_kind": (
                str(updates["failure_kind"])
                if updates.get("failure_kind") is not None
                else None
            ),
        }
        event = ParseJobEvent(
            previous_status=self.status,
            status=status,
            occurred_at=now,
            message=message or f"Job entered {status.value}.",
            data=event_data,
        )
        payload = {
            **self.model_dump(),
            "status": status,
            "updated_at": now,
            "events": [*self.events, event],
            **updates,
        }
        if status.terminal and payload.get("completed_at") is None:
            payload["completed_at"] = now
        return ParseJob.model_validate(payload)
