"""Gate 决策器：质量层唯一的最终状态判定者（spec §8）。

优先级：rejected > reparse_required > manual_review_required
        > pass_with_warnings > pass

规则模块只产观测，不得自行指定最终状态。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from document_parser.core.contracts import (
    GateSummary,
    IssueSeverity,
    IssueStatus,
    QualityCapabilityState,
    QualityState,
    ReparseRecommendation,
)

from quality.config import GateConfig
from quality.gates.capabilities import CapabilityVerdict
from quality.models_internal import IssueDraft


@dataclass(frozen=True)
class GateDecision:
    """Gate 决策结果（内部判定 + 公共投影）。"""

    state: QualityState
    summary: GateSummary
    blocking_reasons: tuple[str, ...] = ()


class GateEvaluator:
    """唯一状态决策器。"""

    def __init__(self, config: GateConfig | None = None) -> None:
        self._config = config or GateConfig()

    def decide(
        self,
        issues: list[IssueDraft],
        capability_verdicts: dict[str, CapabilityVerdict],
        reparse_recommendation: ReparseRecommendation | None = None,
    ) -> GateDecision:
        """由未解决 issue + 能力判定推导最终状态。"""
        blocking_reasons: list[str] = []

        # 1. 能力阻塞项（blocking=True 且非 verified/unavailable）
        capability_blockers = [
            verdict
            for verdict in capability_verdicts.values()
            if verdict.blocking
            and verdict.state
            in {
                QualityCapabilityState.REJECTED,
                QualityCapabilityState.REPARSE_REQUIRED,
                QualityCapabilityState.MANUAL_REVIEW_REQUIRED,
                QualityCapabilityState.INFERRED,
            }
        ]
        rejected_caps = [
            v for v in capability_blockers if v.state == QualityCapabilityState.REJECTED
        ]
        reparse_caps = [
            v
            for v in capability_blockers
            if v.state == QualityCapabilityState.REPARSE_REQUIRED
        ]
        manual_caps = [
            v
            for v in capability_blockers
            if v.state
            in {
                QualityCapabilityState.MANUAL_REVIEW_REQUIRED,
                QualityCapabilityState.INFERRED,
            }
        ]

        # 2. 未解决 issue 统计（IssueDraft 无 status：规则产出的 issue 默认未解决）
        critical_issues = [
            i for i in issues if i.severity == IssueSeverity.CRITICAL
        ]
        warning_issues = [
            i for i in issues if i.severity == IssueSeverity.WARNING
        ]
        info_issues = [i for i in issues if i.severity == IssueSeverity.INFO]

        # 3. 按优先级决策
        if rejected_caps or critical_issues:
            blocking_reasons.extend(
                f"capability {v.name} rejected" for v in rejected_caps
            )
            blocking_reasons.extend(
                f"critical issue: {i.message}" for i in critical_issues
            )
            state = QualityState.REJECTED
        elif reparse_caps:
            if reparse_recommendation is not None:
                blocking_reasons.extend(
                    f"capability {v.name} reparse_required" for v in reparse_caps
                )
                state = QualityState.REPARSE_REQUIRED
            else:
                # 契约要求 reparse_required 必须带建议；无合法建议时
                # 不能假装 reparse：降级为人工复核
                blocking_reasons.append("reparse required but no valid recommendation")
                state = QualityState.MANUAL_REVIEW_REQUIRED
        elif manual_caps:
            blocking_reasons.extend(
                f"capability {v.name} = {v.state.value}" for v in manual_caps
            )
            state = QualityState.MANUAL_REVIEW_REQUIRED
        elif warning_issues:
            blocking_reasons.extend(f"warning issue: {i.message}" for i in warning_issues)
            state = (
                QualityState.PASS_WITH_WARNINGS
                if self._config.warnings_trigger_pass_with_warnings
                else QualityState.PASS
            )
        else:
            state = QualityState.PASS

        # 4. 不变量修正（D-08：info 是否阻塞）
        if self._config.info_blocks_pass and info_issues:
            state = QualityState.PASS_WITH_WARNINGS

        summary = GateSummary(
            critical_issue_count=len(critical_issues),
            manual_review_issue_count=0,
            warning_or_info_issue_count=len(warning_issues) + len(info_issues),
            reparse_issue_count=len(reparse_caps),
            capability_blockers=[v.name for v in capability_blockers],
            blocking_reasons=list(blocking_reasons),
            critical_false_pass=False,
        )
        return GateDecision(
            state=state,
            summary=summary,
            blocking_reasons=tuple(blocking_reasons),
        )
