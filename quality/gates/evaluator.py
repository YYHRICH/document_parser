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


_INFO_STATE_TRANSITIONS = {
    QualityState.PASS: QualityState.PASS_WITH_WARNINGS,
    QualityState.PASS_WITH_WARNINGS: QualityState.PASS_WITH_WARNINGS,
    QualityState.MANUAL_REVIEW_REQUIRED: QualityState.MANUAL_REVIEW_REQUIRED,
    QualityState.REPARSE_REQUIRED: QualityState.REPARSE_REQUIRED,
    QualityState.REJECTED: QualityState.REJECTED,
}


def _apply_info_policy(
    state: QualityState,
    *,
    has_info: bool,
    enabled: bool,
) -> QualityState:
    """应用 info 策略，但绝不降低已有 Gate 状态。"""
    if not enabled or not has_info:
        return state
    return _INFO_STATE_TRANSITIONS[state]


def _critical_target_state(config: GateConfig) -> QualityState:
    """读取 critical issue 的目标状态，并拒绝普通放行状态配置。"""
    try:
        state = QualityState(config.critical_issue_min_state)
    except ValueError as exc:
        raise ValueError(
            "critical_issue_min_state 必须是 manual_review_required、"
            "reparse_required 或 rejected。"
        ) from exc
    if state not in {
        QualityState.MANUAL_REVIEW_REQUIRED,
        QualityState.REPARSE_REQUIRED,
        QualityState.REJECTED,
    }:
        raise ValueError(
            "critical_issue_min_state 必须是 manual_review_required、"
            "reparse_required 或 rejected。"
        )
    return state


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
        critical_target = _critical_target_state(self._config)
        critical_requires_rejected = (
            critical_issues and critical_target == QualityState.REJECTED
        )
        critical_requires_reparse = (
            critical_issues and critical_target == QualityState.REPARSE_REQUIRED
        )
        critical_requires_manual = (
            critical_issues and critical_target == QualityState.MANUAL_REVIEW_REQUIRED
        )

        if rejected_caps or critical_requires_rejected:
            blocking_reasons.extend(
                f"capability {v.name} rejected" for v in rejected_caps
            )
            blocking_reasons.extend(
                f"critical issue: {i.message}" for i in critical_issues
            )
            state = QualityState.REJECTED
        elif reparse_caps or critical_requires_reparse:
            if reparse_recommendation is not None:
                blocking_reasons.extend(
                    f"capability {v.name} reparse_required" for v in reparse_caps
                )
                blocking_reasons.extend(
                    f"critical issue requires reparse: {i.message}"
                    for i in critical_issues
                    if critical_requires_reparse
                )
                state = QualityState.REPARSE_REQUIRED
            else:
                # 契约要求 reparse_required 必须带建议；无合法建议时
                # 不能假装 reparse：降级为人工复核
                blocking_reasons.append("reparse required but no valid recommendation")
                state = QualityState.MANUAL_REVIEW_REQUIRED
        elif manual_caps or critical_requires_manual:
            blocking_reasons.extend(
                f"capability {v.name} = {v.state.value}" for v in manual_caps
            )
            blocking_reasons.extend(
                f"critical issue requires manual review: {i.message}"
                for i in critical_issues
                if critical_requires_manual
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
        state = _apply_info_policy(
            state,
            has_info=bool(info_issues),
            enabled=self._config.info_blocks_pass,
        )

        manual_review_issue_count = len(manual_caps)
        if state == QualityState.MANUAL_REVIEW_REQUIRED:
            manual_review_issue_count += len(critical_issues)
        reparse_issue_count = len(reparse_caps)
        if state == QualityState.REPARSE_REQUIRED and critical_requires_reparse:
            reparse_issue_count += len(critical_issues)

        summary = GateSummary(
            critical_issue_count=len(critical_issues),
            manual_review_issue_count=manual_review_issue_count,
            warning_or_info_issue_count=len(warning_issues) + len(info_issues),
            reparse_issue_count=reparse_issue_count,
            capability_blockers=[v.name for v in capability_blockers],
            blocking_reasons=list(blocking_reasons),
            critical_false_pass=bool(
                critical_issues
                and state in {QualityState.PASS, QualityState.PASS_WITH_WARNINGS}
            ),
        )
        return GateDecision(
            state=state,
            summary=summary,
            blocking_reasons=tuple(blocking_reasons),
        )
