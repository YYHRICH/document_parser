"""Composition-root registry for concrete parser plugins.

The routing package never imports this module.  It receives only the immutable
``ParserCapability`` snapshots built here by a composition root such as Gateway.
Concrete parser construction therefore remains outside routing, normalization,
quality, and storage boundaries.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from ..core.contracts import ParserCapability
from .anydoc import AnyDocParser
from .base import BaseParserAdapter
from .docling import DoclingParser
from .markitdown import MarkItDownParser
from .mineru import MinerUParser
from .ocr import OcrParser


ParserRegistry = Mapping[str, BaseParserAdapter]


def build_parser_registry() -> dict[str, BaseParserAdapter]:
    """Construct the built-in parser plugins at the composition boundary."""

    parsers: list[BaseParserAdapter] = [
        MarkItDownParser(),
        AnyDocParser(),
        DoclingParser(),
        MinerUParser(),
        OcrParser(),
    ]
    return {parser.PARSER_ID: parser for parser in parsers}


def build_capability_snapshot(
    registry: ParserRegistry | None = None,
) -> tuple[ParserCapability, ...]:
    """Copy public capabilities without exposing parser implementation objects.

    The tuple is safe to inject into ``routing.CapabilityRegistry``.  Each
    capability is copied again so later adapter state changes cannot mutate an
    already-created route plan.
    """

    parser_registry = registry if registry is not None else build_parser_registry()
    return tuple(
        parser.capability_snapshot()
        if hasattr(parser, "capability_snapshot")
        else parser.capability.model_copy(deep=True)
        for parser in parser_registry.values()
    )


def iter_parser_capabilities(
    registry: ParserRegistry | None = None,
) -> Iterable[ParserCapability]:
    """Iterate a fresh capability snapshot in parser registration order."""

    return iter(build_capability_snapshot(registry))


def get_parser(
    parser_id: str,
    registry: ParserRegistry | None = None,
) -> BaseParserAdapter:
    """Resolve an execution plugin by its stable parser ID."""

    parser_registry = registry if registry is not None else build_parser_registry()
    try:
        return parser_registry[parser_id]
    except KeyError as error:
        raise KeyError(f"Unregistered parser: {parser_id}") from error


__all__ = [
    "ParserRegistry",
    "build_capability_snapshot",
    "build_parser_registry",
    "get_parser",
    "iter_parser_capabilities",
]
