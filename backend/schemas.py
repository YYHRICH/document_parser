"""Backend API request and response models."""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
import re
from typing import Literal

from pydantic import BaseModel, Field

from ..core.contracts import ParsedDocument, ParserCapability, QualityPackage
from ..orchestration.models import (
    ParseAttemptRecord,
    ParseFailureKind,
    ParseJob,
    ParseJobEvent,
    ParseJobStatus,
)


_SAFE_SOURCE_EXTENSION = re.compile(r"^\.[A-Za-z0-9]{1,16}$")
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_PUBLIC_ROUTE_PROFILES = frozenset({"local_first", "quality_first"})
_PUBLIC_QUALITY_STATES = frozenset(
    {
        "pass",
        "pass_with_warnings",
        "manual_review_required",
        "reparse_required",
        "rejected",
    }
)
_PUBLIC_ATTEMPT_STATUSES = frozenset(
    {"queued", "running", "parsing", "succeeded", "failed", "cancelled", "skipped"}
)
_PUBLIC_ERROR_REFERENCES = frozenset({"worker-interrupted", "client-cancelled"})
_PUBLIC_FAILURE_SUMMARIES: dict[ParseFailureKind, str] = {
    ParseFailureKind.POLICY: "The request could not be processed under the server policy.",
    ParseFailureKind.UNSUPPORTED: "The selected parser does not support this document.",
    ParseFailureKind.UNAVAILABLE: "The selected parser is unavailable in this environment.",
    ParseFailureKind.TRANSIENT: "The parser service is temporarily unavailable; retry may be safe.",
    ParseFailureKind.PARSER: "The parser could not process this document.",
    ParseFailureKind.NORMALIZATION: "The parser output could not be normalized safely.",
    ParseFailureKind.QUALITY: "Quality processing did not complete for this document.",
    ParseFailureKind.INTEGRITY: "A source or artifact integrity check failed.",
    ParseFailureKind.CANCELLED: "The parse job was cancelled.",
    ParseFailureKind.INTERNAL: "The parse job encountered an internal platform failure.",
}


class PublicParseOptions(BaseModel):
    """Only request preferences that are safe for a browser to inherit on reparse."""

    route_profile: Literal["local_first", "quality_first"] | None = None
    allow_cloud: bool | None = None


class PublicParseAttempt(BaseModel):
    """Content-free attempt timeline projection."""

    status: str
    duration_ms: int = Field(ge=0)
    failure_kind: str | None = None
    retryable: bool | None = None
    occurred_at: datetime | None = None


class PublicParseJobEvent(BaseModel):
    """Content-free durable status transition projection."""

    previous_status: str | None = None
    status: str
    occurred_at: datetime


class PublicParseJob(BaseModel):
    """Explicit browser-safe task projection; never inherit the internal ParseJob."""

    parse_id: str
    parent_parse_id: str | None = None
    source_extension: str
    requested_parser_id: str | None = None
    options: PublicParseOptions = Field(default_factory=PublicParseOptions)
    status: str
    attempts: list[PublicParseAttempt] = Field(default_factory=list)
    quality_state: str | None = None
    failure_kind: str | None = None
    retryable: bool
    error: str | None = None
    error_reference: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class ParseJobResponse(BaseModel):
    parse_id: str
    document: ParsedDocument
    native_artifact_count: int = Field(ge=0)


class ParseJobStatusResponse(BaseModel):
    """Asynchronous task control-plane response with only public task metadata."""

    parse_id: str
    status: str
    job: PublicParseJob
    status_url: str


class ParseJobCancelResponse(BaseModel):
    parse_id: str
    status: str
    job: PublicParseJob


class ParseJobEventsResponse(BaseModel):
    """Safe task timeline: no raw event messages, reasons, parameters, or metrics."""

    parse_id: str
    status: str
    attempts: list[PublicParseAttempt] = Field(default_factory=list)
    events: list[PublicParseJobEvent] = Field(default_factory=list)
    error: str | None = None
    error_reference: str | None = None
    failure_kind: str | None = None
    retryable: bool
    updated_at: datetime


