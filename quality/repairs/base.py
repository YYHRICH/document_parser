"""白名单修复协议（spec §6）。

每个修复必须：
- 稳定 rule_id；
- 只做低风险、可证明等价的变换（禁止猜测/补造/改写事实）；
- 记录 before/after、受影响 block、结构化证据；
- 可回放、幂等（同一输入应用两次无第二次变化）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from document_parser.core.contracts import AppliedRepair

from quality.models_internal import EvidenceRef


@dataclass(frozen=True)
class RepairOutcome:
    """一次修复的结果（before/after 用于可回放证据）。"""

    before: str
    after: str
    description: str
    affected_block_ids: list[str] = field(default_factory=list)
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    parameters: dict = field(default_factory=dict)

    @property
    def applied(self) -> bool:
        """是否实际产生了变化（no-op 不算 applied repair）。"""
        return self.before != self.after

    def to_applied_repair(self, repair_id: str, rule_id: str) -> AppliedRepair:
        return AppliedRepair(
            repair_id=repair_id,
            rule_id=rule_id,
            description=self.description,
            affected_block_ids=list(self.affected_block_ids),
            replayable=True,
            evidence={
                "before": self.before,
                "after": self.after,
                "refs": [
                    {
                        "object_type": ref.object_type,
                        "object_id": ref.object_id,
                        "field_path": ref.field_path,
                        **({"value_sha256": ref.value_sha256} if ref.value_sha256 else {}),
                    }
                    for ref in self.evidence_refs
                ],
                "parameters": dict(self.parameters),
                "rollback": {"before": self.before, "after": self.after},
            },
        )


class RepairRule(ABC):
    """白名单修复规则协议。"""

    rule_id: str = ""

    @abstractmethod
    def apply(self, markdown: str) -> RepairOutcome:
        """对 markdown 应用修复；无变化时返回 before==after 的 outcome。"""
        raise NotImplementedError

    def replay(self, markdown: str, parameters: dict | None = None) -> RepairOutcome:
        """按记录的参数重放；MVP 白名单规则均为参数确定性变换。"""
        return self.apply(markdown)

    def rollback(self, markdown: str, *, before: str, after: str) -> str:
        """安全回滚：只接受当前内容等于 repair after 的情况。"""
        if markdown != after:
            raise ValueError("rollback source does not match recorded repair after")
        return before
