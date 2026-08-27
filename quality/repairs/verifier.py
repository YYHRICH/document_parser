"""Post-execution verification for deterministic repair proposals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from quality.contracts import AppliedRepair
from quality.repairs.base import RepairRule
from quality.repairs.executor import RepairExecution


@dataclass(frozen=True)
class RepairVerification:
    execution: RepairExecution
    verified: bool
    reason: str
    applied_repair: AppliedRepair | None = None


class RepairVerifier:
    """Re-run the affected repair rule and accept only an idempotent result."""

    def verify(
        self,
        execution: RepairExecution,
        *,
        rules: Iterable[type[RepairRule]],
    ) -> RepairVerification:
        if not execution.applied or execution.applied_repair is None:
            return RepairVerification(
                execution=execution,
                verified=False,
                reason=execution.reason or "proposal was not executed",
            )
        rule_type = next(
            (item for item in rules if item.rule_id == execution.proposal.rule_id),
            None,
        )
        if rule_type is None:
            return RepairVerification(
                execution=execution,
                verified=False,
                reason="no registered verifier for proposal rule_id",
            )
        try:
            rerun = rule_type().replay(
                execution.after,
                execution.proposal.parameters,
            )
        except Exception as error:
            return RepairVerification(
                execution=execution,
                verified=False,
                reason=f"verifier raised {type(error).__name__}",
            )
        if rerun.applied:
            return RepairVerification(
                execution=execution,
                verified=False,
                reason="affected rule still changes content after execution",
            )
        evidence = {
            **execution.applied_repair.evidence,
            "verification": {
                "status": "verified",
                "method": "rerun_repair_rule_noop",
                "rule_id": execution.proposal.rule_id,
            },
        }
        return RepairVerification(
            execution=execution,
            verified=True,
            reason="affected repair rule reran as a no-op",
            applied_repair=execution.applied_repair.model_copy(
                update={"evidence": evidence}
            ),
        )
