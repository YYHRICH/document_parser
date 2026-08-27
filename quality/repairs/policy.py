"""Policy decisions for deterministic quality repairs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from quality.models_internal import RepairProposal


class RepairPolicyAction(StrEnum):
    AUTO_SAFE = "auto_safe"
    REVIEW_REQUIRED = "review_required"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class RepairPolicyDecision:
    proposal: RepairProposal
    action: RepairPolicyAction
    reason: str

    @property
    def permits_execution(self) -> bool:
        return self.action == RepairPolicyAction.AUTO_SAFE


class RepairPolicy:
    """The only component that authorizes an automatic repair."""

    def decide(self, proposal: RepairProposal) -> RepairPolicyDecision:
        if proposal.target is None or proposal.expected_content_sha256 is None:
            return RepairPolicyDecision(
                proposal=proposal,
                action=RepairPolicyAction.FORBIDDEN,
                reason="proposal lacks an exact target or content hash precondition",
            )
        if proposal.safety == "auto_safe":
            return RepairPolicyDecision(
                proposal=proposal,
                action=RepairPolicyAction.AUTO_SAFE,
                reason="registered deterministic transformation with exact precondition",
            )
        if proposal.safety == "review_required":
            return RepairPolicyDecision(
                proposal=proposal,
                action=RepairPolicyAction.REVIEW_REQUIRED,
                reason="proposal may be useful but requires human review",
            )
        return RepairPolicyDecision(
            proposal=proposal,
            action=RepairPolicyAction.FORBIDDEN,
            reason="proposal is not permitted by deterministic repair policy",
        )
