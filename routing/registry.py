"""Parser capability snapshot used by routing.

The registry deliberately stores only the public :class:`ParserCapability`
contract.  Parser construction and environment probing belong to the composition
root, so this module can be used without importing parser implementations.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..core.contracts import ParserCapability
from .errors import UnknownParserError


class CapabilityRegistry:
    """Immutable-at-the-boundary mapping from parser ID to capability metadata."""

    def __init__(self, capabilities: Iterable[ParserCapability]) -> None:
        self._capabilities: dict[str, ParserCapability] = {}
        for capability in capabilities:
            parser_id = capability.parser_id
            if parser_id in self._capabilities:
                raise ValueError(f"Duplicate parser ID: {parser_id}")
            # Treat the injected list as a snapshot: later mutations by the
            # composition root or callers cannot change an active route plan.
            self._capabilities[parser_id] = capability.model_copy(deep=True)

    @classmethod
    def from_snapshot(
        cls,
        capabilities: Iterable[ParserCapability],
    ) -> "CapabilityRegistry":
        """Build a registry from an explicit parser capability snapshot."""

        return cls(capabilities)

    def get(self, parser_id: str) -> ParserCapability:
        try:
            capability = self._capabilities[parser_id]
        except KeyError as error:
            raise UnknownParserError(f"Unknown parser: {parser_id}") from error
        return capability.model_copy(deep=True)

    def list(self) -> list[ParserCapability]:
        """Return copies so callers cannot mutate the stored snapshot."""

        return [capability.model_copy(deep=True) for capability in self._capabilities.values()]

    def contains(self, parser_id: str) -> bool:
        return parser_id in self._capabilities
