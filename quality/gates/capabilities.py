"""Capability Matrix 汇总器（spec §7）。

能力状态由"上游证据可用性 + 规则执行结果 + 适用性"推导，不是直接复制
ParsedDocument.capabilities。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from document_parser.core.contracts import (
    CapabilityAssessment,
    QualityCapabilityState,
)

from quality.evidence.context import EvidenceContext
from quality.models_internal import CapabilityObservation

# 六项标准能力（spec §7.2）
STANDARD_CAPABILITIES = (
    "content_complete",
    "heading_tree_reliable",
    "table_grid_reliable",
    "table_field_binding_reliable",
    "provenance_reliable",
    "non_table_relation_reliable",
)

# 表格相关能力：无表格文档中不适用（D-03）
_TABLE_CAPABILITIES = {
    "table_grid_reliable",
    "table_field_binding_reliable",
}

# 严重度排序（用于合并同名观测：取最严重）
_STATE_RANK = {
    QualityCapabilityState.REJECTED: 6,
    QualityCapabilityState.REPARSE_REQUIRED: 5,
    QualityCapabilityState.MANUAL_REVIEW_REQUIRED: 4,
    QualityCapabilityState.INFERRED: 3,
    QualityCapabilityState.UNAVAILABLE: 2,
    QualityCapabilityState.VERIFIED: 1,
}


@dataclass(frozen=True)
class CapabilityVerdict:
    """能力内部判定（含适用性与是否阻塞，公共输出只投影 state+evidence）。"""

    name: str
    state: QualityCapabilityState
    applicable: bool = True
    blocking: bool = True
    evidence: dict = field(default_factory=dict)


def _merge_state(states: list[QualityCapabilityState]) -> QualityCapabilityState:
    return max(states, key=lambda s: _STATE_RANK[s])


class CapabilityMatrixBuilder:
    """从规则观测构建能力矩阵。"""

    def __init__(self, config: object | None = None) -> None:
        self._config = config

    def build(
        self,
        observations: list[CapabilityObservation],
        context: EvidenceContext,
    ) -> dict[str, CapabilityVerdict]:
        """汇总规则观测 + 未观测能力补全，返回内部判定（含 blocking）。"""
        # 1. 合并同名观测（取最严重）
        by_name: dict[str, list[QualityCapabilityState]] = {}
        for obs in observations:
            by_name.setdefault(obs.capability_name, []).append(obs.observed_state)
        merged = {
            name: _merge_state(states) for name, states in by_name.items()
        }

        verdicts: dict[str, CapabilityVerdict] = {}
        has_tables = bool(context.parsed.tables)

        for name in STANDARD_CAPABILITIES:
            if name in merged:
                verdicts[name] = CapabilityVerdict(
                    name=name,
                    state=merged[name],
                    blocking=merged[name] != QualityCapabilityState.VERIFIED,
                    evidence={"rule_observations": merged[name].value},
                )
            elif name in _TABLE_CAPABILITIES and not has_tables:
                # D-03：无表格文档 → 不适用，不阻塞
                verdicts[name] = CapabilityVerdict(
                    name=name,
                    state=QualityCapabilityState.UNAVAILABLE,
                    applicable=False,
                    blocking=False,
                    evidence={"applicability": "not_applicable", "reason": "document contains no tables"},
                )
            else:
                # 规则未实现（M1 尚无表格/标题/引用规则）：不阻塞，如实标注
                verdicts[name] = CapabilityVerdict(
                    name=name,
                    state=QualityCapabilityState.UNAVAILABLE,
                    blocking=False,
                    evidence={"reason": "rule not implemented in this milestone"},
                )

        # 2. 非标准能力（如 reading_order_reliable、kind_content_consistent）
        for name, state in merged.items():
            if name not in STANDARD_CAPABILITIES:
                verdicts[name] = CapabilityVerdict(
                    name=name,
                    state=state,
                    blocking=False,
                    evidence={"rule_observations": state.value},
                )
        return verdicts

    def to_public_assessments(
        self, verdicts: dict[str, CapabilityVerdict]
    ) -> dict[str, CapabilityAssessment]:
        """投影为公共契约的 CapabilityAssessment（state + evidence）。"""
        return {
            name: CapabilityAssessment(
                state=verdict.state,
                evidence=dict(verdict.evidence),
            )
            for name, verdict in verdicts.items()
        }
