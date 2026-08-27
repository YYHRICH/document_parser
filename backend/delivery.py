"""Business-delivery policy for verified quality packages.

A published quality package carries its own quality state, issues, repairs, and
reparse guidance. Those signals inform downstream handling; they do not block
normal delivery. Artifact and source integrity remain enforced by storage.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.contracts import QualityState
from quality.packaging.artifacts import QUALITY_PACKAGE_ARTIFACTS


QUALITY_DELIVERY_ARTIFACTS = QUALITY_PACKAGE_ARTIFACTS
_DELIVERABLE_QUALITY_STATES = frozenset(QualityState)


@dataclass(frozen=True)
class DeliveryEligibility:
    """The API outcome for one quality-state delivery decision."""

    allowed: bool
    status_code: int | None = None
    detail: str | None = None


def delivery_eligibility(quality_state: QualityState) -> DeliveryEligibility:
    """Return the business-delivery decision for one verified quality result.

    Every recognised quality state is deliverable with its quality report. This
    lets downstream systems retain uncertainty, reparse recommendations, and
    rejection signals instead of losing a verified package at a review gate.
    """

    if quality_state in _DELIVERABLE_QUALITY_STATES:
        return DeliveryEligibility(allowed=True)
    return DeliveryEligibility(
        allowed=False,
        status_code=409,
        detail="Business delivery is unavailable for an unknown quality result.",
    )
