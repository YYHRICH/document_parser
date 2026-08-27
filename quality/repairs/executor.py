"""Exact-target executor for deterministic repair proposals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from quality.contracts import AppliedRepair
from quality.ids import stable_id
from quality.models_internal import RepairProposal
from quality.packaging.hashing import sha256_text
from quality.repairs.base import RepairOutcome, RepairRule
from quality.repairs.policy import RepairPolicyDecision


class RepairExecutionStatus(StrEnum):
    APPLIED = "applied"
    REJECTED_POLICY = "rejected_policy"
    REJECTED_PRECONDITION = "rejected_precondition"
    REJECTED_EXECUTION = "rejected_execution"


@dataclass(frozen=True)
class RepairExecution:
    proposal: RepairProposal
    decision: RepairPolicyDecision
    status: RepairExecutionStatus
    before: str
    after: str
    applied_repair: AppliedRepair | None = None
    reason: str | None = None

    @property
    def applied(self) -> bool:
        return self.status == RepairExecutionStatus.APPLIED


def _target_payload(proposal: RepairProposal) -> dict[str, object]:
    if proposal.target is None:
        return {}
    return {
        "object_type": proposal.target.object_type,
        "object_id": proposal.target.object_id,
        "field_path": proposal.target.field_path,
        "occurrence": proposal.target.occurrence,
        "stable_key": proposal.target.stable_key,
    }


class RepairExecutor:
    """Execute one proposal only after its target content hash matches."""

    def execute(
        self,
        content: str,
        *,
        proposal: RepairProposal,
        decision: RepairPolicyDecision,
        document_key: str,
        rules: Iterable[type[RepairRule]],
    ) -> RepairExecution:
        if not decision.permits_execution:
            return RepairExecution(
                proposal=proposal,
                decision=decision,
                status=RepairExecutionStatus.REJECTED_POLICY,
                before=content,
                after=content,
                reason=decision.reason,
            )
        expected_hash = proposal.expected_content_sha256
        actual_hash = sha256_text(content)
        if expected_hash != actual_hash:
            return RepairExecution(
                proposal=proposal,
                decision=decision,
                status=RepairExecutionStatus.REJECTED_PRECONDITION,
                before=content,
                after=content,
                reason="target content SHA-256 does not match proposal precondition",
            )
        rule_type = next((item for item in rules if item.rule_id == proposal.rule_id), None)
        if rule_type is None:
            return RepairExecution(
                proposal=proposal,
                decision=decision,
                status=RepairExecutionStatus.REJECTED_EXECUTION,
                before=content,
                after=content,
                reason="no registered executor for proposal rule_id",
            )
        try:
            outcome = rule_type().replay(content, proposal.parameters)
        except Exception as error:
            return RepairExecution(
                proposal=proposal,
                decision=decision,
                status=RepairExecutionStatus.REJECTED_EXECUTION,
                before=content,
                after=content,
                reason=f"executor raised {type(error).__name__}",
            )
        if outcome.before != content or not outcome.applied:
            return RepairExecution(
                proposal=proposal,
                decision=decision,
                status=RepairExecutionStatus.REJECTED_EXECUTION,
                before=content,
                after=content,
                reason="replayed transformation did not apply to the exact target",
            )
        if proposal.expected_after_sha256 != sha256_text(outcome.after):
            return RepairExecution(
                proposal=proposal,
                decision=decision,
                status=RepairExecutionStatus.REJECTED_EXECUTION,
                before=content,
                after=content,
                reason="replayed transformation output differs from proposed output hash",
            )

        audited_outcome = RepairOutcome(
            before=outcome.before,
            after=outcome.after,
            description=proposal.description,
            affected_block_ids=list(proposal.affected_block_ids),
            evidence_refs=list(proposal.evidence_refs),
            parameters=dict(proposal.parameters),
        )
        target_key = proposal.target.stable_key if proposal.target is not None else "unknown"
        repair_id = stable_id(
            f"repair|{document_key}|{proposal.rule_id}|{target_key}|{sha256_text(content)}"
        )
        applied = audited_outcome.to_applied_repair(repair_id, proposal.rule_id)
        evidence = {
            **applied.evidence,
            "target": _target_payload(proposal),
            "precondition": {
                "content_sha256": proposal.expected_content_sha256,
                "expected_after_sha256": proposal.expected_after_sha256,
            },
            "policy": {
                "action": decision.action.value,
                "reason": decision.reason,
            },
        }
        return RepairExecution(
            proposal=proposal,
            decision=decision,
            status=RepairExecutionStatus.APPLIED,
            before=content,
            after=outcome.after,
            applied_repair=applied.model_copy(update={"evidence": evidence}),
        )
