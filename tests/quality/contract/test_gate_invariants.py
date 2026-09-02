"""Gate 不变量测试（M0）：公共契约层的硬约束验证。

对应 spec §8.3 Gate 不变量与验收清单「契约」部分：
- reparse_required 必须带合法 recommendation；
- critical_false_pass=true 时禁止 pass / pass_with_warnings；
- QualityPackage 的 canonical/report document_id 一致；
- 非 available 的 EvidenceCapability 必须带 reason。
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from document_parser.domain.model.contracts import (
    EvidenceAvailability,
    EvidenceCapability,
    GateSummary,
    QualityCapabilityState,
    QualityReport,
    QualityState,
    ReparseRecommendation,
)

DOC_ID = uuid4()


def _base_report(state: QualityState, **kwargs) -> QualityReport:
    """构造一个合法的 QualityReport（capability_matrix 为空通过默认值补全）。"""
    defaults = dict(
        contract_version="1.0",
        document_id=DOC_ID,
        state=state,
        capability_matrix={},
        gate_summary=GateSummary(),
    )
    defaults.update(kwargs)
    return QualityReport(**defaults)


def test_reparse_required_must_have_recommendation():
    with pytest.raises(ValidationError):
        _base_report(QualityState.REPARSE_REQUIRED)


def test_reparse_required_with_recommendation_is_valid():
    report = _base_report(
        QualityState.REPARSE_REQUIRED,
        reparse_recommendation=ReparseRecommendation(
            parser_id="mineru",
            reason="table cells missing, reparse may recover grid",
            parser_options={"is_ocr": True},
        ),
    )
    assert report.state == QualityState.REPARSE_REQUIRED
    assert report.reparse_recommendation.parser_id == "mineru"


def test_reparse_recommendation_reason_required():
    with pytest.raises(ValidationError):
        _base_report(
            QualityState.REPARSE_REQUIRED,
            reparse_recommendation=ReparseRecommendation(parser_id="mineru", reason=""),
        )


@pytest.mark.parametrize("state", [QualityState.PASS, QualityState.PASS_WITH_WARNINGS])
def test_critical_false_pass_forbids_pass_states(state):
    with pytest.raises(ValidationError):
        _base_report(
            state,
            gate_summary=GateSummary(critical_false_pass=True),
        )


def test_critical_false_pass_allows_blocking_states():
    for state in (QualityState.REPARSE_REQUIRED, QualityState.REJECTED):
        kwargs = {}
        if state == QualityState.REPARSE_REQUIRED:
            kwargs["reparse_recommendation"] = ReparseRecommendation(
                parser_id="docling", reason="reparse"
            )
        report = _base_report(
            state,
            gate_summary=GateSummary(critical_false_pass=True),
            **kwargs,
        )
        assert report.gate_summary.critical_false_pass is True


def test_unavailable_capability_requires_reason():
    with pytest.raises(ValidationError):
        EvidenceCapability(state=EvidenceAvailability.UNAVAILABLE)


def test_available_capability_allows_missing_reason():
    cap = EvidenceCapability(state=EvidenceAvailability.AVAILABLE)
    assert cap.state == EvidenceAvailability.AVAILABLE


def test_gate_summary_counts_are_non_negative():
    with pytest.raises(ValidationError):
        GateSummary(critical_issue_count=-1)