def public_parse_job(job: ParseJob) -> PublicParseJob:
    """Return a deliberate allowlist rather than serializing a durable control record."""

    return PublicParseJob(
        parse_id=job.parse_id,
        parent_parse_id=_safe_optional_identifier(job.parent_parse_id),
        source_extension=_public_source_extension(job.source_filename),
        requested_parser_id=_safe_optional_identifier(job.requested_parser_id),
        options=_public_options(job.options),
        status=job.status.value,
        attempts=[public_parse_attempt(item) for item in job.attempts],
        quality_state=_public_quality_state(job.quality_state),
        failure_kind=_public_failure_kind(job.failure_kind),
        retryable=bool(job.retryable),
        error=_public_error_summary(job),
        error_reference=_public_error_reference(job),
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
    )


def public_parse_job_events(job: ParseJob) -> ParseJobEventsResponse:
    """Project the event endpoint without raw diagnostic strings or maps."""

    return ParseJobEventsResponse(
        parse_id=job.parse_id,
        status=job.status.value,
        attempts=[public_parse_attempt(item) for item in job.attempts],
        events=[public_parse_event(item) for item in job.events],
        error=_public_error_summary(job),
        error_reference=_public_error_reference(job),
        failure_kind=_public_failure_kind(job.failure_kind),
        retryable=bool(job.retryable),
        updated_at=job.updated_at,
    )


def public_parse_attempt(attempt: ParseAttemptRecord) -> PublicParseAttempt:
    """Keep only the timeline fields a client needs to understand task progress."""

    normalized_status = attempt.status.strip().lower()
    return PublicParseAttempt(
        status=(normalized_status if normalized_status in _PUBLIC_ATTEMPT_STATUSES else "unknown"),
        duration_ms=attempt.duration_ms,
        failure_kind=_public_failure_kind(attempt.failure_kind),
        retryable=attempt.retryable if isinstance(attempt.retryable, bool) else None,
        occurred_at=attempt.completed_at or attempt.started_at,
    )


def public_parse_event(event: ParseJobEvent) -> PublicParseJobEvent:
    return PublicParseJobEvent(
        previous_status=event.previous_status.value if event.previous_status is not None else None,
        status=event.status.value,
        occurred_at=event.occurred_at,
    )


def _public_options(options: dict[str, object]) -> PublicParseOptions:
    route_profile = options.get("route_profile")
    allow_cloud = options.get("allow_cloud")
    return PublicParseOptions(
        route_profile=(
            route_profile
            if isinstance(route_profile, str) and route_profile in _PUBLIC_ROUTE_PROFILES
            else None
        ),
        allow_cloud=allow_cloud if isinstance(allow_cloud, bool) else None,
    )


def _public_source_extension(filename: str) -> str:
    normalized = filename.replace("\\", "/")
    suffix = PurePosixPath(normalized).suffix.strip().lower()
    return suffix if _SAFE_SOURCE_EXTENSION.fullmatch(suffix) else ".bin"


