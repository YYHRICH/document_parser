"""Composition adapter from durable parse jobs to routing recommendations.

The functions here adapt durable ``ParseJob`` metadata to the public routing
recommendation contracts.  They deliberately do not load a quality package,
read storage, invoke HTTP/FastAPI, or treat request options as execution
authority.  A caller must inject the already-resolved effective policy.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import PurePosixPath

from ..core.contracts import ParserCapability
from ..routing.recommendations import (
    ReparseContext,
    ReparseRecommendationPolicy,
    ReparseRecommendations,
    ReparseSignal,
    ReparseSignalSource,
    recommend_reparse,
)
from ..orchestration.models import ParseFailureKind, ParseJob, ParseJobStatus


_REPARSE_REQUIRED_STATE = "reparse_required"
_REPARSE_FAILURE_KINDS = frozenset(
    {
        ParseFailureKind.TRANSIENT,
        ParseFailureKind.PARSER,
        ParseFailureKind.NORMALIZATION,
        ParseFailureKind.UNAVAILABLE,
        ParseFailureKind.UNSUPPORTED,
    }
)

_FAILURE_MESSAGES: dict[ParseFailureKind, str] = {
    ParseFailureKind.TRANSIENT: (
        "The prior parser attempt failed temporarily; a retry or eligible alternative may help."
    ),
    ParseFailureKind.PARSER: "The prior parser could not process the document.",
    ParseFailureKind.NORMALIZATION: "The prior parser output could not be normalized.",
    ParseFailureKind.UNAVAILABLE: "The prior parser is unavailable in this environment.",
    ParseFailureKind.UNSUPPORTED: "The prior parser did not support this document.",
}


def reparse_context_for_job(job: ParseJob) -> ReparseContext:
    """Project only source and parser-history facts required for recommendation.

    The current parser is the most recent actual attempt when one exists; a
    requested parser is used only as a fallback for a job that has not started.
    ``attempted_parser_ids`` contains actual attempt records, not parser options.
    """

    attempted_parser_ids = _attempted_parser_ids(job)
    current_parser_id = attempted_parser_ids[-1] if attempted_parser_ids else _safe_parser_id(
        job.requested_parser_id
    )
    return ReparseContext(
        parent_parse_id=job.parse_id,
        source_extension=_source_extension(job.source_filename),
        current_parser_id=current_parser_id,
        attempted_parser_ids=attempted_parser_ids,
    )


def reparse_signals_for_job(job: ParseJob) -> tuple[ReparseSignal, ...]:
    """Translate only actionable, safe job conclusions into domain signals.

    Raw ``job.error`` and attempt reasons are deliberately excluded.  Their
    content may be unsuitable for a recommendation API; callers receive stable
    failure codes and curated messages instead.
    """

    signals: list[ReparseSignal] = []
    if _normalized_quality_state(job.quality_state) == _REPARSE_REQUIRED_STATE:
        signals.append(
            ReparseSignal(
                source=ReparseSignalSource.QUALITY,
                code="reparse-required",
                message="Quality checks recommend a new parse before downstream use.",
            )
        )

    failure_kind = job.failure_kind
    if job.status == ParseJobStatus.FAILED and failure_kind in _REPARSE_FAILURE_KINDS:
        signals.append(
            ReparseSignal(
                source=ReparseSignalSource.FAILURE,
                code=f"failure-{failure_kind.value}",
                message=_FAILURE_MESSAGES[failure_kind],
                retryable=job.retryable,
            )
        )
    return tuple(signals)


def recommend_reparse_for_job(
    job: ParseJob,
    capabilities: Iterable[ParserCapability],
    *,
    policy: ReparseRecommendationPolicy | None = None,
) -> ReparseRecommendations | None:
    """Return pure reparse recommendations for a job, or ``None`` without a signal.

    ``policy`` is an explicit, already-resolved policy boundary.  Its default is
    cloud-deny.  This function never reads ``job.options`` (including an
    ``allow_cloud`` value), so request metadata cannot escalate execution policy.
    """

    signals = reparse_signals_for_job(job)
    if not signals:
        return None
    effective_policy = policy or ReparseRecommendationPolicy()
    return recommend_reparse(
        reparse_context_for_job(job),
        capabilities,
        signals,
        effective_policy,
    )


def _attempted_parser_ids(job: ParseJob) -> tuple[str, ...]:
    parser_ids: list[str] = []
    seen: set[str] = set()
    for attempt in job.attempts:
        parser_id = _safe_parser_id(attempt.parser_id)
        if parser_id is not None and parser_id not in seen:
            parser_ids.append(parser_id)
            seen.add(parser_id)
    return tuple(parser_ids)


def _safe_parser_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _source_extension(filename: str) -> str:
    """Extract a cross-platform filename suffix without reading a filesystem path."""

    normalized_filename = filename.replace("\\", "/")
    suffix = PurePosixPath(normalized_filename).suffix.strip().lower()
    return suffix or ".bin"


def _normalized_quality_state(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


__all__ = [
    "recommend_reparse_for_job",
    "reparse_context_for_job",
    "reparse_signals_for_job",
]
