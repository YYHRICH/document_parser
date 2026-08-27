"""Pure, read-only projections for task lineage and same-source comparison.

This module deliberately knows nothing about filesystem layout, delivery packages,
queues, routing, or quality execution.  Its callers provide persisted ``ParseJob``
records and, optionally, already-safe structural counts.  In particular,
``ParseJob.revision`` is a control-record compare-and-swap (CAS) counter.  It is
never presented as a business document revision.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from hmac import compare_digest
import json
import re
from typing import Any

from ..core.contracts import ParsedDocument
from ..orchestration.models import ParseJob


_DEFAULT_MAX_LINEAGE_DEPTH = 64
_MAX_EXPOSED_OPTION_KEYS = 32
_MAX_OPTION_SHAPE_ENTRIES = 64
_MAX_OPTION_SHAPE_ITEMS = 16
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SAFE_MEDIA_TYPE = re.compile(
    r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$"
)
_SENSITIVE_OPTION_KEY_PARTS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "bearer",
        "cookie",
        "credential",
        "credentials",
        "password",
        "private",
        "secret",
        "token",
    }
)


class DifferentSourceIdentityError(ValueError):
    """Raised when a comparison would cross immutable input identities."""


@dataclass(frozen=True)
class LineageResolution:
    """A bounded root-to-target chain resolved through an injected job lookup."""

    jobs: tuple[ParseJob, ...]
    complete: bool
    integrity: str


def same_source_identity(left: ParseJob, right: ParseJob) -> bool:
    """Return whether two jobs describe exactly the same immutable source.

    The digest itself is intentionally never included in public projections.  File
    type and byte size are checked alongside it so a corrupt control record cannot
    accidentally make distinct inputs comparable.
    """

    return (
        compare_digest(left.source_sha256.lower(), right.source_sha256.lower())
        and left.source_size_bytes == right.source_size_bytes
        and left.source_file_type.strip().lower() == right.source_file_type.strip().lower()
    )


def source_identity_matches(left: ParseJob, right: ParseJob) -> bool:
    """Compatibility-friendly alias for :func:`same_source_identity`."""

    return same_source_identity(left, right)


def resolve_lineage(
    target: ParseJob,
    load_job: Callable[[str], ParseJob],
    *,
    max_depth: int = _DEFAULT_MAX_LINEAGE_DEPTH,
) -> LineageResolution:
    """Resolve only one target's parent chain through a narrow injected port.

    The helper does not enumerate a repository.  That keeps the read path bounded,
    preserves future tenant scoping at the repository edge, and prevents unrelated
    packages from being read merely to render one job's lineage.
    """

    if max_depth < 1:
        raise ValueError("max_depth must be positive.")

    reverse_chain = [target]
    seen = {target.parse_id}
    current = target
    while current.parent_parse_id is not None:
        if len(reverse_chain) >= max_depth:
            return _resolution(
                reverse_chain,
                complete=False,
                integrity="depth_limit_reached",
            )
        parent_parse_id = current.parent_parse_id
        if parent_parse_id in seen:
            return _resolution(
                reverse_chain,
                complete=False,
                integrity="cycle_detected",
            )
        try:
            parent = load_job(parent_parse_id)
        except (FileNotFoundError, ValueError):
            return _resolution(
                reverse_chain,
                complete=False,
                integrity="parent_not_found",
            )
        if parent.parse_id != parent_parse_id:
            return _resolution(
                reverse_chain,
                complete=False,
                integrity="parent_not_found",
            )
        if not same_source_identity(target, parent):
            return _resolution(
                reverse_chain,
                complete=False,
                integrity="source_identity_mismatch",
            )
        reverse_chain.append(parent)
        seen.add(parent.parse_id)
        current = parent

    return _resolution(reverse_chain, complete=True, integrity="verified")


def _resolution(
    reverse_chain: list[ParseJob],
    *,
    complete: bool,
    integrity: str,
) -> LineageResolution:
    return LineageResolution(
        jobs=tuple(reversed(reverse_chain)),
        complete=complete,
        integrity=integrity,
    )


def summarize_document_structure(document: ParsedDocument) -> dict[str, object]:
    """Create content-free structural counts from an already-loaded document."""

    block_kind_counts = Counter(block.kind.value for block in document.blocks)
    return {
        "block_count": len(document.blocks),
        "block_kind_counts": dict(sorted(block_kind_counts.items())),
        "table_count": len(document.tables),
        "asset_count": len(document.assets),
        "ocr_span_count": len(document.ocr_spans),
        "native_artifact_count": len(document.native_artifacts),
        "warning_count": len(document.warnings),
    }


def summarize_job(
    job: ParseJob,
    *,
    structural_counts: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return one safe control-plane projection with no paths or source content."""

    counts = _normalise_structural_counts(structural_counts)
    return {
        "parse_id": job.parse_id,
        "parent_parse_id": job.parent_parse_id,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "status": job.status.value,
        # This is specifically named to prevent clients treating it as a user-facing
        # document revision.  It only guards concurrent control-record writes.
        "cas_revision": job.revision,
        "request": {
            "requested_parser_id": _safe_identifier(job.requested_parser_id),
            "options": summarize_options(job.options),
        },
        "attempts": _summarize_attempts(job),
        "quality_state": _safe_identifier(job.quality_state),
        "failure_kind": job.failure_kind.value if job.failure_kind is not None else None,
        "retryable": job.retryable,
        "duration": {
            "elapsed_ms": _elapsed_ms(job.created_at, job.completed_at or job.updated_at),
            "attempt_total_ms": sum(item.duration_ms for item in job.attempts),
        },
        "structural_counts_available": counts is not None,
        "structural_counts": counts,
    }


