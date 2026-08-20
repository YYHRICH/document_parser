"""统一文档解析门面；业务代码不直接依赖具体解析器实现。"""

from __future__ import annotations

import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import FallbackAttempt, ParsedDocument, ParseRequest, ParserCapability, RoutingDecision
from .converter import DocumentConverter, LegacyOfficeConverter
from .inspector import SimpleSourceInspector
from ..routing import ModelRouter
from ..parsers.markitdown import MarkItDownParser
from ..parsers.registry import build_parser_registry, get_parser, iter_parser_capabilities


@dataclass(frozen=True)
class GatewayParseResult:
    """Parsed document plus package-only native sidecar bytes."""

    document: ParsedDocument
    native_files: dict[str, bytes]


class DocumentParserGateway:
    """知识中心统一文档解析入口。"""

    PARSER_ID = MarkItDownParser.PARSER_ID

    def __init__(
        self,
        parser: MarkItDownParser | None = None,
        converters: tuple[DocumentConverter, ...] | None = None,
        router: ModelRouter | None = None,
    ) -> None:
        # 解析器和格式转换器都可注入；业务入口不依赖任何具体实现类。
        self._adapters = build_parser_registry()
        if parser is not None:
            self._adapters[self.PARSER_ID] = parser
        self._parser = self._adapters[self.PARSER_ID]
        self._converters = converters or (LegacyOfficeConverter(),)
        self._inspector = SimpleSourceInspector()
        self._router = router or ModelRouter.from_environment()

    @classmethod
    def from_environment(cls) -> "DocumentParserGateway":
        """保留统一构造方式，后续升级解析器时编排层无需修改。"""

        return cls()

    def list_parsers(self) -> list[ParserCapability]:
        """返回当前注册的解析能力，供健康检查和 OpenAPI 使用。"""

        converted_formats = {
            extension
            for converter in self._converters
            for extension in converter.source_formats
        }
        capabilities = list(iter_parser_capabilities(self._adapters))
        return [
            capability.model_copy(
                update={"formats": capability.formats | converted_formats}
            )
            if capability.parser_id == self.PARSER_ID
            else capability
            for capability in capabilities
        ]

    def parse(self, request: ParseRequest) -> ParsedDocument:
        """根据请求选择解析器，再做必要的格式转换和恢复。"""

        return self.parse_for_package(request).document

    def parse_for_package(self, request: ParseRequest) -> GatewayParseResult:
        """Parse once and keep native sidecars for document package materialization."""

        original_signals = self._inspector.inspect(request)
        use_router = request.parser_id is None
        routing_decision = (
            self._router.route_request(request)
            if self._router and use_router
            else None
        )
        if routing_decision is not None:
            return self._parse_auto_route(request, original_signals, routing_decision)

        return self._parse_with_parser(request, original_signals, routing_decision=None)

    def _parse_auto_route(
        self,
        request: ParseRequest,
        original_signals: Any,
        routing_decision: RoutingDecision,
    ) -> GatewayParseResult:
        candidate_parser_ids = [
            routing_decision.selected_parser_id,
            *routing_decision.fallback_parser_ids,
        ]
        attempts: list[FallbackAttempt] = []
        original_selected_parser_id = routing_decision.selected_parser_id
        last_result: GatewayParseResult | None = None

        for index, parser_id in enumerate(candidate_parser_ids):
            candidate_decision = routing_decision.model_copy(
                update={
                    "selected_parser_id": parser_id,
                    "fallback_parser_ids": candidate_parser_ids[index + 1 :],
                    "allow_automatic_fallback": bool(candidate_parser_ids[index + 1 :]),
                    "parser_options": self._parser_options_for_routed_candidate(
                        routing_decision,
                        parser_id,
                    ),
                }
            )
            effective_request = request.model_copy(
                update={
                    "parser_id": parser_id,
                    "options": {
                        **request.options,
                        **candidate_decision.parser_options,
                        "_routing_decision": candidate_decision.model_dump(mode="json"),
                    },
                }
            )
            started = time.perf_counter()
            try:
                result = self._parse_with_parser(
                    effective_request,
                    original_signals,
                    routing_decision=candidate_decision,
                )
            except Exception as error:
                attempts.append(
                    FallbackAttempt(
                        parser_id=parser_id,
                        status="failed",
                        reason=str(error),
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                )
                continue

            if self._is_fallback_needed(result.document):
                last_result = result
                attempts.append(
                    FallbackAttempt(
                        parser_id=parser_id,
                        status="failed",
                        reason=self._fallback_reason(result.document),
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                )
                continue

            return self._with_fallback_history(
                result,
                attempts=attempts,
                original_selected_parser_id=original_selected_parser_id,
            )

        if last_result is not None:
            return self._with_fallback_history(
                last_result,
                attempts=attempts,
                original_selected_parser_id=original_selected_parser_id,
            )
        raise ValueError("No routed parser produced a usable result.")

    def _parse_with_parser(
        self,
        effective_request: ParseRequest,
        original_signals: Any,
        *,
        routing_decision: RoutingDecision | None,
    ) -> GatewayParseResult:
        parser = self._select_parser(effective_request.parser_id)
        if parser.PARSER_ID != self.PARSER_ID:
            if hasattr(parser, "normalize"):
                bundle = parser.normalize(effective_request, original_signals)
                return GatewayParseResult(
                    document=self._attach_routing_metadata(
                        bundle.to_parsed_document(),
                        request=effective_request,
                        routing_decision=routing_decision,
                    ),
                    native_files=bundle.native_files,
                )
            return GatewayParseResult(
                document=self._attach_routing_metadata(
                    parser.parse(effective_request, original_signals),
                    request=effective_request,
                    routing_decision=routing_decision,
                ),
                native_files={},
            )
        if original_signals.extension in self._parser.capability.formats:
            return GatewayParseResult(
                document=self._attach_routing_metadata(
                    self._parser.parse(effective_request, original_signals),
                    request=effective_request,
                    routing_decision=routing_decision,
                ),
                native_files={},
            )

        converter = next(
            (
                item
                for item in self._converters
                if original_signals.extension in item.source_formats
            ),
            None,
        )
        if converter is None:
            raise ValueError(f"当前不支持文件格式：{original_signals.extension}")

        # core 转换层只改变交给解析器的内容和扩展名；最终协议仍描述原始文件。
        converted = converter.convert(effective_request.content, original_signals.extension)
        converted_filename = str(
            Path(effective_request.filename).with_suffix(converted.extension)
        )
        converted_request = effective_request.model_copy(
            update={
                "filename": converted_filename,
                "file_type": mimetypes.guess_type(converted_filename)[0]
                or "application/octet-stream",
                "content": converted.content,
            }
        )
        parsed = self._parser.parse(
            converted_request,
            self._inspector.inspect(converted_request),
        )

        # 分项耗时写入 provenance；parse_duration_ms 始终表示完整解析总耗时。
        parameters = {
            **parsed.provenance.parameters,
            "input_extension": original_signals.extension,
            "converted_extension": converted.extension,
            "format_converter": converted.converter_id,
        }
        provenance = parsed.provenance.model_copy(
            update={
                "parameters": parameters,
                "format_conversion_duration_ms": converted.duration_ms,
                "parse_duration_ms": (
                    converted.duration_ms
                    + parsed.provenance.markitdown_duration_ms
                ),
            }
        )
        return GatewayParseResult(
            document=self._attach_routing_metadata(
                parsed.model_copy(
                    update={
                        "filename": effective_request.filename,
                        "file_type": effective_request.file_type,
                        "provenance": provenance,
                    }
                ),
                request=effective_request,
                routing_decision=routing_decision,
            ),
            native_files={},
        )

    def parse_file(
        self,
        path: Path,
        *,
        filename: str | None = None,
        file_type: str = "application/octet-stream",
        parser_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> ParsedDocument:
        """面向编排层的文件快捷入口；原始协议仍由 ParseRequest 承载。"""
        # 文件读取集中在门面层，底层解析器始终只处理内存字节协议。
        return self.parse(
            ParseRequest(
                filename=filename or path.name,
                file_type=file_type,
                content=path.read_bytes(),
                parser_id=parser_id or self.PARSER_ID,
                options=options or {},
            )
        )

    def close(self) -> None:
        """MarkItDown 当前无持久资源；保留生命周期接口供以后升级。"""

    def _parser_options_for_routed_candidate(
        self,
        routing_decision: RoutingDecision,
        parser_id: str,
    ) -> dict[str, Any]:
        if parser_id == routing_decision.selected_parser_id:
            return routing_decision.parser_options
        if self._router is None or not hasattr(self._router, "route"):
            return {
                "route_profile": routing_decision.parser_options.get("route_profile"),
                "allow_cloud": routing_decision.parser_options.get("allow_cloud"),
            }
        decision = self._router.route(
            routing_decision.signals,
            requested_parser_id=parser_id,
            profile=routing_decision.parser_options.get("route_profile"),
            allow_cloud=routing_decision.parser_options.get("allow_cloud"),
            libreoffice_available=routing_decision.parser_options.get("libreoffice_available"),
        )
        return decision.parser_options

    def _is_fallback_needed(self, document: ParsedDocument) -> bool:
        if document.markdown.strip() or document.blocks or document.tables or document.ocr_spans:
            return False
        if document.native_artifacts:
            return False
        return document.routing_decision is not None and document.routing_decision.allow_automatic_fallback

    def _fallback_reason(self, document: ParsedDocument) -> str:
        warning = next(
            (
                item
                for item in document.warnings
                if "failed" in item.lower()
                or "尚未接入" in item
                or "placeholder" in item.lower()
                or "未提供" in item
            ),
            None,
        )
        return warning or "Parser returned no normalized content or native artifacts."

    def _with_fallback_history(
        self,
        result: GatewayParseResult,
        *,
        attempts: list[FallbackAttempt],
        original_selected_parser_id: str,
    ) -> GatewayParseResult:
        if not attempts:
            return result
        document = result.document
        provenance = document.provenance.model_copy(
            update={
                "fallback_history": [
                    *attempts,
                    *document.provenance.fallback_history,
                ],
                "parameters": {
                    **document.provenance.parameters,
                    "routing_initial_parser_id": original_selected_parser_id,
                },
            }
        )
        warnings = [
            *document.warnings,
            (
                "Automatic fallback executed: "
                + " -> ".join(
                    [attempt.parser_id for attempt in attempts]
                    + [document.provenance.parser_id]
                )
            ),
        ]
        return GatewayParseResult(
            document=document.model_copy(
                update={
                    "provenance": provenance,
                    "warnings": warnings,
                }
            ),
            native_files=result.native_files,
        )

    def _attach_routing_metadata(
        self,
        document: ParsedDocument,
        *,
        request: ParseRequest,
        routing_decision: Any,
    ) -> ParsedDocument:
        if routing_decision is None:
            return document
        provenance = document.provenance.model_copy(
            update={
                "requested_parser_id": routing_decision.requested_parser_id,
                "routing_mode": routing_decision.mode,
                "parameters": {
                    **document.provenance.parameters,
                    **{
                        key: value
                        for key, value in request.options.items()
                        if key
                        not in {
                            "_routing_decision",
                            "api_token",
                            "authorization",
                            "bearer_token",
                            "mineru_api_token",
                        }
                    },
                },
            }
        )
        return document.model_copy(
            update={
                "routing_decision": routing_decision,
                "provenance": provenance,
            }
        )

    def _select_parser(self, parser_id: str | None) -> Any:
        """按 parser_id 选择当前注册解析器。"""

        selected_id = parser_id or self.PARSER_ID
        try:
            return get_parser(selected_id, self._adapters)
        except KeyError as error:
            raise ValueError(f"当前不支持解析器：{selected_id}") from error
