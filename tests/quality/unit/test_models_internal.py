"""内部模型单元测试：可构造、不可变、类型正确。"""

from dataclasses import FrozenInstanceError

import pytest

from document_parser.domain.model.contracts import (
    CanonicalSourceLocator,
    IssueSeverity,
    QualityCapabilityState,
)

from document_parser.domain.quality.models_internal import (
    BindingCandidate,
    CapabilityObservation,
    EvidenceRef,
    IssueDraft,
    RelationCandidate,
    RepairProposal,
    RuleResult,
)


def test_evidence_ref_construction():
    ref = EvidenceRef(object_type="block", object_id="mineru-content-0001", field_path="text")
    assert ref.object_type == "block"
    assert ref.value_sha256 is None


def test_evidence_ref_is_frozen():
    ref = EvidenceRef(object_type="block", object_id="b1", field_path="text")
    with pytest.raises(FrozenInstanceError):
        ref.object_id = "changed"  # type: ignore[misc]


def test_rule_result_empty_defaults():
    result = RuleResult()
    assert result.issues == ()
    assert result.binding_candidates == ()
    assert result.capability_observations == ()


def test_rule_result_with_content():
    result = RuleResult(
        issues=(
            IssueDraft(
                severity=IssueSeverity.INFO,
                category="citation_binding",
                message="test",
                affected_block_ids=["p1"],
            ),
        ),
        relation_candidates=(
            RelationCandidate(
                relation_type="parent_child",
                from_id="h1",
                to_id="h2",
            ),
        ),
        binding_candidates=(),
    )
    assert len(result.issues) == 1
    assert result.issues[0].severity == IssueSeverity.INFO
    assert result.relation_candidates[0].relation_type == "parent_child"


def test_binding_candidate_carries_column_path():
    candidate = BindingCandidate(
        table_id="table-001",
        block_id="canonical-table-001",
        row_key="TN3K",
        column_path=["Train 10%"],
        value="259",
        source_locator=CanonicalSourceLocator(
            source_block_id="mineru-content-0004",
            provenance_status=QualityCapabilityState.VERIFIED,
        ),
    )
    assert candidate.column_path == ["Train 10%"]
    assert candidate.source_locator.source_block_id == "mineru-content-0004"


def test_capability_observation():
    obs = CapabilityObservation(
        capability_name="table_grid_reliable",
        observed_state=QualityCapabilityState.VERIFIED,
    )
    assert obs.observed_state == QualityCapabilityState.VERIFIED


def test_repair_proposal_defaults_replayable():
    proposal = RepairProposal(
        rule_id="QL-RPR-001",
        description="normalize trailing whitespace",
    )
    assert proposal.replayable is True
    assert proposal.affected_block_ids == []
