"""Parser capability registry for routing.

领域层只依赖能力数据；解析器实例的装配（from_settings）已移到
``infra.parsers.registry.build_capabilities``，保证 domain 不反向依赖 infra。
"""

from __future__ import annotations

from typing import Iterable

from ..model.contracts import ParserCapability
from .errors import UnknownParserError
from .ids import ANYDOC_ID, DOCLING_ID, MARKITDOWN_ID, MINERU_ID, OCR_ID


class CapabilityRegistry:
    """Stable mapping from parser ID to capability metadata."""

    def __init__(self, capabilities: Iterable[ParserCapability]) -> None:
        self._capabilities: dict[str, ParserCapability] = {}
        for capability in capabilities:
            if capability.parser_id in self._capabilities:
                raise ValueError(f"Duplicate parser ID: {capability.parser_id}")
            self._capabilities[capability.parser_id] = capability

    def get(self, parser_id: str) -> ParserCapability:
        try:
            return self._capabilities[parser_id]
        except KeyError as error:
            raise UnknownParserError(f"Unknown parser: {parser_id}") from error

    def list(self) -> list[ParserCapability]:
        return list(self._capabilities.values())

    def contains(self, parser_id: str) -> bool:
        return parser_id in self._capabilities
