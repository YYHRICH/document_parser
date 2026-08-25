"""解析器注册表与能力快照（infra 层：领域只消费能力数据，不反向依赖这里）。"""

from __future__ import annotations

from collections.abc import Iterable

from .base import BaseParserAdapter
from .anydoc import AnyDocParser
from .docling import DoclingParser
from .markitdown import MarkItDownParser
from .mineru import MinerUParser
from .ocr import OcrParser
from ...domain.model.contracts import ParserCapability
from ...domain.routing.config import RoutingSettings
from ...domain.routing.ids import MINERU_ID


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


def build_capabilities(settings: RoutingSettings) -> list[ParserCapability]:
    """按环境设置生成能力快照（原 CapabilityRegistry.from_settings 的组合逻辑）。

    领域路由只依赖这份快照数据；解析器实例化与可用性修正都在这里完成。
    """

    capabilities = list(iter_parser_capabilities(build_parser_registry()))
    if settings.mineru_api_token is not None:
        capabilities = [
            capability.model_copy(
                update={"available": True, "unavailable_reason": None}
            )
            if capability.parser_id == MINERU_ID
            else capability
            for capability in capabilities
        ]
    return capabilities


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
