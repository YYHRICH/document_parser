"""Durable parse-job orchestration with safe audit and quality-state mapping."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import UTC, datetime
from typing import Any, Iterable

from ..core import validate_parsed_document_integrity
from ..core.contracts import FallbackAttempt, QualityState
from .models import (
    JobConflictError,
    ParseAttemptRecord,
    ParseFailureKind,
    ParseJob,
    ParseJobStatus,
)
from .ports import JobRepository, ParsingGateway, QualityRunner


class ParseJobOrchestrator:
    """Compose gateway, normalizer validation, quality, and durable publication."""

    def __init__(
        self,
        *,
        gateway: ParsingGateway,
        repository: JobRepository,
        quality_runner: QualityRunner,
    ) -> None:
        self._gateway = gateway
        self._repository = repository
        self._quality_runner = quality_runner

    def run(self, parse_id: str) -> ParseJob:
        """Claim a queued job once, execute it, and leave an append-only audit trail."""

        job = self._repository.load_job(parse_id)
        if job.status.terminal:
            return job
        # A competing worker has already claimed a non-queued record.  It must
        # finish it; blindly replaying it would duplicate a cloud/local attempt.
        if job.status != ParseJobStatus.QUEUED:
            return job

        parse_started_at: datetime | None = None
        selected_parser_id: str | None = job.requested_parser_id
        try:
            job = self._save_transition(
                job,
                ParseJobStatus.PREFLIGHT,
                message="Request and durable source passed preflight.",
            )
            request = self._repository.load_request(parse_id)
            selected_parser_id = request.parser_id
            job = self._save_transition(
                job,
                ParseJobStatus.PARSING,
                message="Parser execution started.",
            )
            parse_started_at = datetime.now(UTC)
            started = time.perf_counter()
            result = self._gateway.parse_for_package(request)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            parse_completed_at = datetime.now(UTC)
            document = result.document
            attempts = _attempts_from_fallbacks(document.provenance.fallback_history)
            attempts.append(
                ParseAttemptRecord(
                    parser_id=document.provenance.parser_id,
                    parser_version=document.provenance.version,
                    status="succeeded",
                    reason="Parser produced a normalized document.",
                    started_at=parse_started_at,
                    completed_at=parse_completed_at,
                    duration_ms=max(elapsed_ms, document.provenance.parse_duration_ms),
                    parameters_fingerprint=_options_fingerprint(
                        document.provenance.parameters
                    ),
                    metrics={
                        "wall_duration_ms": elapsed_ms,
                        "reported_parse_duration_ms": document.provenance.parse_duration_ms,
                    },
                )
            )
            job = self._save_transition(
                job,
                ParseJobStatus.NORMALIZING,
                attempts=attempts,
                message="Normalized document contract is being validated.",
            )
            # Gateway adapters may normalize internally, but the orchestrator owns
            # the durable boundary validation before quality and publication.
            validate_parsed_document_integrity(document)
            job = self._save_transition(
                job,
                ParseJobStatus.QUALITY_CHECKING,
                message="Deterministic quality checks started.",
            )
            quality_package = self._quality_runner(document)
            terminal_status = _quality_terminal_status(quality_package)
            package_path = self._repository.commit_completed_job(
                job=job,
                document=document,
                quality_package=quality_package,
                native_files=result.native_files,
            )
            terminal_message = "Document package published with its quality report."
            return self._save_transition(
                job,
                terminal_status,
                document_id=document.document_id,
                quality_run_id=_quality_run_id(quality_package),
                quality_state=_quality_state_value(quality_package),
                package_path=package_path,
                error=None,
                error_reference=None,
                failure_kind=None,
                retryable=False,
                message=terminal_message,
            )
        except JobConflictError:
            # The winning writer may be a cancellation or a competing worker.
            return self._repository.load_job(parse_id)
        except Exception as error:
            return self._record_failure(
                parse_id=parse_id,
                error=error,
                parse_started_at=parse_started_at,
                selected_parser_id=selected_parser_id,
            )

    def _save_transition(
        self,
        job: ParseJob,
        status: ParseJobStatus,
        *,
        message: str,
        **updates: Any,
    ) -> ParseJob:
        return self._repository.save_job(job.transition(status, message=message, **updates))

    def _record_failure(
        self,
        *,
        parse_id: str,
        error: Exception,
        parse_started_at: datetime | None,
        selected_parser_id: str | None,
    ) -> ParseJob:
        try:
            current = self._repository.load_job(parse_id)
            if current.status.terminal:
                return current
            failure_kind, retryable = _classify_failure(error)
            attempts = _merge_attempts(
                current.attempts,
                _attempts_from_error(error),
            )
            if not attempts and parse_started_at is not None:
                completed_at = datetime.now(UTC)
                duration_ms = max(
                    0,
                    int((completed_at - parse_started_at).total_seconds() * 1000),
                )
                attempts = [
                    ParseAttemptRecord(
                        parser_id=selected_parser_id or "unknown",
                        status="failed",
                        reason=_safe_attempt_reason(error),
                        started_at=parse_started_at,
                        completed_at=completed_at,
                        duration_ms=duration_ms,
                        failure_kind=failure_kind,
                        retryable=retryable,
                        metrics={"wall_duration_ms": duration_ms},
                    )
                ]
            return self._save_transition(
                current,
                ParseJobStatus.FAILED,
                attempts=attempts,
                error=_safe_failure_message(failure_kind),
                error_reference=_error_reference(error),
                failure_kind=failure_kind,
                retryable=retryable,
                message="Job failed; inspect the safe failure kind and attempt audit.",
            )
        except JobConflictError:
            return self._repository.load_job(parse_id)


def _attempts_from_fallbacks(
    history: Iterable[FallbackAttempt],
) -> list[ParseAttemptRecord]:
    attempts: list[ParseAttemptRecord] = []
    for item in history:
        failure_kind = _failure_kind_from_value(item.failure_kind)
        attempts.append(
            ParseAttemptRecord(
                attempt_id=item.attempt_id,
                parser_id=item.parser_id,
                status=item.status,
                reason=_safe_text(item.reason, limit=500),
                started_at=item.started_at,
                completed_at=item.completed_at,
                duration_ms=item.duration_ms,
                parser_version=item.parser_version,
                parameters_fingerprint=item.parameters_fingerprint,
                failure_kind=failure_kind,
                retryable=item.retryable,
                metrics=dict(item.metrics),
            )
        )
    return attempts


def _attempts_from_error(error: Exception) -> list[ParseAttemptRecord]:
    history = getattr(error, "attempts", ())
    if not isinstance(history, Iterable):
        return []
    fallback_items = [item for item in history if isinstance(item, FallbackAttempt)]
    return _attempts_from_fallbacks(fallback_items)


def _merge_attempts(
    existing: list[ParseAttemptRecord],
    incoming: list[ParseAttemptRecord],
) -> list[ParseAttemptRecord]:
    merged = list(existing)
    known = {item.attempt_id for item in merged}
    for item in incoming:
        if item.attempt_id not in known:
            merged.append(item)
            known.add(item.attempt_id)
    return merged


def _options_fingerprint(options: dict[str, Any]) -> str:
    encoded = json.dumps(
        options,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _quality_run_id(package: Any) -> str:
    payload = getattr(package, "package_manifest", None)
    if payload is None:
        return hashlib.sha256(repr(package).encode("utf-8")).hexdigest()[:32]
    encoded = json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:32]


def _quality_state_value(package: Any) -> str | None:
    state = getattr(getattr(package, "quality_report", None), "state", None)
    return getattr(state, "value", str(state)) if state is not None else None


def _quality_terminal_status(package: Any) -> ParseJobStatus:
    """Complete once a verified quality package has been published.

    ``QualityReport.state`` remains the authoritative risk signal for downstream
    consumers. It must not turn a published result into a stuck workflow: the
    report, issues, repairs, and any reparse recommendation travel with the
    deliverable package.
    """

    state = getattr(getattr(package, "quality_report", None), "state", None)
    if state in set(QualityState):
        return ParseJobStatus.SUCCEEDED
    return ParseJobStatus.NEEDS_REVIEW


def _failure_kind_from_value(value: str | None) -> ParseFailureKind:
    if value is not None:
        try:
            return ParseFailureKind(value)
        except ValueError:
            pass
    return ParseFailureKind.PARSER


def _classify_failure(error: Exception) -> tuple[ParseFailureKind, bool]:
    explicit_kind = getattr(error, "failure_kind", None)
    if explicit_kind is not None:
        kind = _failure_kind_from_value(str(explicit_kind))
        return kind, bool(getattr(error, "retryable", kind == ParseFailureKind.TRANSIENT))
    causes = getattr(error, "causes", ())
    details = " ".join(
        [f"{type(error).__name__} {error}", *[f"{type(item).__name__} {item}" for item in causes]]
    ).lower()
    if any(token in details for token in ("timeout", "temporar", "connection", "rate limit")):
        return ParseFailureKind.TRANSIENT, True
    if any(token in details for token in ("forbid", "policy", "untrusted", "not allowed")):
        return ParseFailureKind.POLICY, False
    if any(token in details for token in ("unsupported", "not support", "不支持")):
        return ParseFailureKind.UNSUPPORTED, False
    if any(token in details for token in ("unavailable", "not installed", "不可用")):
        return ParseFailureKind.UNAVAILABLE, False
    if "integrity" in details:
        return ParseFailureKind.INTEGRITY, False
    if any(token in details for token in ("normaliz", "schema", "contract")):
        return ParseFailureKind.NORMALIZATION, False
    if "quality" in details:
        return ParseFailureKind.QUALITY, False
    return ParseFailureKind.PARSER, False


def _safe_failure_message(kind: ParseFailureKind) -> str:
    messages = {
        ParseFailureKind.POLICY: "The request violates the server execution policy.",
        ParseFailureKind.UNSUPPORTED: "The selected parser does not support this document.",
        ParseFailureKind.UNAVAILABLE: "The selected parser is unavailable in this environment.",
        ParseFailureKind.TRANSIENT: "The parser service is temporarily unavailable; retry is safe.",
        ParseFailureKind.NORMALIZATION: "The parser output could not be validated as a document package.",
        ParseFailureKind.QUALITY: "Quality processing did not complete for the parsed document.",
        ParseFailureKind.INTEGRITY: "A durable source or artifact integrity check failed.",
        ParseFailureKind.CANCELLED: "The parse job was cancelled.",
        ParseFailureKind.INTERNAL: "The parse job encountered an internal platform error.",
        ParseFailureKind.PARSER: "The parser could not process this document.",
    }
    return messages[kind]


def _safe_attempt_reason(error: Exception) -> str:
    return _safe_text(f"{type(error).__name__}: {error}", limit=500)


def _safe_text(value: str, *, limit: int) -> str:
    compact = " ".join(value.split())
    compact = re.sub(
        r"(?i)(bearer|token|authorization)\s*[:=]\s*[^\s,;]+",
        r"\1=[redacted]",
        compact,
    )
    return compact[:limit] or "Parser attempt failed."


def _error_reference(error: Exception) -> str:
    payload = f"{type(error).__name__}:{error}".encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()[:20]
