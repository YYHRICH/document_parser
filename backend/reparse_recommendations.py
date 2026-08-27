"""Safe delivery projections for deterministic reparse recommendations.

The recommendation domain can retain richer diagnostic and policy objects.  This
adapter intentionally exposes only the small, content-free fields required for a
read-only API.  It never serializes automatic option values, candidate reasons,
or capability-provided diagnostic text.
"""

from __future__ import annotations

import re

from ..routing.recommendations import (
    ReparseRecommendationPolicy,
    ReparseRecommendations,
)


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def cloud_denied_reparse_policy() -> ReparseRecommendationPolicy:
    """Return the default read-only policy while no identity grant exists.

    A recommendation endpoint has no ``Principal`` or ``CloudExecutionGrant``
    input.  It must therefore deny cloud execution regardless of deployment
    settings or untrusted historical ``job.options`` values.
    """

    return ReparseRecommendationPolicy(allow_cloud=False)


def public_reparse_recommendations(
    recommendations: ReparseRecommendations | None,
) -> dict[str, object] | None:
    """Project recommendation facts without options, errors, paths, or content."""

    if recommendations is None:
        return None

    automatic = recommendations.automatic
    return {
        "signals": [
            {
                "source": signal.source.value,
                "code": _safe_identifier(signal.code),
                "retryable": signal.retryable,
            }
            for signal in recommendations.signals
        ],
        "candidates": [
            {
                "parser_id": _safe_identifier(candidate.parser_id),
                "executable": candidate.executable,
                "replaces_current_parser": candidate.replaces_current_parser,
                "requires_cloud": candidate.requires_cloud,
            }
            for candidate in recommendations.candidates
        ],
        "automatic": (
            {
                "parser_id": _safe_identifier(automatic.parser_id),
                "requires_cloud": automatic.requires_cloud,
            }
            if automatic is not None
            else None
        ),
    }


def _safe_identifier(value: str) -> str:
    normalized = value.strip()
    return normalized if _SAFE_IDENTIFIER.fullmatch(normalized) else "<redacted>"
