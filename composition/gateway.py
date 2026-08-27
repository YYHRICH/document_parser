"""应用组合层的统一文档解析门面。"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..core.contracts import (
    FallbackAttempt,
    ParsedDocument,
    ParseRequest,
    ParserCapability,
    RoutingMode,
)
from ..core.converter import DocumentConverter, LegacyOfficeConverter
from ..core.inspector import SimpleSourceInspector
from ..routing import CapabilityRegistry, ModelRouter
from ..parsers.markitdown import MarkItDownParser
from ..parsers.registry import build_parser_registry, get_parser, iter_parser_capabilities


@dataclass(frozen=True)
class GatewayParseResult:
    """Parsed document plus package-only native sidecar bytes."""

    document: ParsedDocument
    native_files: dict[str, bytes]


class GatewayParseError(RuntimeError):
    """All parser attempts from one routing decision failed.

    The original exceptions remain available through ``causes`` and the last
    failure is set as ``__cause__`` by the caller.  ``attempts`` is safe to
    serialize as provenance or a job error record without retaining parser
    implementation objects.
    """

    def __init__(
        self,
        *,
        attempts: list[FallbackAttempt],
        causes: list[Exception],
        routing_decision: Any,
    ) -> None:
        self.attempts = tuple(attempts)
        self.causes = tuple(causes)
        self.routing_decision = routing_decision
        detail = "; ".join(
            f"{attempt.parser_id} [{attempt.status}]: {attempt.reason}"
            for attempt in attempts
        )
        super().__init__(f"All routed parser attempts failed. {detail}")


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
        self._converters = converters or (LegacyOfficeConverter(),)
        self._inspector = SimpleSourceInspector()
        # Gateway is the composition root: it is the only layer that knows both
        # adapter instances and the routing module.  Routing receives a public
        # capability snapshot and never imports these adapters itself.
        self._router = router or ModelRouter.from_environment(
            CapabilityRegistry.from_snapshot(self._routing_capabilities())
        )

    @classmethod
    def from_environment(cls) -> "DocumentParserGateway":
        """保留统一构造方式，后续升级解析器时编排层无需修改。"""

        return cls()

    @property
    def cloud_parsers_enabled(self) -> bool:
        """Whether this server permits network-backed parsers to be selected."""

        return bool(self._router.settings.allow_cloud)

    def list_parsers(self) -> list[ParserCapability]:
        """返回当前注册的解析能力，供健康检查和 OpenAPI 使用。"""

        return self._routing_capabilities()

    def _routing_capabilities(self) -> list[ParserCapability]:
        """Collect the adapter-owned capability snapshot for a router instance."""

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
        """Execute the selected parser and an allowed automatic fallback chain.

        Routing remains a pure planner: this gateway is the composition point
        that performs the attempts.  A parser explicitly selected by a caller
        never enters this chain, so its original failure behavior is retained.
        """

        original_signals = self._inspector.inspect(request)
        routing_decision = self._router.route_request(request) if self._router else None
        if routing_decision is None:
            return self._parse_once(
                request,
                original_signals=original_signals,
                routing_decision=None,
            )

        # Explicit requests are still validated by ModelRouter, but retain the
        # historical one-attempt error behavior and never enter fallback.
        if routing_decision.mode == RoutingMode.MANUAL:
            return self._parse_once(
                self._request_for_routed_attempt(
                    request,
                    parser_id=routing_decision.selected_parser_id,
                    routing_decision=routing_decision,
                ),
                original_signals=original_signals,
                routing_decision=routing_decision,
            )

        parser_ids = [routing_decision.selected_parser_id]
        if self._allows_automatic_fallback(routing_decision):
            parser_ids.extend(routing_decision.fallback_parser_ids)

        failures: list[FallbackAttempt] = []
        causes: list[Exception] = []
        for parser_id in parser_ids:
            effective_request = self._request_for_routed_attempt(
                request,
                parser_id=parser_id,
                routing_decision=routing_decision,
            )
            started_at = datetime.now(UTC)
            started = time.perf_counter()
            parser_version = self._attempt_parser_version(parser_id)
            parameters_fingerprint = self._attempt_parameters_fingerprint(
                effective_request.options
            )
            try:
                result = self._parse_once(
                    effective_request,
                    original_signals=original_signals,
                    routing_decision=routing_decision,
                )
            except Exception as error:
                completed_at = datetime.now(UTC)
                duration_ms = int((time.perf_counter() - started) * 1000)
                failure_kind, retryable = self._failure_classification(error)
                failures.append(
                    FallbackAttempt(
                        parser_id=parser_id,
                        status="failed",
                        reason=self._failure_reason(error),
                        duration_ms=duration_ms,
                        started_at=started_at,
                        completed_at=completed_at,
                        parser_version=parser_version,
                        parameters_fingerprint=parameters_fingerprint,
                        failure_kind=failure_kind,
                        retryable=retryable,
                        metrics={"wall_duration_ms": duration_ms},
                    )
                )
                causes.append(error)
                continue
            return self._with_fallback_history(result, failures)

        error = GatewayParseError(
            attempts=failures,
            causes=causes,
            routing_decision=routing_decision,
        )
        if causes:
            raise error from causes[-1]
        raise error

    def _parse_once(
        self,
        request: ParseRequest,
        *,
        original_signals: Any,
        routing_decision: Any,
    ) -> GatewayParseResult:
        """Run exactly one parser attempt, including the MarkItDown converter path."""

        parser = self._select_parser(request.parser_id)
        if parser.PARSER_ID != self.PARSER_ID:
            if hasattr(parser, "normalize"):
                bundle = parser.normalize(request, original_signals)
                return GatewayParseResult(
                    document=self._attach_routing_metadata(
                        bundle.to_parsed_document(),
                        request=request,
                        routing_decision=routing_decision,
                    ),
                    native_files=bundle.native_files,
                )
            return GatewayParseResult(
                document=self._attach_routing_metadata(
                    parser.parse(request, original_signals),
                    request=request,
                    routing_decision=routing_decision,
                ),
                native_files={},
            )
        if original_signals.extension in parser.capability.formats:
            # The normalized bundle owns both the public document and its
            # manifest-validated native sidecars.  Returning only ``parse()``
            # loses those sidecars and makes later durable publication fail.
            bundle = parser.normalize(request, original_signals)
            return GatewayParseResult(
                document=self._attach_routing_metadata(
                    bundle.to_parsed_document(),
                    request=request,
                    routing_decision=routing_decision,
                ),
                native_files=dict(bundle.native_files),
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

        # core conversion only changes the parser input; the final protocol
        # continues to describe the original file.
        converted = converter.convert(request.content, original_signals.extension)
        converted_filename = str(Path(request.filename).with_suffix(converted.extension))
        converted_request = request.model_copy(
            update={
                "filename": converted_filename,
                "file_type": mimetypes.guess_type(converted_filename)[0]
                or "application/octet-stream",
                "content": converted.content,
            }
        )
        parsed_bundle = parser.normalize(
            converted_request,
            self._inspector.inspect(converted_request),
        )
        parsed = parsed_bundle.to_parsed_document()

        # parse_duration_ms remains the complete successful parser attempt;
        # previous failed attempts are recorded separately in fallback_history.
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
                        "filename": request.filename,
                        "file_type": request.file_type,
                        "provenance": provenance,
                    }
                ),
                request=request,
                routing_decision=routing_decision,
            ),
            native_files=dict(parsed_bundle.native_files),
        )

    def _request_for_routed_attempt(
        self,
        request: ParseRequest,
        *,
        parser_id: str,
        routing_decision: Any,
    ) -> ParseRequest:
        """Build an isolated request for one candidate without mutating caller data."""

        return request.model_copy(
            update={
                "parser_id": parser_id,
                "options": {
                    **request.options,
                    **routing_decision.parser_options,
                    "_routing_decision": routing_decision.model_dump(mode="json"),
                },
            }
        )

    @staticmethod
    def _allows_automatic_fallback(routing_decision: Any) -> bool:
        """Honor both the route mode and its explicit fallback permission."""

        return (
            routing_decision.mode == RoutingMode.AUTO
            and routing_decision.allow_automatic_fallback
        )

    @staticmethod
    def _failure_reason(error: Exception) -> str:
        """Retain a bounded, redacted diagnostic suitable for provenance."""

        detail = " ".join(str(error).split())
        detail = re.sub(
            r"(?i)(bearer|token|authorization)\s*[:=]\s*[^\s,;]+",
            r"\1=[redacted]",
            detail,
        )
        if not detail:
            return type(error).__name__
        return f"{type(error).__name__}: {detail[:500]}"

    def _attempt_parser_version(self, parser_id: str) -> str | None:
        """Read public adapter metadata without retaining an implementation object."""

        try:
            capability = getattr(self._select_parser(parser_id), "capability", None)
            return getattr(capability, "default_model_version", None)
        except Exception:
            return None

    @staticmethod
    def _attempt_parameters_fingerprint(options: dict[str, Any]) -> str:
        """Hash execution options for reproducibility without persisting secrets."""

        redacted = {
            key: value
            for key, value in options.items()
            if key
            not in {
                "_routing_decision",
                "api_token",
                "authorization",
                "bearer_token",
                "mineru_api_token",
            }
        }
        encoded = json.dumps(
            redacted,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _failure_classification(error: Exception) -> tuple[str, bool]:
        """Classify portable attempt metadata without importing orchestration."""

        explicit_kind = getattr(error, "failure_kind", None)
        if explicit_kind is not None:
            kind = getattr(explicit_kind, "value", explicit_kind)
            normalized_kind = str(kind).strip().lower()
            retryable = getattr(error, "retryable", normalized_kind == "transient")
            return normalized_kind or "parser", bool(retryable)
        detail = f"{type(error).__name__} {error}".lower()
        if any(token in detail for token in ("timeout", "temporar", "connection", "rate limit")):
            return "transient", True
        if any(token in detail for token in ("forbid", "policy", "untrusted", "not allowed")):
            return "policy", False
        if any(token in detail for token in ("unsupported", "not support", "不支持")):
            return "unsupported", False
        if any(token in detail for token in ("unavailable", "not installed", "不可用")):
            return "unavailable", False
        if any(token in detail for token in ("normaliz", "schema", "contract")):
            return "normalization", False
        return "parser", False

    @staticmethod
    def _with_fallback_history(
        result: GatewayParseResult,
        failures: list[FallbackAttempt],
    ) -> GatewayParseResult:
        if not failures:
            return result
        provenance = result.document.provenance.model_copy(
            update={
                "fallback_history": [
                    *result.document.provenance.fallback_history,
                    *failures,
                ]
            }
        )
        return GatewayParseResult(
            document=result.document.model_copy(update={"provenance": provenance}),
            native_files=result.native_files,
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
