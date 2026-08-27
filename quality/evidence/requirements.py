"""Quality-owned evidence requirements.

Rules declare their minimum evidence here through ``EvidenceRequirement``.
``QualityEvidenceRequirements`` is the immutable, parser-neutral catalogue that
makes those declarations inspectable and testable at the quality boundary.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

EvidenceKind = Literal[
    "blocks",
    "block_anchor",
    "block_order",
    "heading_level",
    "tables",
    "table_cells",
    "table_bbox",
    "ocr_spans",
    "assets",
    "native_artifacts",
    "capabilities",
    "provenance",
]

EvidenceScope = Literal["document", "block", "table", "cell"]


@dataclass(frozen=True)
class EvidenceRequirement:
    """One evidence requirement declared by a deterministic quality rule.

    ``required_state`` is deliberately small: ``available`` requires complete
    evidence, while ``partial_allowed`` allows a rule to run in limited mode.
    Missing or failed evidence is handled by capability negotiation rather than
    by parser-specific branches inside rules.
    """

    kind: EvidenceKind
    required_state: Literal["available", "partial_allowed"]
    scope: EvidenceScope = "document"
    purpose: str = ""

    def as_dict(self) -> dict[str, str]:
        """Return a stable, JSON-friendly representation for audit output."""

        result = {
            "kind": self.kind,
            "required_state": self.required_state,
            "scope": self.scope,
        }
        if self.purpose:
            result["purpose"] = self.purpose
        return result


@dataclass(frozen=True)
class QualityEvidenceRequirements:
    """Immutable map from quality rule ID to its required input evidence.

    This is owned by the quality layer.  Parsers do not need to import it or
    branch on it; they publish their generic ``ParsedDocument.capabilities``
    declaration, and quality negotiates the two at runtime.
    """

    by_rule_id: Mapping[str, tuple[EvidenceRequirement, ...]]
    schema_name: str = field(
        default="QualityEvidenceRequirements",
        init=False,
    )
    schema_version: str = field(default="1.0", init=False)

    def __post_init__(self) -> None:
        normalized: dict[str, tuple[EvidenceRequirement, ...]] = {}
        for rule_id, requirements in self.by_rule_id.items():
            if not isinstance(rule_id, str) or not rule_id.strip():
                raise ValueError("quality evidence requirements require a non-empty rule ID")
            values = tuple(requirements)
            if any(not isinstance(value, EvidenceRequirement) for value in values):
                raise TypeError("each rule requirement must be an EvidenceRequirement")
            if len(values) != len(set(values)):
                raise ValueError(f"rule {rule_id} declares duplicate evidence requirements")
            normalized[rule_id] = values
        object.__setattr__(self, "by_rule_id", MappingProxyType(normalized))

    @classmethod
    def from_rules(cls, rules: Iterable[object]) -> "QualityEvidenceRequirements":
        """Build the catalogue from rule classes without importing parser code."""

        values: dict[str, tuple[EvidenceRequirement, ...]] = {}
        for rule in rules:
            rule_id = getattr(rule, "rule_id", None)
            if not isinstance(rule_id, str) or not rule_id.strip():
                raise ValueError("quality rule is missing a stable rule_id")
            if rule_id in values:
                raise ValueError(f"duplicate quality rule ID: {rule_id}")
            requirements = tuple(getattr(rule, "required_evidence", ()))
            values[rule_id] = requirements
        return cls(values)

    @property
    def rule_ids(self) -> tuple[str, ...]:
        """Stable sorted rule IDs for fixtures, documentation, and audits."""

        return tuple(sorted(self.by_rule_id))

    def for_rule(self, rule_id: str) -> tuple[EvidenceRequirement, ...]:
        """Return the complete requirement declaration for one rule."""

        try:
            return self.by_rule_id[rule_id]
        except KeyError as error:
            raise KeyError(f"no evidence declaration registered for {rule_id}") from error

    def as_dict(self) -> dict[str, list[dict[str, str]]]:
        """Return a stable JSON-friendly view without exposing mutable state."""

        return {
            rule_id: [requirement.as_dict() for requirement in self.for_rule(rule_id)]
            for rule_id in self.rule_ids
        }
