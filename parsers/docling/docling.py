"""Docling 解析器骨架。"""

from __future__ import annotations

import json
import hashlib
import tempfile
import time
from importlib.util import find_spec
from pathlib import Path

from ...core.contracts import DocumentSignals, ParseRequest, ParserCapability, ParserNativeResult
from ...normalizers import ParserNormalizationBundle, make_stable_document_id
from ..base import BaseParserAdapter


class DoclingParser(BaseParserAdapter):
    """Docling 的预留入口。"""

    PARSER_ID = "docling"
    PROVIDER = "ds4sd"
    DISPLAY_NAME = "Docling 解析器"
    NATIVE_FORMATS = {".pdf", ".docx", ".pptx", ".html", ".md", ".txt"}
    MODEL_VERSIONS = ["docling"]
    DEFAULT_MODEL_VERSION = "docling"
    UNAVAILABLE_REASON = "Docling 适配器骨架已创建，尚未接入实际实现。"

    @property
    def capability(self) -> ParserCapability:
        """根据当前虚拟环境动态报告 Docling 是否已安装。"""

        available = find_spec("docling") is not None
        return ParserCapability(
            parser_id=self.PARSER_ID,
            provider=self.PROVIDER,
            display_name=self.DISPLAY_NAME,
            formats=self.NATIVE_FORMATS,
            model_versions=self.MODEL_VERSIONS,
            default_model_version=self.DEFAULT_MODEL_VERSION,
            requires_network=self.REQUIRES_NETWORK,
            requires_gpu=self.REQUIRES_GPU,
            available=available,
            unavailable_reason=None if available else self.UNAVAILABLE_REASON,
        )

    def build_native_result(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNativeResult:
        sidecar_result = self._build_native_result_from_options(request, signals)
        if sidecar_result is not None:
            return sidecar_result
        if find_spec("docling") is not None:
            return self._build_with_docling(request, signals)
        return self._build_placeholder_native_result(request, signals)

    def _build_with_docling(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNativeResult:
        """调用已安装的 Docling，并保留它导出的真实 sidecar。"""

        from docling.document_converter import DocumentConverter

        started = time.perf_counter()
        source_sha256 = hashlib.sha256(request.content).hexdigest()
        parser_version = self._installed_version("docling", self.DEFAULT_MODEL_VERSION)
        document_id = make_stable_document_id(
            source_sha256=source_sha256,
            parser_id=self.PARSER_ID,
            parser_version=parser_version,
        )

        try:
            with tempfile.TemporaryDirectory(prefix="docling-run-") as temporary:
                source_path = Path(temporary) / f"source{signals.extension or Path(request.filename).suffix}"
                source_path.write_bytes(request.content)
                result = DocumentConverter().convert(source_path)
                document = result.document

                markdown = document.export_to_markdown()
                payload = document.export_to_dict() if hasattr(document, "export_to_dict") else {}
                html = document.export_to_html() if hasattr(document, "export_to_html") else None
        except Exception as error:  # pragma: no cover - depends on runtime Docling backend
            return self._build_placeholder_native_result(
                request,
                signals,
                parser_version=parser_version,
                warnings=[
                    f"Docling local invocation failed and fell back to placeholder output: {error}",
                ],
            )

        native_files: dict[str, bytes] = {
            "native/docling_document.json": json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                default=str,
            ).encode("utf-8"),
            "native/full.md": markdown.encode("utf-8"),
        }
        if html:
            native_files["native/document.html"] = html.encode("utf-8")
        native_artifacts = [
            self._native_artifact(
                path=path,
                content=content,
                artifact_type=self._artifact_type_for_path(path),
                file_type=self._file_type_for_path(path),
                required_for_quality=path.endswith(".json"),
            )
            for path, content in native_files.items()
        ]

        return ParserNativeResult(
            document_id=document_id,
            parser_id=self.PARSER_ID,
            parser_version=parser_version,
            filename=request.filename,
            file_type=request.file_type,
            source_size_bytes=len(request.content),
            source_sha256=source_sha256,
            options=request.options,
            markdown=markdown,
            html=html,
            payload=payload,
            native_artifacts=native_artifacts,
            native_files=native_files,
            warnings=[f"Docling 实际调用完成，耗时 {int((time.perf_counter() - started) * 1000)} ms。"],
        )

    def normalize(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNormalizationBundle:
        """返回统一占位包；真实 Docling JSON 映射会在这里接入。"""

        return self.normalize_native_result(
            self.build_native_result(request, signals),
            request,
            signals,
        )
