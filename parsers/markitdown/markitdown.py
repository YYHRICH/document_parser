"""Microsoft MarkItDown 解析器实现。

职责边界：本文件只把 MarkItDown 原生支持的文件转换为 Markdown，再生成统一
文档块。`.doc/.ppt` 等旧格式由 ``core.converter`` 在进入解析器前统一标准化，
这里不判断操作系统，也不调用 LibreOffice、Word 或 PowerPoint。
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import time
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from pathlib import Path

from ...core.contracts import (
    DocumentSignals,
    NativeArtifact,
    ParseConfidence,
    ParsedDocument,
    ParseRequest,
    ParserCapability,
    ParserNativeResult,
    RoutingDecision,
    RoutingMode,
)
from ...normalizers import (
    NormalizationContext,
    ParserNormalizationBundle,
    available_capability,
    make_stable_document_id,
    unavailable_capability,
)
from ..ports import (
    ParserExecutionError,
    ParserFailureKind,
    ParserProbeResult,
    diagnose_parser_exception,
)
from .block_builder import blocks_from_markdown


class MarkItDownParser:
    """MarkItDown plugin with explicit probe/execute/normalize/diagnose ports."""

    PARSER_ID = "microsoft.markitdown"
    PROVIDER = "microsoft"
    DISPLAY_NAME = "Microsoft MarkItDown 解析器"
    DEFAULT_MODEL_VERSION = "markitdown"

    # Only direct MarkItDown inputs are declared here.  Legacy Office conversion
    # remains a composition-root concern and is added to Gateway's snapshot.
    NATIVE_FORMATS = {
        ".pdf",
        ".docx",
        ".pptx",
        ".xlsx",
        ".xls",
        ".html",
        ".htm",
        ".md",
        ".txt",
        ".csv",
        ".json",
        ".xml",
        ".zip",
        ".epub",
    }

    @property
    def capability(self) -> ParserCapability:
        """Report package availability without initializing its converter."""

        available = find_spec("markitdown") is not None
        return ParserCapability(
            parser_id=self.PARSER_ID,
            provider=self.PROVIDER,
            display_name=self.DISPLAY_NAME,
            formats=self.NATIVE_FORMATS,
            model_versions=[self.DEFAULT_MODEL_VERSION],
            default_model_version=self.DEFAULT_MODEL_VERSION,
            requires_network=False,
            requires_gpu=False,
            available=available,
            unavailable_reason=(
                None
                if available
                else "markitdown[all] is not installed in the current environment."
            ),
        )

    def probe(
        self,
        request: ParseRequest | None = None,
        signals: DocumentSignals | None = None,
    ) -> ParserProbeResult:
        """Expose a routing-safe capability snapshot without doing a conversion."""

        capability = self.capability.model_copy(deep=True)
        extension = self._probe_extension(request=request, signals=signals)
        supported = extension is None or extension in capability.formats
        if not supported:
            reason = f"{self.DISPLAY_NAME} does not support {extension}."
        elif not capability.available:
            reason = capability.unavailable_reason
        else:
            reason = None
        return ParserProbeResult(
            capability=capability,
            supported=supported,
            executable=bool(supported and capability.available),
            reason=reason,
        )

    def capability_snapshot(self) -> ParserCapability:
        """Return a detached snapshot suitable for routing injection."""

        return self.probe().capability.model_copy(deep=True)

    def execute(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNativeResult:
        """Convert input to native Markdown without constructing final documents."""

        probe = self.probe(request, signals)
        if not probe.supported:
            raise self.execution_error(
                failure_kind=ParserFailureKind.UNSUPPORTED,
                safe_message=f"{self.DISPLAY_NAME} does not support this input.",
            )
        if not probe.executable:
            raise self.execution_error(
                failure_kind=ParserFailureKind.UNAVAILABLE,
                safe_message=f"{self.DISPLAY_NAME} backend is unavailable in this environment.",
            )

        started = time.perf_counter()
        try:
            markdown = _convert_with_markitdown(request.content, signals.extension)
        except ParserExecutionError:
            raise
        except Exception as error:
            diagnosed = self.diagnose(error, request=request, signals=signals)
            raise diagnosed from error
        duration_ms = int((time.perf_counter() - started) * 1000)
        source_sha256 = hashlib.sha256(request.content).hexdigest()
        parser_version = _markitdown_version()
        document_id = make_stable_document_id(
            source_sha256,
            parser_id=self.PARSER_ID,
            parser_version=parser_version,
        )
        native_content = markdown.encode("utf-8")
        native_path = "native/full.md"
        return ParserNativeResult(
            document_id=document_id,
            parser_id=self.PARSER_ID,
            parser_version=parser_version,
            filename=request.filename,
            file_type=request.file_type,
            source_size_bytes=len(request.content),
            source_sha256=source_sha256,
            options={"_markitdown_duration_ms": duration_ms},
            markdown=markdown,
            native_artifacts=[
                NativeArtifact(
                    artifact_id="markitdown-full-markdown",
                    artifact_type="parser_markdown",
                    path=native_path,
                    file_type="text/markdown",
                    size_bytes=len(native_content),
                    sha256=hashlib.sha256(native_content).hexdigest(),
                    required_for_quality=False,
                )
            ],
            native_files={native_path: native_content},
            warnings=[f"MarkItDown native conversion completed in {duration_ms} ms."],
        )

    def build_native_result(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNativeResult:
        """Compatibility alias for callers using the older native-result name."""

        return self.execute(request, signals)

    def normalize_native(
        self,
        native_result: ParserNativeResult,
        context: NormalizationContext,
    ) -> ParserNormalizationBundle:
        """Normalize Markdown evidence without importing Gateway or routing."""

        markdown = native_result.markdown or ""
        routing_decision = context.routing_decision or self._routing_decision(context)
        duration_raw = native_result.options.get("_markitdown_duration_ms", 0)
        duration_ms = duration_raw if isinstance(duration_raw, int) and duration_raw >= 0 else 0
        bundle = ParserNormalizationBundle.from_minimal_markdown(
            document_id=native_result.document_id,
            filename=native_result.filename,
            file_type=native_result.file_type,
            markdown=markdown,
            parser_id=native_result.parser_id,
            parser_version=native_result.parser_version,
            parser_parameters={
                "plugins_enabled": False,
                "source_extension": context.signals.extension,
                **self._public_options(context.parser_options),
            },
            routing_decision=routing_decision,
            source_size_bytes=native_result.source_size_bytes,
            source_sha256=native_result.source_sha256,
            blocks=blocks_from_markdown(markdown),
            confidence=ParseConfidence(overall=0.9 if markdown else 0.0),
            capabilities={
                "text_content": available_capability(granularity="document"),
                "page_bbox": unavailable_capability("MarkItDown does not emit page coordinates."),
                "table_cells": unavailable_capability("MarkItDown does not emit physical table cells."),
                "ocr_confidence": unavailable_capability("MarkItDown does not emit OCR confidence."),
                "native_artifacts": available_capability(evidence={"source": "native_sidecar"}),
            },
            warnings=list(native_result.warnings),
            native_artifacts=list(native_result.native_artifacts),
            native_files=dict(native_result.native_files),
        )
        provenance = bundle.provenance.model_copy(
            update={
                "markitdown_duration_ms": duration_ms,
                "parse_duration_ms": duration_ms,
            }
        )
        return bundle.model_copy(update={"provenance": provenance})

    def normalize_native_result(
        self,
        native_result: ParserNativeResult,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNormalizationBundle:
        """Compatibility bridge to the standalone normalizer context."""

        return self.normalize_native(
            native_result,
            NormalizationContext.from_parse_request(request, signals),
        )

    def normalize(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNormalizationBundle:
        """Run the execution and normalization ports in sequence."""

        return self.normalize_native_result(self.execute(request, signals), request, signals)

    def parse(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParsedDocument:
        """Compatibility document entry point used by the existing Gateway path."""

        return self.normalize(request, signals).to_parsed_document()

    def diagnose(
        self,
        error: Exception,
        *,
        request: ParseRequest | None = None,
        signals: DocumentSignals | None = None,
    ) -> ParserExecutionError:
        """Map raw MarkItDown failures to a redacted platform error."""

        del request, signals
        return diagnose_parser_exception(
            error,
            parser_id=self.PARSER_ID,
            display_name=self.DISPLAY_NAME,
        )

    def execution_error(
        self,
        *,
        failure_kind: ParserFailureKind | str = ParserFailureKind.PARSER,
        retryable: bool = False,
        safe_message: str,
    ) -> ParserExecutionError:
        """Construct a typed error without exposing backend diagnostics."""

        return ParserExecutionError(
            parser_id=self.PARSER_ID,
            failure_kind=failure_kind,
            retryable=retryable,
            safe_message=safe_message,
        )

    @staticmethod
    def _probe_extension(
        *,
        request: ParseRequest | None,
        signals: DocumentSignals | None,
    ) -> str | None:
        if signals is not None and signals.extension:
            value = signals.extension
        elif request is not None:
            value = Path(request.filename).suffix
        else:
            return None
        normalized = str(value).strip().lower()
        if not normalized:
            return None
        return normalized if normalized.startswith(".") else f".{normalized}"

    def _routing_decision(self, context: NormalizationContext) -> RoutingDecision:
        manual = context.requested_parser_id == self.PARSER_ID
        return RoutingDecision(
            mode=RoutingMode.MANUAL if manual else RoutingMode.AUTO,
            requested_parser_id=context.requested_parser_id,
            selected_parser_id=self.PARSER_ID,
            reason="MarkItDown standalone normalization",
            signals=context.signals,
            parser_options=self._public_options(context.parser_options),
            allow_automatic_fallback=not manual,
        )

    @staticmethod
    def _public_options(options: dict[str, object]) -> dict[str, object]:
        redacted = {
            "api_token",
            "authorization",
            "bearer_token",
            "mineru_api_token",
            "_routing_decision",
        }
        return {key: value for key, value in options.items() if key not in redacted}


def _convert_with_markitdown(content: bytes, extension: str) -> str:
    """在受控子进程执行第三方转换器，并返回 UTF-8 Markdown。"""

    # 当前 MarkItDown 依赖在普通后台线程中存在阻塞风险。隔离到子进程后，单个
    # 文件超时或第三方库崩溃只会使当前任务失败，不会锁死 API worker。
    script = r"""
