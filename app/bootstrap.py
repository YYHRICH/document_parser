"""Composition root for the document parser application.

组合根是唯一允许感知"谁是谁"的地方：在这里把 infra 实现注入 domain 端口，
再组装成 app 用例。trigger 层只消费组合好的容器，不直接 new 实现。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain.ports import StoragePort
from ..domain.routing import CapabilityRegistry, ModelRouter, RoutingSettings
from ..infra.converter import LegacyOfficeConverter
from ..infra.parsers.markitdown import MarkItDownParser
from ..infra.parsers.registry import build_capabilities, build_parser_registry
from ..infra.storage import ApiStorage
from .orchestration import DocumentParsePipeline
from .use_cases import ParseDocumentUseCase, ReparseDocumentUseCase, RunQualityUseCase


@dataclass(frozen=True)
class ApplicationContainer:
    parse_document: ParseDocumentUseCase
    reparse_document: ReparseDocumentUseCase
    run_quality: RunQualityUseCase
    storage: StoragePort
    parser: DocumentParsePipeline


def build_default_pipeline(*, settings: RoutingSettings | None = None) -> DocumentParsePipeline:
    """组装默认解析编排服务（组合根：infra 适配器注入到 app 编排）。"""

    resolved_settings = settings or RoutingSettings.from_environment()
    return DocumentParsePipeline(
        router=ModelRouter(
            CapabilityRegistry(build_capabilities(resolved_settings)),
            resolved_settings,
        ),
        parsers=build_parser_registry(),
        converters=(LegacyOfficeConverter(),),
        default_parser_id=MarkItDownParser.PARSER_ID,
    )


def build_router(**overrides: Any) -> ModelRouter:
    """组装路由决策引擎（组合根：domain 不直接感知解析器实例）。"""

    settings = RoutingSettings.from_environment(**overrides)
    return ModelRouter(CapabilityRegistry(build_capabilities(settings)), settings)


def build_application(
    *,
    storage_root: Path | str = Path("outputs/api"),
    parser: DocumentParsePipeline | None = None,
    storage: StoragePort | None = None,
) -> ApplicationContainer:
    resolved_storage = storage or ApiStorage(storage_root)
    resolved_parser = parser or build_default_pipeline()
    run_quality = RunQualityUseCase()
    return ApplicationContainer(
        parse_document=ParseDocumentUseCase(resolved_parser, resolved_storage, run_quality),
        reparse_document=ReparseDocumentUseCase(resolved_parser, resolved_storage),
        run_quality=run_quality,
        storage=resolved_storage,
        parser=resolved_parser,
    )


def build_use_cases(storage_root: Path | str = Path("outputs/api")):
    """Backward-compatible tuple factory; new code should use build_application."""
    container = build_application(storage_root=storage_root)
    return (
        container.parse_document,
        container.reparse_document,
        container.run_quality,
        container.storage,
    )