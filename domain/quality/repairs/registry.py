"""修复注册表：按顺序应用白名单修复，产出 AppliedRepair 列表。

幂等保证：修复本身天然幂等（rstrip 二次无变化；分隔行对齐二次无变化），
应用顺序固定，重复运行不产生第二次修复记录。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from document_parser.domain.model.contracts import AppliedRepair

from ..ids import stable_id
from ..hashing import sha256_text
from .base import RepairOutcome, RepairRule
from .whitelist import (
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
    affected_block_ids_by_rule: Mapping[str, list[str]] | None = None,
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
                f"repair|{document_key}|{rule.rule_id}|{sha256_text(outcome.before)}"
            )
            block_ids = (affected_block_ids_by_rule or {}).get(rule.rule_id, [])
            if block_ids:
                outcome = RepairOutcome(
                    before=outcome.before,
                    after=outcome.after,
                    description=outcome.description,
                    affected_block_ids=list(block_ids),
                    evidence_refs=outcome.evidence_refs,
                    parameters=outcome.parameters,
                )
            applied.append(outcome.to_applied_repair(repair_id, rule.rule_id))
    return RepairResult(markdown=current, applied=tuple(applied))


def replay_repair(markdown: str, applied_repair: AppliedRepair, *, rules: tuple[type[RepairRule], ...] = WHITELIST_REPAIRS) -> str:
    """按 AppliedRepair 的 rule_id 重放一次；结果必须与记录 after 一致。"""
    rule_type = next((r for r in rules if r.rule_id == applied_repair.rule_id), None)
    if rule_type is None:
        raise ValueError(f"unknown repair rule: {applied_repair.rule_id}")
    outcome = rule_type().replay(markdown, applied_repair.evidence.get("parameters", {}))
    expected = applied_repair.evidence.get("after")
    if expected is not None and outcome.after != expected:
        raise ValueError("replayed repair does not match recorded after")
    return outcome.after


def rollback_repair(markdown: str, applied_repair: AppliedRepair) -> str:
    """按记录的 before/after 安全回滚一次修复。"""
    before = applied_repair.evidence.get("before")
    after = applied_repair.evidence.get("after")
    if not isinstance(before, str) or not isinstance(after, str) or markdown != after:
        raise ValueError("rollback source does not match recorded repair")
    return before