import sys
from pathlib import Path
from markitdown import MarkItDown

source, output, extension = sys.argv[1:4]
with Path(source).open("rb") as stream:
    result = MarkItDown(enable_plugins=False).convert_stream(
        stream,
        file_extension=extension,
    )
Path(output).write_text(result.text_content, encoding="utf-8")
"""

    # 输入、输出和错误日志均放入一次性目录，退出后自动清理。
    with tempfile.TemporaryDirectory(prefix="markitdown-run-") as temporary:
        directory = Path(temporary)
        source = directory / f"source{extension}"
        output = directory / "output.md"
        error_log = directory / "error.log"
        source.write_bytes(content)

        # Windows 隐藏子进程窗口；其他系统 creationflags 必须为 0。
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with error_log.open("w", encoding="utf-8") as errors:
            completed = subprocess.run(
                [sys.executable, "-c", script, str(source), str(output), extension],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=errors,
                timeout=300,
                creationflags=creation_flags,
                check=False,
            )

        # 错误只回传子进程日志，不泄露输入正文或临时文件内容。
        if completed.returncode != 0 or not output.is_file():
            message = error_log.read_text(encoding="utf-8").strip()
            raise RuntimeError(
                f"MarkItDown 转换失败（退出码 {completed.returncode}）：{message}"
            )
        return output.read_text(encoding="utf-8")


def _markitdown_version() -> str:
    """读取安装版本并写入 provenance，方便复现不同版本的解析差异。"""

    try:
        return version("markitdown")
    except PackageNotFoundError:
        return "unknown"
