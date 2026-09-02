"""Gate 决策器：质量层唯一的最终状态判定者（spec §8）。

优先级：rejected > reparse_required > pass_with_warnings > pass

规则模块只产观测，不得自行指定最终状态。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from document_parser.domain.model.contracts import (
    GateSummary,
    IssueSeverity,
    IssueStatus,
    QualityCapabilityState,
    QualityState,
    ReparseRecommendation,
)

from ..config import GateConfig
from .capabilities import CapabilityVerdict
from ..models_internal import IssueDraft


_INFO_STATE_TRANSITIONS = {
    QualityState.PASS: QualityState.PASS_WITH_WARNINGS,
    QualityState.PASS_WITH_WARNINGS: QualityState.PASS_WITH_WARNINGS,
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
            "critical_issue_min_state 必须是 reparse_required 或 rejected。"
        ) from exc
    if state not in {
        QualityState.REPARSE_REQUIRED,
        QualityState.REJECTED,
    }:
        raise ValueError(
            "critical_issue_min_state 必须是 reparse_required 或 rejected。"
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

        # 1. 能力阻塞项（只有 rejected/reparse 会阻断自动交付）
        capability_blockers = [
            verdict
            for verdict in capability_verdicts.values()
            if verdict.blocking
            and verdict.state
            in {
                QualityCapabilityState.REJECTED,
                QualityCapabilityState.REPARSE_REQUIRED,
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
        uncertain_caps = [
            v
            for v in capability_verdicts.values()
            if v.state
            in {
                QualityCapabilityState.INFERRED,
                QualityCapabilityState.MANUAL_REVIEW_REQUIRED,
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
                # 没有可执行的自动重解析建议时直接拒绝，不产生人工队列。
                blocking_reasons.append("reparse required but no valid recommendation")
                state = QualityState.REJECTED
        elif warning_issues or uncertain_caps:
            blocking_reasons.extend(f"warning issue: {i.message}" for i in warning_issues)
            blocking_reasons.extend(
                f"capability {v.name} = inferred" for v in uncertain_caps
            )
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

        reparse_issue_count = len(reparse_caps)
        if state == QualityState.REPARSE_REQUIRED and critical_requires_reparse:
            reparse_issue_count += len(critical_issues)

        summary = GateSummary(
            critical_issue_count=len(critical_issues),
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
