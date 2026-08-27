"""Compatibility facade for the P4 proposal-based repair workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from quality.contracts import AppliedRepair
from quality.repairs.base import RepairRule
from quality.repairs.workflow import REGISTERED_REPAIRS, RepairWorkflow
from quality.representations.models import RepresentationTarget

# Kept as a compatibility name for callers and focused tests.  It is a catalog,
# not an instruction to mutate content directly.
WHITELIST_REPAIRS: tuple[type[RepairRule], ...] = REGISTERED_REPAIRS


@dataclass(frozen=True)
class RepairResult:
    markdown: str
    applied: tuple[AppliedRepair, ...] = field(default_factory=tuple)


def apply_repairs(
    markdown: str,
    *,
    document_key: str,
    rules: tuple[type[RepairRule], ...] = WHITELIST_REPAIRS,
    affected_block_ids_by_rule: Mapping[str, list[str]] | None = None,
) -> RepairResult:
    """Apply deterministic repairs through proposal, policy, executor, verifier.

    This legacy API uses the document Markdown field as its exact target.  The
    pipeline uses the same workflow with real document/block representation
    targets from RepresentationInventory.
    """
    workflow = RepairWorkflow(rules=rules)
    result = workflow.run(
        markdown,
        document_key=document_key,
        target=RepresentationTarget(
            object_type="document",
            object_id=document_key,
            field_path="markdown",
        ),
        affected_block_ids_by_rule=affected_block_ids_by_rule,
    )
    return RepairResult(markdown=result.content, applied=result.applied)


def replay_repair(
    markdown: str,
    applied_repair: AppliedRepair,
    *,
    rules: tuple[type[RepairRule], ...] = WHITELIST_REPAIRS,
) -> str:
    """Replay a recorded repair and require its documented output."""
    rule_type = next((item for item in rules if item.rule_id == applied_repair.rule_id), None)
    if rule_type is None:
        raise ValueError(f"unknown repair rule: {applied_repair.rule_id}")
    outcome = rule_type().replay(markdown, applied_repair.evidence.get("parameters", {}))
    expected = applied_repair.evidence.get("after")
    if expected is not None and outcome.after != expected:
        raise ValueError("replayed repair does not match recorded after")
    return outcome.after


def rollback_repair(markdown: str, applied_repair: AppliedRepair) -> str:
    """Safely roll back only when the target equals the recorded post-state."""
    before = applied_repair.evidence.get("before")
    after = applied_repair.evidence.get("after")
    if not isinstance(before, str) or not isinstance(after, str) or markdown != after:
        raise ValueError("rollback source does not match recorded repair")
    return before
