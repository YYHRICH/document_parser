"""Capability Matrix 汇总器（spec §7）。

能力状态由"上游证据可用性 + 规则执行结果 + 适用性"推导，不是直接复制
ParsedDocument.capabilities。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quality.contracts import (
    CapabilityAssessment,
    QualityCapabilityState,
)

from quality.evidence.context import EvidenceContext
from quality.models_internal import CapabilityObservation, EvidenceRef

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
    evidence_refs: tuple[EvidenceRef, ...] = ()


def _merge_state(states: list[QualityCapabilityState]) -> QualityCapabilityState:
    return max(states, key=lambda s: _STATE_RANK[s])


def _merge_observations(
    observations: list[CapabilityObservation],
) -> tuple[QualityCapabilityState, tuple[EvidenceRef, ...]]:
    """合并状态和证据，并以稳定顺序去重证据引用。"""
    state = _merge_state([obs.observed_state for obs in observations])
    refs: dict[tuple[str, str, str, str | None], EvidenceRef] = {}
    for observation in observations:
        for ref in observation.evidence_refs:
            key = (ref.object_type, ref.object_id, ref.field_path, ref.value_sha256)
            refs[key] = ref
    return state, tuple(
        refs[key]
        for key in sorted(refs, key=lambda item: (*item[:3], item[3] or ""))
    )


def _evidence_payload(refs: tuple[EvidenceRef, ...]) -> dict:
    return {
        "evidence_refs": [
            {
                "object_type": ref.object_type,
                "object_id": ref.object_id,
                "field_path": ref.field_path,
                "value_sha256": ref.value_sha256,
            }
            for ref in refs
        ]
    }


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
        by_name: dict[str, list[CapabilityObservation]] = {}
        for obs in observations:
            by_name.setdefault(obs.capability_name, []).append(obs)
        merged = {
            name: _merge_observations(items) for name, items in by_name.items()
        }

        verdicts: dict[str, CapabilityVerdict] = {}
        has_tables = bool(context.parsed.tables)

        for name in STANDARD_CAPABILITIES:
            if name in merged:
                observed_state, evidence_refs = merged[name]
                state = observed_state
                evidence = {
                    "rule_observations": observed_state.value,
                    **_evidence_payload(evidence_refs),
                }
                if state == QualityCapabilityState.VERIFIED and not evidence_refs:
                    state = QualityCapabilityState.INFERRED
                    evidence["downgrade_reason"] = (
                        "verified capability requires at least one evidence_ref"
                    )
                verdicts[name] = CapabilityVerdict(
                    name=name,
                    state=state,
                    # inferred means a deterministic, evidence-backed fallback
                    # was used. It remains visible in the matrix but is not an
                    # automatic human-review blocker; only unresolved ambiguity
                    # (manual/reparse/rejected) blocks the Gate.
                    blocking=state in {
                        QualityCapabilityState.MANUAL_REVIEW_REQUIRED,
                        QualityCapabilityState.REPARSE_REQUIRED,
                        QualityCapabilityState.REJECTED,
                    },
                    evidence=evidence,
                    evidence_refs=evidence_refs,
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
        for name, (observed_state, evidence_refs) in merged.items():
            if name not in STANDARD_CAPABILITIES:
                state = observed_state
                evidence = {
                    "rule_observations": observed_state.value,
                    **_evidence_payload(evidence_refs),
                }
                if state == QualityCapabilityState.VERIFIED and not evidence_refs:
                    state = QualityCapabilityState.INFERRED
                    evidence["downgrade_reason"] = (
                        "verified capability requires at least one evidence_ref"
                    )
                verdicts[name] = CapabilityVerdict(
                    name=name,
                    state=state,
                    # Non-standard observations are diagnostic only. As above,
                    # inferred is not synonymous with manual review.
                    blocking=state in {
                        QualityCapabilityState.MANUAL_REVIEW_REQUIRED,
                        QualityCapabilityState.REPARSE_REQUIRED,
                        QualityCapabilityState.REJECTED,
                    },
                    evidence=evidence,
                    evidence_refs=evidence_refs,
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
