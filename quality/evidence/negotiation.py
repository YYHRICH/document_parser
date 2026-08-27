"""Parser-neutral capability negotiation for the quality layer.

The input contract already carries generic ``ParsedDocument.capabilities``.
This module snapshots that declaration together with observed representations,
then negotiates it against rule-owned ``EvidenceRequirement`` values.  It never
looks at parser IDs, routing decisions, native parser objects, or file paths.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from quality.contracts import EvidenceAvailability
from quality.evidence.availability import AvailabilityResolver, RequirementCheck
from quality.evidence.requirements import EvidenceKind, EvidenceRequirement


@dataclass(frozen=True)
class CapabilityEntry:
    """One declared or observed evidence availability fact."""

    name: str
    state: EvidenceAvailability
    reason: str | None = None
    granularity: str | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "parsed_document.capabilities"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("capability entry name must not be empty")
        if not isinstance(self.state, EvidenceAvailability):
            object.__setattr__(self, "state", EvidenceAvailability(self.state))
        if self.state != EvidenceAvailability.AVAILABLE and not self.reason:
            raise ValueError("non-available capability entries require a reason")
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))


@dataclass(frozen=True)
class CapabilityDeclaration:
    """Immutable, parser-neutral snapshot of a ``ParsedDocument`` input.

    ``declared`` preserves the generic capability declaration produced by the
    normalizer.  ``observed`` captures quality-side checks of concrete fields
    such as table cells and OCR spans, so a claimed capability cannot override
    absent evidence.  Parser identity is intentionally not represented.
    """

    table_count: int
    declared: Mapping[str, CapabilityEntry] = field(default_factory=dict)
    observed: Mapping[EvidenceKind, CapabilityEntry] = field(default_factory=dict)
    document_schema_name: str = "ParsedDocument"
    document_schema_version: str = "2.2"
    schema_name: str = field(default="CapabilityDeclaration", init=False)
    schema_version: str = field(default="1.0", init=False)

    def __post_init__(self) -> None:
        if self.table_count < 0:
            raise ValueError("table_count must be non-negative")
        declared = dict(self.declared)
        observed = dict(self.observed)
        for name, entry in declared.items():
            if name != entry.name:
                raise ValueError("declared capability map key must match entry name")
        for name, entry in observed.items():
            if name != entry.name:
                raise ValueError("observed capability map key must match entry name")
        object.__setattr__(self, "declared", MappingProxyType(declared))
        object.__setattr__(self, "observed", MappingProxyType(observed))

    @classmethod
    def from_parsed_document(
        cls,
        parsed_document: object,
        *,
        representation_states: Mapping[
            EvidenceKind,
            tuple[EvidenceAvailability, str | None],
        ] | None = None,
    ) -> "CapabilityDeclaration":
        """Snapshot only generic evidence fields from an in-memory document."""

        declared: dict[str, CapabilityEntry] = {}
        raw_capabilities = getattr(parsed_document, "capabilities", {}) or {}
        for name, capability in raw_capabilities.items():
            raw_state = getattr(capability, "state", None)
            try:
                state = EvidenceAvailability(raw_state)
            except (TypeError, ValueError):
                state = EvidenceAvailability.UNAVAILABLE
            reason = getattr(capability, "reason", None)
            if state != EvidenceAvailability.AVAILABLE and not reason:
                reason = f"capabilities declaration for {name} is missing a usable state or reason"
            raw_evidence = getattr(capability, "evidence", {}) or {}
            declared[str(name)] = CapabilityEntry(
                name=str(name),
                state=state,
                reason=reason,
                granularity=getattr(capability, "granularity", None),
                evidence=raw_evidence if isinstance(raw_evidence, Mapping) else {},
            )

        observed: dict[EvidenceKind, CapabilityEntry] = {}
        for kind, value in (representation_states or {}).items():
            raw_state, reason = value
            try:
                state = EvidenceAvailability(raw_state)
            except (TypeError, ValueError):
                state = EvidenceAvailability.UNAVAILABLE
            if state != EvidenceAvailability.AVAILABLE and not reason:
                reason = f"quality observation for {kind} is unavailable"
            observed[kind] = CapabilityEntry(
                name=kind,
                state=state,
                reason=reason,
                source="quality.representations",
            )

        tables = getattr(parsed_document, "tables", ()) or ()
        return cls(
            table_count=len(tables),
            declared=declared,
            observed=observed,
            document_schema_name=str(
                getattr(parsed_document, "schema_name", "ParsedDocument")
            ),
            document_schema_version=str(
                getattr(parsed_document, "schema_version", "2.2")
            ),
        )

    def build_resolver(self) -> AvailabilityResolver:
        """Build the legacy-compatible resolver from this immutable snapshot."""

        return AvailabilityResolver(
            capabilities=dict(self.declared),
            table_count=self.table_count,
            representation_states={
                kind: (entry.state, entry.reason)
                for kind, entry in self.observed.items()
            },
        )


@dataclass(frozen=True)
class RuleEvidenceNegotiation:
    """Auditable result of negotiating one rule against one document input."""

    rule_id: str
    checks: tuple[RequirementCheck, ...]
    mode: str
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        """Return a stable, JSON-friendly audit payload."""

        return {
            "rule_id": self.rule_id,
            "mode": self.mode,
            "reason": self.reason,
            "checks": [
                {
                    "kind": check.requirement.kind,
                    "required_state": check.requirement.required_state,
                    "scope": check.requirement.scope,
                    "state": check.state.value,
                    "applicable": check.applicable,
                    "reason": check.reason,
                }
                for check in self.checks
            ],
        }


class QualityEvidenceNegotiator:
    """Matches quality-owned requirements with one capability declaration."""

    def __init__(
        self,
        declaration: CapabilityDeclaration,
        *,
        resolver: AvailabilityResolver | None = None,
    ) -> None:
        self.declaration = declaration
        self._resolver = resolver or declaration.build_resolver()

    def check_requirements(
        self,
        requirements: tuple[EvidenceRequirement, ...],
    ) -> tuple[RequirementCheck, ...]:
        return self._resolver.check_all(requirements)

    def summary(
        self,
        requirements: tuple[EvidenceRequirement, ...],
    ) -> tuple[str, str]:
        return self._resolver.summary(requirements)

    def negotiate(
        self,
        rule_id: str,
        requirements: tuple[EvidenceRequirement, ...],
    ) -> RuleEvidenceNegotiation:
        if not rule_id:
            raise ValueError("rule_id must not be empty")
        checks = self.check_requirements(requirements)
        mode, reason = self.summary(requirements)
        return RuleEvidenceNegotiation(
            rule_id=rule_id,
            checks=checks,
            mode=mode,
            reason=reason,
        )
