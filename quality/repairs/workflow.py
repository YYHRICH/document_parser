"""Proposal -> policy -> executor -> verifier workflow for repair targets."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from quality.contracts import AppliedRepair
from quality.models_internal import EvidenceRef, RepairProposal
from quality.packaging.hashing import sha256_text
from quality.repairs.base import RepairRule
from quality.repairs.executor import RepairExecutor, RepairExecution
from quality.repairs.policy import RepairPolicy, RepairPolicyDecision
from quality.repairs.verifier import RepairVerification, RepairVerifier
from quality.repairs.whitelist import (
    QL_RPR_001_TrailingWhitespace,
    QL_RPR_002_TableSeparator,
    QL_RPR_003_HtmlTableToMarkdown,
)
from quality.representations.models import RepresentationTarget


REGISTERED_REPAIRS: tuple[type[RepairRule], ...] = (
    QL_RPR_001_TrailingWhitespace,
    QL_RPR_002_TableSeparator,
    QL_RPR_003_HtmlTableToMarkdown,
)


@dataclass(frozen=True)
class RepairAuditEntry:
    rule_id: str
    target_key: str
    policy_action: str
    execution_status: str
    verification_status: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {
            "rule_id": self.rule_id,
            "target_key": self.target_key,
            "policy_action": self.policy_action,
            "execution_status": self.execution_status,
            "verification_status": self.verification_status,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RepairWorkflowResult:
    content: str
    proposals: tuple[RepairProposal, ...] = ()
    decisions: tuple[RepairPolicyDecision, ...] = ()
    executions: tuple[RepairExecution, ...] = ()
    verifications: tuple[RepairVerification, ...] = ()
    applied: tuple[AppliedRepair, ...] = ()
    audit: tuple[RepairAuditEntry, ...] = ()


class RepairWorkflow:
    """Plans and applies deterministic repairs to exactly one representation."""

    def __init__(
        self,
        *,
        rules: tuple[type[RepairRule], ...] = REGISTERED_REPAIRS,
        policy: RepairPolicy | None = None,
        executor: RepairExecutor | None = None,
        verifier: RepairVerifier | None = None,
    ) -> None:
        self.rules = rules
        self.policy = policy or RepairPolicy()
        self.executor = executor or RepairExecutor()
        self.verifier = verifier or RepairVerifier()

    def plan(
        self,
        content: str,
        *,
        target: RepresentationTarget,
        affected_block_ids_by_rule: Mapping[str, list[str]] | None = None,
    ) -> tuple[RepairProposal, ...]:
        """Dry-run registered rules and create hash-guarded exact proposals."""
        current = content
        proposals: list[RepairProposal] = []
        for rule_type in self.rules:
            rule = rule_type()
            outcome = rule.apply(current)
            if not outcome.applied:
                continue
            before_hash = sha256_text(current)
            target_ref = target.evidence_ref(value_sha256=before_hash)
            refs = self._dedupe_refs((target_ref, *outcome.evidence_refs))
            proposals.append(
                RepairProposal(
                    rule_id=rule.rule_id,
                    description=outcome.description,
                    target=target,
                    expected_content_sha256=before_hash,
                    expected_after_sha256=sha256_text(outcome.after),
                    affected_block_ids=list(
                        (affected_block_ids_by_rule or {}).get(rule.rule_id, [])
                    ),
                    evidence_refs=list(refs),
                    parameters=dict(outcome.parameters),
                    safety="auto_safe",
                )
            )
            current = outcome.after
        return tuple(proposals)

    def run(
        self,
        content: str,
        *,
        document_key: str,
        target: RepresentationTarget,
        affected_block_ids_by_rule: Mapping[str, list[str]] | None = None,
    ) -> RepairWorkflowResult:
        proposals = self.plan(
            content,
            target=target,
            affected_block_ids_by_rule=affected_block_ids_by_rule,
        )
        return self.execute_plan(content, proposals=proposals, document_key=document_key)

    def execute_plan(
        self,
        content: str,
        *,
        proposals: Iterable[RepairProposal],
        document_key: str,
    ) -> RepairWorkflowResult:
        current = content
        proposal_items = tuple(proposals)
        decisions: list[RepairPolicyDecision] = []
        executions: list[RepairExecution] = []
        verifications: list[RepairVerification] = []
        applied: list[AppliedRepair] = []
        audit: list[RepairAuditEntry] = []
        for proposal in proposal_items:
            decision = self.policy.decide(proposal)
            execution = self.executor.execute(
                current,
                proposal=proposal,
                decision=decision,
                document_key=document_key,
                rules=self.rules,
            )
            verification = self.verifier.verify(execution, rules=self.rules)
            decisions.append(decision)
            executions.append(execution)
            verifications.append(verification)
            if verification.verified and verification.applied_repair is not None:
                current = execution.after
                applied.append(verification.applied_repair)
            target_key = proposal.target.stable_key if proposal.target else "missing-target"
            audit.append(
                RepairAuditEntry(
                    rule_id=proposal.rule_id,
                    target_key=target_key,
                    policy_action=decision.action.value,
                    execution_status=execution.status.value,
                    verification_status="verified" if verification.verified else "rejected",
                    reason=verification.reason,
                )
            )
        return RepairWorkflowResult(
            content=current,
            proposals=proposal_items,
            decisions=tuple(decisions),
            executions=tuple(executions),
            verifications=tuple(verifications),
            applied=tuple(applied),
            audit=tuple(audit),
        )

    @staticmethod
    def _dedupe_refs(refs: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
        result: list[EvidenceRef] = []
        seen: set[tuple[str, str, str, str | None]] = set()
        for ref in refs:
            key = (ref.object_type, ref.object_id, ref.field_path, ref.value_sha256)
            if key not in seen:
                seen.add(key)
                result.append(ref)
        return tuple(result)
