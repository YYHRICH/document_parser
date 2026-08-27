"""Pure domain recommendations for parser reparse candidates.

This module deliberately accepts only detached, public data contracts.  It does
not load parser plugins, inspect storage, invoke FastAPI, or consume quality
objects directly.  The composition layer must adapt its job, quality report, or
failure record into :class:`ReparseContext` and :class:`ReparseSignal` first.

Parser-specific preferences are injected through ``priority_parser_ids`` and
``auto_options_by_parser``.  The recommendation algorithm itself therefore
remains valid for future plugins without a parser-family branch.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from ..core.contracts import ParserCapability


class ReparseSignalSource(StrEnum):
    """The independently-owned source of a safe reparse signal."""

    QUALITY = "quality"
    FAILURE = "failure"


class ReparseSignal(BaseModel):
    """A parser-agnostic, safe explanation for why a new parse is considered.

    ``message`` must already be safe for an end user or an audit record.  This
    boundary intentionally does not import a quality-report model or an
    orchestration failure enum: their owners adapt those richer records here.
    """

    source: ReparseSignalSource
    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False

    @field_validator("code", "message")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Reparse signal text cannot be blank.")
        return normalized


class ReparseContext(BaseModel):
    """A minimal, storage-free projection of the parent parse task.

    ``attempted_parser_ids`` records actual parser attempts known to the caller.
    It is intentionally separate from the parser capability snapshot so an
    immutable historical task can be projected without importing orchestration.
    """

    parent_parse_id: str | None = None
    source_extension: str = Field(min_length=1)
    current_parser_id: str | None = None
    attempted_parser_ids: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("parent_parse_id", "current_parser_id")
    @classmethod
    def normalize_optional_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Parser and parent identifiers cannot be blank.")
        return normalized

    @field_validator("source_extension")
    @classmethod
    def normalize_extension(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("source_extension cannot be blank.")
        return normalized if normalized.startswith(".") else f".{normalized}"

    @field_validator("attempted_parser_ids")
    @classmethod
    def normalize_attempted_parser_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        seen: set[str] = set()
        for parser_id in value:
            item = parser_id.strip()
            if not item:
                raise ValueError("attempted_parser_ids cannot contain blank values.")
            if item not in seen:
                normalized.append(item)
                seen.add(item)
        return tuple(normalized)


class ReparseRecommendationPolicy(BaseModel):
    """Resolved execution policy for pure recommendation.

    The caller supplies the *effective* cloud permission after applying server,
    tenant, consent, and request policy.  This module never treats a client
    preference as authority to enable cloud execution.
    """

    allow_cloud: bool = False
    allowed_parser_ids: tuple[str, ...] | None = None
    priority_parser_ids: tuple[str, ...] = Field(default_factory=tuple)
    exclude_attempted_parsers: bool = True
    allow_current_parser_retry: bool = False
    common_auto_options: dict[str, Any] = Field(default_factory=dict)
    auto_options_by_parser: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @field_validator("allowed_parser_ids", "priority_parser_ids")
    @classmethod
    def normalize_parser_id_sequence(
        cls,
        value: tuple[str, ...] | None,
    ) -> tuple[str, ...] | None:
        if value is None:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for parser_id in value:
            item = parser_id.strip()
            if not item:
                raise ValueError("Parser policy identifiers cannot be blank.")
            if item not in seen:
                normalized.append(item)
                seen.add(item)
        return tuple(normalized)

    @field_validator("auto_options_by_parser")
    @classmethod
    def normalize_option_parser_ids(
        cls,
        value: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for parser_id, options in value.items():
            item = parser_id.strip()
            if not item:
                raise ValueError("auto_options_by_parser cannot contain a blank parser ID.")
            normalized[item] = deepcopy(options)
        return normalized


class ReparseCandidate(BaseModel):
    """One deterministic candidate, including an explicit execution verdict."""

    parser_id: str
    reason: str
    executable: bool
    replaces_current_parser: bool
    requires_cloud: bool
    auto_options: dict[str, Any] = Field(default_factory=dict)
    blockers: tuple[str, ...] = Field(default_factory=tuple)


class AutomaticReparseOption(BaseModel):
    """The first executable candidate under the injected, stable priority policy."""

    parser_id: str
    reason: str
    requires_cloud: bool
    options: dict[str, Any] = Field(default_factory=dict)


class ReparseRecommendations(BaseModel):
    """Stable result that a delivery/API layer can serialize without extra work."""

    context: ReparseContext
    signals: tuple[ReparseSignal, ...]
    candidates: tuple[ReparseCandidate, ...]
    automatic: AutomaticReparseOption | None = None


def recommend_reparse(
    context: ReparseContext,
    capabilities: Iterable[ParserCapability],
    signals: Iterable[ReparseSignal],
    policy: ReparseRecommendationPolicy | None = None,
) -> ReparseRecommendations:
    """Recommend parsers using only capability facts and injected policy.

    Candidates are sorted by executable status, then the explicit policy priority,
    then parser ID.  A candidate is executable only when all of the following
    facts hold: it is allowed by policy, supports the source extension, is
    available, is not cloud-blocked, and is not an excluded prior attempt.
    Non-executable candidates remain visible with blockers so callers can explain
    why they are disabled, but they never receive automatic options or become the
    automatic choice.
    """

    context_snapshot = context.model_copy(deep=True)
    policy_snapshot = (policy or ReparseRecommendationPolicy()).model_copy(deep=True)
    signal_snapshot = _snapshot_signals(signals)
    if not signal_snapshot:
        raise ValueError("At least one quality or failure signal is required for reparse recommendation.")

    capability_snapshot = _snapshot_capabilities(capabilities)
    priority = {
        parser_id: index
        for index, parser_id in enumerate(policy_snapshot.priority_parser_ids)
    }
    candidates = [
        _make_candidate(
            context_snapshot,
            capability,
            signal_snapshot,
            policy_snapshot,
        )
        for capability in capability_snapshot
    ]
    candidates.sort(
        key=lambda candidate: (
            0 if candidate.executable else 1,
            priority.get(candidate.parser_id, len(priority)),
            candidate.parser_id,
        )
    )
    candidate_snapshot = tuple(candidates)
    automatic_candidate = next(
        (candidate for candidate in candidate_snapshot if candidate.executable),
        None,
    )
    automatic = (
        AutomaticReparseOption(
            parser_id=automatic_candidate.parser_id,
            reason=automatic_candidate.reason,
            requires_cloud=automatic_candidate.requires_cloud,
            options=deepcopy(automatic_candidate.auto_options),
        )
        if automatic_candidate is not None
        else None
    )
    return ReparseRecommendations(
        context=context_snapshot,
        signals=signal_snapshot,
        candidates=candidate_snapshot,
        automatic=automatic,
    )


def _make_candidate(
    context: ReparseContext,
    capability: ParserCapability,
    signals: tuple[ReparseSignal, ...],
    policy: ReparseRecommendationPolicy,
) -> ReparseCandidate:
    parser_id = capability.parser_id.strip()
    blockers = _candidate_blockers(context, capability, signals, policy)
    executable = not blockers
    replaces_current = (
        context.current_parser_id is not None and parser_id != context.current_parser_id
    )
    reason = _candidate_reason(
        context=context,
        capability=capability,
        signals=signals,
        replaces_current=replaces_current,
        blockers=blockers,
    )
    return ReparseCandidate(
        parser_id=parser_id,
        reason=reason,
        executable=executable,
        replaces_current_parser=replaces_current,
        requires_cloud=capability.requires_network,
        auto_options=_auto_options_for(parser_id, policy) if executable else {},
        blockers=tuple(blockers),
    )


def _candidate_blockers(
    context: ReparseContext,
    capability: ParserCapability,
    signals: tuple[ReparseSignal, ...],
    policy: ReparseRecommendationPolicy,
) -> list[str]:
    parser_id = capability.parser_id.strip()
    blockers: list[str] = []
    allowed = policy.allowed_parser_ids
    if allowed is not None and parser_id not in allowed:
        blockers.append("Parser is not allowed by the effective reparse policy.")
    if context.source_extension not in _normalized_formats(capability):
        blockers.append(f"Parser does not support {context.source_extension}.")
    if not capability.available:
        blockers.append(capability.unavailable_reason or "Parser is unavailable in the current environment.")
    if capability.requires_network and not policy.allow_cloud:
        blockers.append("Effective cloud policy forbids this network parser.")

    current_retry_allowed = (
        parser_id == context.current_parser_id
        and policy.allow_current_parser_retry
        and _has_retryable_failure(signals)
    )
    if parser_id == context.current_parser_id and not current_retry_allowed:
        blockers.append(
            "Current parser is not an executable reparse candidate without an enabled retryable failure policy."
        )
    if (
        policy.exclude_attempted_parsers
        and parser_id in context.attempted_parser_ids
        and not current_retry_allowed
    ):
        blockers.append("Parser was already attempted by the parent task.")
    return blockers


def _candidate_reason(
    *,
    context: ReparseContext,
    capability: ParserCapability,
    signals: tuple[ReparseSignal, ...],
    replaces_current: bool,
    blockers: list[str],
) -> str:
    signal_summary = "; ".join(
        f"{signal.source.value}:{signal.code} ({signal.message})" for signal in signals
    )
    if capability.parser_id == context.current_parser_id:
        base = "Current parser retry was evaluated against the supplied signals."
    elif replaces_current:
        base = f"Alternative parser supports {context.source_extension}."
    else:
        base = f"Parser supports {context.source_extension}."
    if blockers:
        return f"{base} Reparse signals: {signal_summary}. Not executable: {' '.join(blockers)}"
    return f"{base} Reparse signals: {signal_summary}."


def _auto_options_for(
    parser_id: str,
    policy: ReparseRecommendationPolicy,
) -> dict[str, Any]:
    # The reparse marker is a domain invariant.  Policy may add parser-neutral or
    # plugin-owned options, but may not disable the fact that this is a reparse.
    return {
        **deepcopy(policy.common_auto_options),
        **deepcopy(policy.auto_options_by_parser.get(parser_id, {})),
        "reparse": True,
    }


def _has_retryable_failure(signals: tuple[ReparseSignal, ...]) -> bool:
    return any(
        signal.source == ReparseSignalSource.FAILURE and signal.retryable
        for signal in signals
    )


def _normalized_formats(capability: ParserCapability) -> set[str]:
    formats: set[str] = set()
    for extension in capability.formats:
        normalized = str(extension).strip().lower()
        if normalized:
            formats.add(normalized if normalized.startswith(".") else f".{normalized}")
    return formats


def _snapshot_capabilities(
    capabilities: Iterable[ParserCapability],
) -> tuple[ParserCapability, ...]:
    snapshot: list[ParserCapability] = []
    known: set[str] = set()
    for capability in capabilities:
        parser_id = capability.parser_id.strip()
        if not parser_id:
            raise ValueError("Capability snapshot cannot contain a blank parser ID.")
        if parser_id in known:
            raise ValueError(f"Duplicate parser ID in capability snapshot: {parser_id}")
        snapshot.append(capability.model_copy(deep=True, update={"parser_id": parser_id}))
        known.add(parser_id)
    return tuple(snapshot)


def _snapshot_signals(signals: Iterable[ReparseSignal]) -> tuple[ReparseSignal, ...]:
    snapshot = [signal.model_copy(deep=True) for signal in signals]
    snapshot.sort(
        key=lambda signal: (
            signal.source.value,
            signal.code,
            signal.message,
            signal.retryable,
        )
    )
    return tuple(snapshot)


__all__ = [
    "AutomaticReparseOption",
    "ReparseCandidate",
    "ReparseContext",
    "ReparseRecommendationPolicy",
    "ReparseRecommendations",
    "ReparseSignal",
    "ReparseSignalSource",
    "recommend_reparse",
]
