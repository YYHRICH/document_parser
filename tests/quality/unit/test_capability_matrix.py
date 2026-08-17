"""Capability Matrix 汇总器单元测试。"""

from __future__ import annotations

from pathlib import Path

from document_parser.core.contracts import QualityCapabilityState

from quality.evidence.context import EvidenceContext
from quality.gates.capabilities import (
    CapabilityMatrixBuilder,
    STANDARD_CAPABILITIES,
)
from quality.models_internal import CapabilityObservation

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "quality" / "fixtures" / "parsed_documents"


def _load(sample: str):
    from document_parser.core.contracts import ParsedDocument

    return ParsedDocument.model_validate_json(
        (FIXTURES / f"{sample}.json").read_text(encoding="utf-8")
    )


def test_merge_same_capability_takes_worst():
    builder = CapabilityMatrixBuilder()
    context = EvidenceContext(_load("sdp-004-mineru"))
    verdicts = builder.build(
        [
            CapabilityObservation("content_complete", QualityCapabilityState.VERIFIED),
            CapabilityObservation("content_complete", QualityCapabilityState.MANUAL_REVIEW_REQUIRED),
        ],
        context,
    )
    assert verdicts["content_complete"].state == QualityCapabilityState.MANUAL_REVIEW_REQUIRED
    assert verdicts["content_complete"].blocking


def test_unimplemented_capabilities_not_blocking():
    """M1：标题/表格/引用规则未实现 → unavailable 且不阻塞。"""
    builder = CapabilityMatrixBuilder()
    context = EvidenceContext(_load("sdp-004-mineru"))
    verdicts = builder.build([], context)
    for name in (
        "heading_tree_reliable",
        "table_grid_reliable",
        "table_field_binding_reliable",
        "non_table_relation_reliable",
    ):
        v = verdicts[name]
        assert v.state == QualityCapabilityState.UNAVAILABLE, name
        assert v.blocking is False, f"{name} 不应阻塞（M1 未实现）"


def test_table_capabilities_not_applicable_without_tables():
    """D-03：无表格文档表格能力不适用、不阻塞。"""
    builder = CapabilityMatrixBuilder()
    context = EvidenceContext(_load("sdp-006-fallback"))
    assert not context.parsed.tables
    verdicts = builder.build([], context)
    for name in ("table_grid_reliable", "table_field_binding_reliable"):
        v = verdicts[name]
        assert v.applicable is False
        assert v.blocking is False
        assert "not_applicable" in v.evidence.get("applicability", "")


def test_standard_capabilities_all_present():
    builder = CapabilityMatrixBuilder()
    context = EvidenceContext(_load("sdp-004-mineru"))
    verdicts = builder.build([], context)
    assert set(STANDARD_CAPABILITIES) <= set(verdicts)


def test_to_public_assessments_projects_state_and_evidence():
    builder = CapabilityMatrixBuilder()
    context = EvidenceContext(_load("sdp-004-mineru"))
    verdicts = builder.build(
        [CapabilityObservation("content_complete", QualityCapabilityState.VERIFIED)],
        context,
    )
    assessments = builder.to_public_assessments(verdicts)
    for name, assessment in assessments.items():
        # 公共契约只有 state + evidence（applicable/blocking 不投影）
        assert assessment.state is not None
        assert isinstance(assessment.evidence, dict)
