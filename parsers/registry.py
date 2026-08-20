"""解析器注册表。"""

from __future__ import annotations

from collections.abc import Iterable

from .base import BaseParserAdapter
from .anydoc import AnyDocParser
from .docling import DoclingParser
from .markitdown import MarkItDownParser
from .mineru import MinerUParser
from .ocr import OcrParser
from ..core.contracts import ParserCapability


def build_parser_registry() -> dict[str, BaseParserAdapter]:
    """构建当前可用的解析器实例注册表。"""

    parsers: list[BaseParserAdapter] = [
        MarkItDownParser(),
        AnyDocParser(),
        DoclingParser(),
        MinerUParser(),
        OcrParser(),
    ]
    return {parser.PARSER_ID: parser for parser in parsers}


def iter_parser_capabilities(
    registry: dict[str, BaseParserAdapter] | None = None,
) -> Iterable[ParserCapability]:
    """按注册顺序遍历解析器能力。"""

    parser_registry = registry or build_parser_registry()
    return (parser.capability for parser in parser_registry.values())


def get_parser(
    parser_id: str,
    registry: dict[str, BaseParserAdapter] | None = None,
) -> BaseParserAdapter:
    """按 parser_id 获取解析器实例。"""

    parser_registry = registry or build_parser_registry()
    try:
        return parser_registry[parser_id]
    except KeyError as error:
        raise KeyError(f"未注册解析器：{parser_id}") from error
