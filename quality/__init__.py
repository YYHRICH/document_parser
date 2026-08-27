"""Deterministic, parser-agnostic document quality layer.

The pure public entry point is ``run_quality(parsed_document, config=...)``.
It accepts only the shared ParsedDocument contract plus optional QualityConfig;
routing, parsers, backend, Gateway, and artifact directories are not required.
"""

from quality.api import (
    get_quality_evidence_requirements,
    inspect_quality_capabilities,
    load_parsed_document,
    run_quality,
    run_quality_json,
    write_quality_package,
)
from quality.config import GateConfig, QualityConfig
from quality.evidence import (
    CapabilityDeclaration,
    CapabilityEntry,
    EvidenceRequirement,
    QualityEvidenceNegotiator,
    QualityEvidenceRequirements,
    RuleEvidenceNegotiation,
)
from quality.ids import binding_id, block_id, issue_id, relation_id, stable_id
from quality.models_internal import (
    BindingCandidate,
    CapabilityObservation,
    EvidenceRef,
    IssueDraft,
    RelationCandidate,
    RepairProposal,
    RuleResult,
)

__all__ = [
    "get_quality_evidence_requirements",
    "inspect_quality_capabilities",
    "load_parsed_document",
    "run_quality",
    "run_quality_json",
    "write_quality_package",
    "GateConfig",
    "QualityConfig",
    "CapabilityDeclaration",
    "CapabilityEntry",
    "EvidenceRequirement",
    "QualityEvidenceNegotiator",
    "QualityEvidenceRequirements",
    "RuleEvidenceNegotiation",
    "stable_id",
    "binding_id",
    "block_id",
    "issue_id",
    "relation_id",
    "BindingCandidate",
    "CapabilityObservation",
    "EvidenceRef",
    "IssueDraft",
    "RelationCandidate",
    "RepairProposal",
    "RuleResult",
]
