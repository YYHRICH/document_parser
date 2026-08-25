"""证据可用性判定：EvidenceRequirement -> 实际可用状态。

规则调度器用 ``check_requirements`` 决定：
- 执行规则；
- 以有限证据执行并限制最高状态；
- 跳过规则并输出 unavailable；
- 判定不适用（如无表格文档的 table 能力，D-03）。
"""

from __future__ import annotations

from dataclasses import dataclass

from document_parser.domain.model.contracts import EvidenceAvailability

from .requirements import EvidenceKind, EvidenceRequirement

# EvidenceKind -> ParsedDocument.capabilities 的键（None=必填结构，无对应声明）
CAPABILITY_MAP: dict[EvidenceKind, str | None] = {
    "blocks": None,
    "block_anchor": "page_bbox",
    "block_order": "page_bbox",
    "heading_level": None,
    "tables": None,
    "table_cells": "table_cells",
    "table_bbox": "page_bbox",
    "ocr_spans": "ocr_confidence",
    "assets": None,
    "native_artifacts": None,
    "capabilities": None,
    "provenance": None,
}

# 依赖"文档中存在表格"才适用的证据
_TABLE_SCOPED = {"table_cells", "table_bbox"}


@dataclass(frozen=True)
class RequirementCheck:
    """一条证据需求的判定结果。"""

    requirement: EvidenceRequirement
    state: EvidenceAvailability
    applicable: bool
    reason: str | None = None

    @property
    def allowed(self) -> bool:
        """是否允许规则完整执行。"""
        return self.applicable and self.state == EvidenceAvailability.AVAILABLE

    @property
    def limited(self) -> bool:
        """是否允许有限执行（仅当需求允许 partial）。"""
        return (
            self.applicable
            and self.state == EvidenceAvailability.PARTIAL
            and self.requirement.required_state == "partial_allowed"
        )

    @property
    def blocked(self) -> bool:
        """是否必须跳过（证据缺失且不允许 partial，或能力 failed）。"""
        return self.applicable and not self.allowed and not self.limited

    @property
    def not_applicable(self) -> bool:
        """文档不含该能力对应的内容（D-03：不适用不阻塞）。"""
        return not self.applicable


class AvailabilityResolver:
    """把 EvidenceRequirement 与 ParsedDocument.capabilities 结合判定。"""

    def __init__(
        self,
        capabilities: dict[str, object] | None,
        table_count: int,
    ) -> None:
        # capabilities: {name: EvidenceCapability}，可能为空 dict
        self._capabilities = capabilities or {}
        self._table_count = table_count

    def check(self, requirement: EvidenceRequirement) -> RequirementCheck:
        """判定单条需求的可用性。"""
        # 适用性：表格类证据在无表格文档中不适用
        if requirement.kind in _TABLE_SCOPED and self._table_count == 0:
            return RequirementCheck(
                requirement=requirement,
                state=EvidenceAvailability.UNAVAILABLE,
                applicable=False,
                reason="文档不包含表格（D-03：不适用）。",
            )

        capability_name = CAPABILITY_MAP.get(requirement.kind)
        if capability_name is None:
            # 必填结构（blocks 等）：以对象是否存在判断
            return RequirementCheck(
                requirement=requirement,
                state=EvidenceAvailability.AVAILABLE,
                applicable=True,
            )

        capability = self._capabilities.get(capability_name)
        if capability is None:
            return RequirementCheck(
                requirement=requirement,
                state=EvidenceAvailability.UNAVAILABLE,
                applicable=True,
                reason=f"capabilities 未声明 {capability_name}。",
            )
        state = getattr(capability, "state", None)
        reason = getattr(capability, "reason", None)
        if state is None:
            return RequirementCheck(
                requirement=requirement,
                state=EvidenceAvailability.UNAVAILABLE,
                applicable=True,
                reason=f"{capability_name} 缺少 state。",
            )
        return RequirementCheck(
            requirement=requirement,
            state=state,
            applicable=True,
            reason=reason,
        )

    def check_all(self, requirements: tuple[EvidenceRequirement, ...]) -> tuple[RequirementCheck, ...]:
        return tuple(self.check(req) for req in requirements)

    def summary(self, requirements: tuple[EvidenceRequirement, ...]) -> tuple[str, str]:
        """返回 (执行模式, 原因)。mode 取值：allowed / limited / blocked / not_applicable。

        blocked 模式需要规则跳过并输出 unavailable；limited 限制最高状态。
        """
        checks = self.check_all(requirements)
        if any(c.not_applicable for c in checks):
            if all(c.not_applicable for c in checks):
                return "not_applicable", "全部证据不适用。"
        blocked = [c for c in checks if c.blocked]
        if blocked:
            reasons = "; ".join(
                f"{c.requirement.kind}={c.state}({c.reason or 'no reason'})"
                for c in blocked
            )
            return "blocked", reasons
        limited = [c for c in checks if c.limited]
        if limited:
            reasons = "; ".join(f"{c.requirement.kind}={c.state}" for c in limited)
            return "limited", reasons
        return "allowed", ""
