"""解析编排（app 层）：路由 → 候选解析器 → fallback → 格式转换 → 元数据补齐。

从原 ``infra/parsers/gateway.py`` 门面拆分而来：编排是应用层职责，
``infra`` 只保留解析器适配器、格式转换器和注册表（``ParserPort`` / ``ConverterPort`` 的实现）。
组合根（``app/bootstrap.py``）负责把端口实现注入本编排服务。
"""

from __future__ import annotations

import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..domain.model.contracts import (
    FallbackAttempt,
    ParsedDocument,
    ParseRequest,
    ParserCapability,
    RoutingDecision,
)
from ..domain.ports import ConverterPort, ParserOutcome, ParserPort
from ..domain.routing import ModelRouter
from ..domain.service.source_inspector import SimpleSourceInspector


@dataclass(frozen=True)
class ParseOutcome:
    """一次解析编排的结果：统一文档 + 仅写入包内的原生旁路字节。"""

    document: ParsedDocument
    native_files: dict[str, bytes]


class DocumentParsePipeline:
    """文档解析编排服务（app 层；替代原 ``DocumentParserGateway`` 门面）。

    只依赖注入的端口与领域服务：解析器注册表（``ParserPort``）、格式转换器
    （``ConverterPort``）、路由决策器（``ModelRouter``）和文件信号检查器。
    不 import 任何 ``infra`` 具体实现类，便于换实现、换入口（HTTP/CLI/MQ）复用。
    """

    def __init__(
        self,
        *,
        router: ModelRouter | None = None,
        parsers: Mapping[str, ParserPort] | None = None,
        converters: Sequence[ConverterPort] | None = None,
        inspector: SimpleSourceInspector | None = None,
        default_parser_id: str | None = None,
    ) -> None:
        self._router = router
        self.parsers: dict[str, ParserPort] = dict(parsers or {})
        self._converters = tuple(converters or ())
        self._inspector = inspector or SimpleSourceInspector()
        self._default_parser_id = default_parser_id

    def list_parsers(self) -> list[ParserCapability]:
        """返回当前注册的解析能力；默认解析器合并可转换格式。"""

        converted_formats = {
            extension
            for converter in self._converters
            for extension in converter.source_formats
        }
        return [
            capability.model_copy(update={"formats": capability.formats | converted_formats})
            if capability.parser_id == self._default_parser_id
            else capability
            for capability in (parser.capability for parser in self.parsers.values())
        ]

    def parse(self, request: ParseRequest) -> ParsedDocument:
        """便捷入口：只要统一文档，忽略包内旁路字节。"""

        return self.parse_for_package(request).document

    def parse_for_package(self, request: ParseRequest) -> ParserOutcome:
        """按请求选择解析器，做必要的格式转换与 fallback，返回文档 + 旁路字节。"""

        original_signals = self._inspector.inspect(request)
        use_router = request.parser_id is None
        routing_decision = (
            self._router.route_request(request)
            if self._router is not None and use_router
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
    ) -> ParserOutcome:
        candidate_parser_ids = [
            routing_decision.selected_parser_id,
            *routing_decision.fallback_parser_ids,
        ]
        attempts: list[FallbackAttempt] = []
        original_selected_parser_id = routing_decision.selected_parser_id
        last_result: ParserOutcome | None = None

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
    ) -> ParserOutcome:
        parser = self._select_parser(effective_request.parser_id)
        if parser.PARSER_ID != self._default_parser_id:
            normalize = getattr(parser, "normalize", None)
            if callable(normalize):
                bundle = normalize(effective_request, original_signals)
                return ParseOutcome(
                    document=self._attach_routing_metadata(
                        bundle.to_parsed_document(),
                        request=effective_request,
                        routing_decision=routing_decision,
                    ),
                    native_files=bundle.native_files,
                )
            return ParseOutcome(
                document=self._attach_routing_metadata(
                    parser.parse(effective_request, original_signals),
                    request=effective_request,
                    routing_decision=routing_decision,
                ),
                native_files={},
            )

        default_parser = self._default_parser()
        if default_parser is None:
            raise ValueError("未配置默认解析器。")
        if original_signals.extension in default_parser.capability.formats:
            return ParseOutcome(
                document=self._attach_routing_metadata(
                    default_parser.parse(effective_request, original_signals),
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

        # 转换层只改变交给解析器的内容和扩展名；最终协议仍描述原始文件。
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
        parsed = default_parser.parse(
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
        return ParseOutcome(
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
        result: ParserOutcome,
        *,
        attempts: list[FallbackAttempt],
        original_selected_parser_id: str,
    ) -> ParserOutcome:
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
        return ParseOutcome(
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

    def _select_parser(self, parser_id: str | None) -> ParserPort:
        """按 parser_id 选择当前注册解析器；未指定时回退默认解析器。"""

        selected_id = parser_id or self._default_parser_id
        parser = self.parsers.get(selected_id) if selected_id is not None else None
        if parser is None:
            raise ValueError(f"当前不支持解析器：{selected_id}")
        return parser

    def _default_parser(self) -> ParserPort | None:
        if self._default_parser_id is None:
            return None
        return self.parsers.get(self._default_parser_id)