def summarize_options(options: Mapping[str, Any]) -> dict[str, object]:
    """Summarize request options without exposing option values or secret-like keys."""

    raw_keys = [str(key) for key in options]
    displayed_keys = sorted(_safe_option_key(key) for key in raw_keys)
    return {
        "key_count": len(raw_keys),
        "keys": displayed_keys[:_MAX_EXPOSED_OPTION_KEYS],
        "keys_truncated": len(displayed_keys) > _MAX_EXPOSED_OPTION_KEYS,
        # This fingerprint represents shape (keys and value types), never values.
        "shape_fingerprint": _options_shape_fingerprint(options),
    }


def build_lineage_snapshot(
    target: ParseJob,
    jobs: Iterable[ParseJob],
    *,
    structural_counts_by_parse_id: Mapping[str, Mapping[str, object]] | None = None,
    lineage_complete: bool | None = None,
    lineage_integrity: str | None = None,
) -> dict[str, object]:
    """Build root-to-target ancestry without reading storage or mutating any job.

    A missing parent, cycle, or source-identity mismatch is reported in safe
    metadata.  The invalid parent is not included in the returned chain.
    """

    by_parse_id = {job.parse_id: job for job in jobs}
    by_parse_id[target.parse_id] = target
    counts_by_parse_id = structural_counts_by_parse_id or {}

    chain = [target]
    seen = {target.parse_id}
    current = target
    integrity = "verified"
    complete = True
    while current.parent_parse_id is not None:
        parent = by_parse_id.get(current.parent_parse_id)
        if parent is None:
            integrity = "parent_not_found"
            complete = False
            break
        if parent.parse_id in seen:
            integrity = "cycle_detected"
            complete = False
            break
        if not same_source_identity(target, parent):
            integrity = "source_identity_mismatch"
            complete = False
            break
        chain.append(parent)
        seen.add(parent.parse_id)
        current = parent

    ordered = list(reversed(chain))
    entries: list[dict[str, object]] = []
    for generation, job in enumerate(ordered):
        item = summarize_job(
            job,
            structural_counts=counts_by_parse_id.get(job.parse_id),
        )
        item["generation"] = generation
        entries.append(item)

    effective_complete = complete if lineage_complete is None else lineage_complete
    effective_integrity = integrity if lineage_integrity is None else lineage_integrity
    return {
        "parse_id": target.parse_id,
        # An incomplete walk must not pretend its oldest readable item is the root.
        "root_parse_id": ordered[0].parse_id if effective_complete else None,
        "ancestor_count": len(ordered) - 1,
        "lineage_complete": effective_complete,
        "lineage_integrity": effective_integrity,
        "source": _public_source_summary(target),
        "items": entries,
    }


