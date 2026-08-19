"""Parser capability registry for routing."""

from __future__ import annotations

from typing import Iterable

from ..core.contracts import ParserCapability
from ..parsers.anydoc import AnyDocParser
from ..parsers.docling import DoclingParser
from ..parsers.markitdown import MarkItDownParser
from ..parsers.mineru import MinerUParser
from ..parsers.ocr import OcrParser
from ..parsers.registry import build_parser_registry
from .config import RoutingSettings
from .errors import UnknownParserError


MARKITDOWN_ID = MarkItDownParser.PARSER_ID
ANYDOC_ID = AnyDocParser.PARSER_ID
DOCLING_ID = DoclingParser.PARSER_ID
MINERU_ID = MinerUParser.PARSER_ID
OCR_ID = OcrParser.PARSER_ID


class CapabilityRegistry:
    """Stable mapping from parser ID to capability metadata."""

    def __init__(self, capabilities: Iterable[ParserCapability]) -> None:
        self._capabilities: dict[str, ParserCapability] = {}
        for capability in capabilities:
            if capability.parser_id in self._capabilities:
                raise ValueError(f"Duplicate parser ID: {capability.parser_id}")
            self._capabilities[capability.parser_id] = capability

    @classmethod
    def from_settings(cls, settings: RoutingSettings) -> "CapabilityRegistry":
        del settings
        parsers = build_parser_registry()
        return cls(parser.capability for parser in parsers.values())

    def get(self, parser_id: str) -> ParserCapability:
        try:
            return self._capabilities[parser_id]
        except KeyError as error:
            raise UnknownParserError(f"Unknown parser: {parser_id}") from error

    def list(self) -> list[ParserCapability]:
        return list(self._capabilities.values())

    def contains(self, parser_id: str) -> bool:
        return parser_id in self._capabilities
