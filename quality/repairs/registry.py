"""修复注册表：按顺序应用白名单修复，产出 AppliedRepair 列表。

幂等保证：修复本身天然幂等（rstrip 二次无变化；分隔行对齐二次无变化），
应用顺序固定，重复运行不产生第二次修复记录。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from document_parser.core.contracts import AppliedRepair

from quality.ids import stable_id
from quality.repairs.base import RepairRule
from quality.repairs.whitelist import (
    QL_RPR_001_TrailingWhitespace,
    QL_RPR_002_TableSeparator,
)

# MVP 白名单修复（顺序固定）
WHITELIST_REPAIRS: tuple[type[RepairRule], ...] = (
    QL_RPR_001_TrailingWhitespace,
    QL_RPR_002_TableSeparator,
)


@dataclass(frozen=True)
class RepairResult:
    """修复应用结果。"""

    markdown: str
    applied: tuple[AppliedRepair, ...] = field(default_factory=tuple)


def apply_repairs(
    markdown: str,
    *,
    document_key: str,
    rules: tuple[type[RepairRule], ...] = WHITELIST_REPAIRS,
) -> RepairResult:
    """按注册顺序应用全部白名单修复。

    只有实际产生变化的修复才记录（no-op 不计入 applied_repairs）。
    """
    current = markdown
    applied: list[AppliedRepair] = []
    for rule_type in rules:
        rule = rule_type()
        outcome = rule.apply(current)
        if outcome.applied:
            current = outcome.after
            repair_id = stable_id(
                f"repair|{document_key}|{rule.rule_id}|{outcome.before[:64]}"
            )
            applied.append(outcome.to_applied_repair(repair_id, rule.rule_id))
    return RepairResult(markdown=current, applied=tuple(applied))
