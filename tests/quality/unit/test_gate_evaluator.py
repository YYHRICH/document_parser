"""Gate 决策器单元测试：自动状态推导、优先级、D-08/D-03 配置。"""

from __future__ import annotations

import pytest

from document_parser.domain.model.contracts import (
    IssueSeverity,
    QualityCapabilityState,
    QualityState,
    ReparseRecommendation,
)

from document_parser.domain.quality.config import GateConfig
from document_parser.domain.quality.gates.capabilities import CapabilityVerdict
from document_parser.domain.quality.gates.evaluator import GateEvaluator
from document_parser.domain.quality.models_internal import IssueDraft


def _issue(severity: IssueSeverity, message: str = "issue") -> IssueDraft:
    return IssueDraft(severity=severity, category="test", message=message)


def _cap(name: str, state: QualityCapabilityState) -> CapabilityVerdict:
    return CapabilityVerdict(name=name, state=state, blocking=state != QualityCapabilityState.VERIFIED)


def test_clean_document_passes():
    decision = GateEvaluator().decide([], {})
    assert decision.state == QualityState.PASS


def test_warning_issue_triggers_pass_with_warnings():
    decision = GateEvaluator().decide([_issue(IssueSeverity.WARNING)], {})
    assert decision.state == QualityState.PASS_WITH_WARNINGS
    assert decision.summary.warning_or_info_issue_count == 1


def test_info_issue_does_not_block_pass_d08():
    decision = GateEvaluator().decide([_issue(IssueSeverity.INFO)], {})
    assert decision.state == QualityState.PASS


def test_info_issue_blocks_when_configured():
    evaluator = GateEvaluator(GateConfig(info_blocks_pass=True))
    decision = evaluator.decide([_issue(IssueSeverity.INFO)], {})
    assert decision.state == QualityState.PASS_WITH_WARNINGS


def test_info_policy_preserves_all_gate_states():
    evaluator = GateEvaluator(GateConfig(info_blocks_pass=True))
    info = [_issue(IssueSeverity.INFO)]

    assert evaluator.decide(info, {}).state == QualityState.PASS_WITH_WARNINGS
    assert evaluator.decide([_issue(IssueSeverity.WARNING), *info], {}).state == QualityState.PASS_WITH_WARNINGS
    assert evaluator.decide([_issue(IssueSeverity.CRITICAL), *info], {}).state == QualityState.REJECTED
    assert evaluator.decide(
        info,
        {"heading_tree_reliable": _cap("heading_tree_reliable", QualityCapabilityState.MANUAL_REVIEW_REQUIRED)},
    ).state == QualityState.PASS_WITH_WARNINGS
    assert evaluator.decide(
        info,
        {"content_complete": _cap("content_complete", QualityCapabilityState.REPARSE_REQUIRED)},
        reparse_recommendation=ReparseRecommendation(parser_id="mineru", reason="reparse"),
    ).state == QualityState.REPARSE_REQUIRED


def test_critical_issue_rejects():
    decision = GateEvaluator().decide([_issue(IssueSeverity.CRITICAL)], {})
    assert decision.state == QualityState.REJECTED
    assert decision.summary.critical_issue_count == 1


def test_manual_critical_issue_target_is_not_supported():
    evaluator = GateEvaluator(GateConfig(critical_issue_min_state="manual_review_required"))
    with pytest.raises(ValueError, match="reparse_required 或 rejected"):
        evaluator.decide([_issue(IssueSeverity.CRITICAL)], {})


def test_critical_issue_can_require_reparse_with_recommendation():
    evaluator = GateEvaluator(
        GateConfig(critical_issue_min_state="reparse_required")
    )
    decision = evaluator.decide(
        [_issue(IssueSeverity.CRITICAL)],
        {},
        reparse_recommendation=ReparseRecommendation(
            parser_id="mineru", reason="reparse"
        ),
    )

    assert decision.state == QualityState.REPARSE_REQUIRED
    assert decision.summary.reparse_issue_count == 1


def test_manual_capability_becomes_warning_without_manual_queue():
    verdicts = {"heading_tree_reliable": _cap("heading_tree_reliable", QualityCapabilityState.MANUAL_REVIEW_REQUIRED)}
    decision = GateEvaluator().decide([], verdicts)
    assert decision.state == QualityState.PASS_WITH_WARNINGS


def test_inferred_capability_becomes_warning_without_manual_queue():
    verdicts = {"heading_tree_reliable": _cap("heading_tree_reliable", QualityCapabilityState.INFERRED)}
    decision = GateEvaluator().decide([], verdicts)
    assert decision.state == QualityState.PASS_WITH_WARNINGS


def test_unavailable_capability_not_blocking_d03():
    verdicts = {
        "table_grid_reliable": CapabilityVerdict(
            name="table_grid_reliable",
            state=QualityCapabilityState.UNAVAILABLE,
            applicable=False,
            blocking=False,
        )
    }
    decision = GateEvaluator().decide([], verdicts)
    assert decision.state == QualityState.PASS


def test_reparse_with_recommendation():
    verdicts = {"content_complete": _cap("content_complete", QualityCapabilityState.REPARSE_REQUIRED)}
    decision = GateEvaluator().decide(
        [],
        verdicts,
        reparse_recommendation=ReparseRecommendation(parser_id="mineru", reason="reparse"),
    )
    assert decision.state == QualityState.REPARSE_REQUIRED


def test_reparse_without_recommendation_is_rejected():
    """没有自动重解析建议时直接拒绝，不产生人工复核队列。"""
    verdicts = {"content_complete": _cap("content_complete", QualityCapabilityState.REPARSE_REQUIRED)}
    decision = GateEvaluator().decide([], verdicts)
    assert decision.state == QualityState.REJECTED


def test_rejected_capability_wins_over_manual():
    verdicts = {
        "content_complete": _cap("content_complete", QualityCapabilityState.REJECTED),
        "heading_tree_reliable": _cap("heading_tree_reliable", QualityCapabilityState.MANUAL_REVIEW_REQUIRED),
    }
    decision = GateEvaluator().decide([], verdicts)
    assert decision.state == QualityState.REJECTED


def test_critical_false_pass_never_in_clean_pass():
    decision = GateEvaluator().decide([], {})
    assert decision.summary.critical_false_pass is False


def test_blocking_reasons_recorded():
    verdicts = {"heading_tree_reliable": _cap("heading_tree_reliable", QualityCapabilityState.MANUAL_REVIEW_REQUIRED)}
    decision = GateEvaluator().decide([], verdicts)
    assert any("heading_tree_reliable" in r for r in decision.blocking_reasons)
    assert decision.summary.capability_blockers == []