def build_same_source_comparison(
    left: ParseJob,
    right: ParseJob,
    *,
    structural_counts_by_parse_id: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Build a content-free comparison after enforcing immutable-source equality."""

    if not same_source_identity(left, right):
        raise DifferentSourceIdentityError(
            "Jobs do not belong to the same immutable source identity."
        )

    counts_by_parse_id = structural_counts_by_parse_id or {}
    left_counts = _normalise_structural_counts(counts_by_parse_id.get(left.parse_id))
    right_counts = _normalise_structural_counts(counts_by_parse_id.get(right.parse_id))
    left_summary = summarize_job(left, structural_counts=left_counts)
    right_summary = summarize_job(right, structural_counts=right_counts)
    return {
        "same_source": True,
        "source": _public_source_summary(left),
        "left": left_summary,
        "right": right_summary,
        "differences": {
            "requested_parser_changed": left.requested_parser_id != right.requested_parser_id,
            "options_changed": left.options != right.options,
            "status_changed": left.status != right.status,
            "quality_state_changed": left.quality_state != right.quality_state,
            "attempt_count_delta": len(right.attempts) - len(left.attempts),
            "elapsed_ms_delta": _duration_delta(left_summary, right_summary),
            "structural_counts_delta": _structural_counts_delta(left_counts, right_counts),
        },
    }


def _public_source_summary(job: ParseJob) -> dict[str, object]:
    return {
        "file_type": _safe_media_type(job.source_file_type),
        "size_bytes": job.source_size_bytes,
    }


def _summarize_attempts(job: ParseJob) -> dict[str, object]:
    statuses = Counter(_safe_identifier(item.status) or "unknown" for item in job.attempts)
    parser_ids = sorted(
        {
            safe_parser_id
            for item in job.attempts
            if (safe_parser_id := _safe_identifier(item.parser_id)) is not None
        }
    )
    successful_count = sum(item.status == "succeeded" for item in job.attempts)
    failed_count = sum(item.status == "failed" for item in job.attempts)
    return {
        "count": len(job.attempts),
        "successful_count": successful_count,
        "failed_count": failed_count,
        "other_count": len(job.attempts) - successful_count - failed_count,
        "total_duration_ms": sum(item.duration_ms for item in job.attempts),
        "parser_ids": parser_ids,
        "status_counts": dict(sorted(statuses.items())),
    }


def _elapsed_ms(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds() * 1000))


def _duration_delta(left: Mapping[str, object], right: Mapping[str, object]) -> int | None:
    left_duration = _nested_int(left, "duration", "elapsed_ms")
    right_duration = _nested_int(right, "duration", "elapsed_ms")
    if left_duration is None or right_duration is None:
        return None
    return right_duration - left_duration


def _nested_int(value: Mapping[str, object], outer: str, inner: str) -> int | None:
    nested = value.get(outer)
    if not isinstance(nested, Mapping):
        return None
    candidate = nested.get(inner)
    return candidate if isinstance(candidate, int) else None


def _structural_counts_delta(
    left: Mapping[str, object] | None,
    right: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if left is None or right is None:
        return None
    numeric_fields = (
        "block_count",
        "table_count",
        "asset_count",
        "ocr_span_count",
        "native_artifact_count",
        "warning_count",
    )
    delta = {
        field: _count_value(right, field) - _count_value(left, field)
        for field in numeric_fields
    }
    left_kinds = left.get("block_kind_counts")
    right_kinds = right.get("block_kind_counts")
    left_kind_counts = left_kinds if isinstance(left_kinds, Mapping) else {}
    right_kind_counts = right_kinds if isinstance(right_kinds, Mapping) else {}
    kind_names = sorted({*left_kind_counts, *right_kind_counts}, key=lambda item: str(item))
    delta["block_kind_counts"] = {
        _safe_identifier(str(kind)) or "unknown": _mapping_count(right_kind_counts, kind)
        - _mapping_count(left_kind_counts, kind)
        for kind in kind_names
    }
    return delta


def _normalise_structural_counts(
    counts: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if counts is None:
        return None
    numeric_fields = (
        "block_count",
        "table_count",
        "asset_count",
        "ocr_span_count",
        "native_artifact_count",
        "warning_count",
    )
    normalized: dict[str, object] = {
        field: _count_value(counts, field) for field in numeric_fields
    }
    raw_block_kinds = counts.get("block_kind_counts")
    if not isinstance(raw_block_kinds, Mapping):
        raw_block_kinds = {}
    normalized["block_kind_counts"] = {
        _safe_identifier(str(kind)) or "unknown": max(0, _mapping_count(raw_block_kinds, kind))
        for kind in sorted(raw_block_kinds, key=lambda item: str(item))
    }
    return normalized


def _count_value(counts: Mapping[str, object], field: str) -> int:
    value = counts.get(field)
    return value if isinstance(value, int) and value >= 0 else 0


def _mapping_count(counts: Mapping[object, object], key: object) -> int:
    value = counts.get(key)
    return value if isinstance(value, int) and value >= 0 else 0


def _safe_identifier(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if _SAFE_IDENTIFIER.fullmatch(text) else "<redacted>"


def _safe_media_type(value: object) -> str:
    text = str(value).strip().lower()
    return text if _SAFE_MEDIA_TYPE.fullmatch(text) else "unknown"


def _safe_option_key(key: str) -> str:
    normalized = key.strip()
    key_parts = [part for part in re.split(r"[^a-z0-9]+", normalized.lower()) if part]
    lowered = normalized.lower()
    if (
        not _SAFE_IDENTIFIER.fullmatch(normalized)
        or any(part in _SENSITIVE_OPTION_KEY_PARTS for part in key_parts)
        or any(part in lowered for part in _SENSITIVE_OPTION_KEY_PARTS)
    ):
        return "<redacted>"
    return normalized


def _options_shape_fingerprint(options: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _option_shape(options),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _option_shape(value: Any) -> object:
    if isinstance(value, Mapping):
        entries = [
            {"key": _safe_option_key(str(key)), "shape": _option_shape(nested)}
            for key, nested in value.items()
        ]
        entries.sort(key=lambda item: json.dumps(item, ensure_ascii=True, sort_keys=True))
        return {
            "type": "object",
            "key_count": len(entries),
            "entries": entries[:_MAX_OPTION_SHAPE_ENTRIES],
            "truncated": len(entries) > _MAX_OPTION_SHAPE_ENTRIES,
        }
    if isinstance(value, (list, tuple)):
        item_shapes = [_option_shape(item) for item in value[:_MAX_OPTION_SHAPE_ITEMS]]
        return {
            "type": "array",
            "item_count": len(value),
            "items": item_shapes,
            "truncated": len(value) > _MAX_OPTION_SHAPE_ITEMS,
        }
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, bytes):
        return "bytes"
    return "other"