def _safe_optional_identifier(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if _SAFE_IDENTIFIER.fullmatch(normalized) else None


def _public_quality_state(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized in _PUBLIC_QUALITY_STATES else None


def _public_failure_kind(value: ParseFailureKind | None) -> str | None:
    return value.value if value is not None else None


def _public_error_summary(job: ParseJob) -> str | None:
    if job.failure_kind is not None:
        return _PUBLIC_FAILURE_SUMMARIES[job.failure_kind]
    if job.status == ParseJobStatus.CANCELLED:
        return _PUBLIC_FAILURE_SUMMARIES[ParseFailureKind.CANCELLED]
    if job.status == ParseJobStatus.FAILED:
        return "The parse job did not complete."
    return None


def _public_error_reference(job: ParseJob) -> str | None:
    if job.error_reference in _PUBLIC_ERROR_REFERENCES:
        return job.error_reference
    if job.failure_kind is not None:
        return f"failure-{job.failure_kind.value}"
    return None


class ParseRecordResponse(BaseModel):
    parse_id: str
    document: ParsedDocument


class QualityPackageResponse(BaseModel):
    parse_id: str
    quality_package: QualityPackage


class ReparseRequest(BaseModel):
    parser_id: str | None = None
    options: dict[str, object] = Field(default_factory=dict)


class ParserSelectionPolicy(BaseModel):
    """Browser-safe server policy that constrains manual parser choices."""

    cloud_parsers_enabled: bool = False


class ParserListResponse(BaseModel):
    parsers: list[ParserCapability]
    selection_policy: ParserSelectionPolicy = Field(default_factory=ParserSelectionPolicy)


class SourceIdentitySummary(BaseModel):
    """Non-secret immutable-source metadata; the source digest is never exposed."""

    file_type: str
    size_bytes: int = Field(ge=0)


class JobOptionsSummary(BaseModel):
    """Shape-only option summary; values and secret-like keys are omitted."""

    key_count: int = Field(ge=0)
    keys: list[str] = Field(default_factory=list)
    keys_truncated: bool = False
    shape_fingerprint: str


class JobRequestSummary(BaseModel):
    requested_parser_id: str | None = None
    options: JobOptionsSummary


class JobAttemptSummary(BaseModel):
    count: int = Field(ge=0)
    successful_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    other_count: int = Field(ge=0)
    total_duration_ms: int = Field(ge=0)
    parser_ids: list[str] = Field(default_factory=list)
    status_counts: dict[str, int] = Field(default_factory=dict)


class JobDurationSummary(BaseModel):
    elapsed_ms: int = Field(ge=0)
    attempt_total_ms: int = Field(ge=0)


class StructuralCountsSummary(BaseModel):
    """Counts only; no Markdown, block text, filenames, or artifact paths."""

    block_count: int = Field(ge=0)
    block_kind_counts: dict[str, int] = Field(default_factory=dict)
    table_count: int = Field(ge=0)
    asset_count: int = Field(ge=0)
    ocr_span_count: int = Field(ge=0)
    native_artifact_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)


class JobMetadataSummary(BaseModel):
    """Safe, read-only projection of a task control record."""

    parse_id: str
    parent_parse_id: str | None = None
    created_at: str
    completed_at: str | None = None
    status: str
    cas_revision: int = Field(
        ge=0,
        description=(
            "Optimistic-concurrency control-record counter (CAS), not a business "
            "document revision."
        ),
    )
    request: JobRequestSummary
    attempts: JobAttemptSummary
    quality_state: str | None = None
    failure_kind: str | None = None
    retryable: bool
    duration: JobDurationSummary
    structural_counts_available: bool
    structural_counts: StructuralCountsSummary | None = None


class LineageJobMetadataSummary(JobMetadataSummary):
    generation: int = Field(ge=0)


class ParseJobLineageResponse(BaseModel):
    parse_id: str
    root_parse_id: str | None = Field(
        default=None,
        description="Resolved root only when lineage_complete is true.",
    )
    ancestor_count: int = Field(ge=0)
    lineage_complete: bool
    lineage_integrity: Literal[
        "verified",
        "parent_not_found",
        "cycle_detected",
        "depth_limit_reached",
        "source_identity_mismatch",
    ]
    source: SourceIdentitySummary
    items: list[LineageJobMetadataSummary]


class StructuralCountsDelta(BaseModel):
    """Right-minus-left structural count deltas for a same-source comparison."""

    block_count: int
    block_kind_counts: dict[str, int] = Field(default_factory=dict)
    table_count: int
    asset_count: int
    ocr_span_count: int
    native_artifact_count: int
    warning_count: int


class JobComparisonDifferences(BaseModel):
    requested_parser_changed: bool
    options_changed: bool
    status_changed: bool
    quality_state_changed: bool
    attempt_count_delta: int
    elapsed_ms_delta: int | None = None
    structural_counts_delta: StructuralCountsDelta | None = None


class ParseJobComparisonResponse(BaseModel):
    """Read-only, content-free comparison between two jobs with one source identity."""

    same_source: bool
    source: SourceIdentitySummary
    left: JobMetadataSummary
    right: JobMetadataSummary
    differences: JobComparisonDifferences


class ReparseRecommendationSignalResponse(BaseModel):
    """Safe signal code only; the domain message is deliberately omitted."""

    source: Literal["quality", "failure"]
    code: str
    retryable: bool


class ReparseRecommendationCandidateResponse(BaseModel):
    """Candidate execution facts without options, diagnostic text, or paths."""

    parser_id: str
    executable: bool
    replaces_current_parser: bool
    requires_cloud: bool


class AutomaticReparseResponse(BaseModel):
    parser_id: str
    requires_cloud: bool


class ReparseRecommendationsResponse(BaseModel):
    """Content-free reparse advice; option values are never part of this API."""

    signals: list[ReparseRecommendationSignalResponse] = Field(default_factory=list)
    candidates: list[ReparseRecommendationCandidateResponse] = Field(default_factory=list)
    automatic: AutomaticReparseResponse | None = None


class ParseJobReparseRecommendationsResponse(BaseModel):
    """A null recommendation explicitly means the job has no actionable signal."""

    parse_id: str
    recommendations: ReparseRecommendationsResponse | None = None
