"""Docling 解析器骨架。"""

from __future__ import annotations

import json
import hashlib
import tempfile
import time
from importlib.util import find_spec
from pathlib import Path

from ....domain.model.contracts import DocumentSignals, ParseRequest, ParserCapability, ParserNativeResult
from ....domain.normalization import ParserNormalizationBundle, make_stable_document_id
from ....domain.routing.ids import DOCLING_ID
from ..base import BaseParserAdapter
from ..markdown_normalization import blocks_and_tables_from_markdown


def _table_coordinate_text(table) -> dict[tuple[int, int], str]:
    """Return origin-cell text by coordinate for a conservative table match."""

    return {
        (cell.start_row, cell.start_col): " ".join(cell.text.split())
        for cell in table.cells
    }


def _align_docling_table_markdown(
    bundle: ParserNormalizationBundle,
) -> ParserNormalizationBundle:
    """Bind Docling native table structure to its own pipe-table rendering.

    Docling structured JSON sometimes serializes table markdown as one
    flattened line even though export_to_markdown contains a valid pipe
    table. Alignment is allowed only when table count, dimensions, and every
    origin-cell value match. Native cells, spans, anchors, and grids remain the
    authoritative structure.
    """

    if not bundle.tables or not bundle.markdown:
        return bundle
    _, rendered_tables = blocks_and_tables_from_markdown(bundle.markdown)
    if len(rendered_tables) != len(bundle.tables):
        return bundle.model_copy(
            update={
                "warnings": [
                    *bundle.warnings,
                    "Docling table rendering was not aligned: structured and Markdown table counts differ.",
                ]
            }
        )

    updated_tables = []
    block_markdown: dict[str, str] = {}
    aligned = 0
    for native, rendered in zip(bundle.tables, rendered_tables, strict=True):
        dimensions_match = (
            native.num_rows == rendered.num_rows
            and native.num_cols == rendered.num_cols
        )
        values_match = _table_coordinate_text(native) == _table_coordinate_text(rendered)
        if not dimensions_match or not values_match:
            updated_tables.append(native)
            continue
        metadata = {
            **native.metadata,
            "markdown_rendering": "docling_export_pipe",
            "markdown_rendering_aligned": True,
        }
        updated = native.model_copy(
            update={"markdown": rendered.markdown, "metadata": metadata}
        )
        updated_tables.append(updated)
        block_markdown[str(native.block_id)] = rendered.markdown
        aligned += 1

    if not aligned:
        return bundle.model_copy(
            update={
                "warnings": [
                    *bundle.warnings,
                    "Docling table rendering was not aligned: cell evidence did not match.",
                ]
            }
        )
    updated_blocks = [
        block.model_copy(update={"markdown": block_markdown[str(block.id)]})
        if str(block.id) in block_markdown
        else block
        for block in bundle.blocks
    ]
    warning = (
        f"Aligned {aligned}/{len(bundle.tables)} Docling table renderings "
        "after exact dimension and cell-value checks."
    )
    return bundle.model_copy(
        update={
            "tables": updated_tables,
            "blocks": updated_blocks,
            "warnings": [*bundle.warnings, warning],
        }
    )


class DoclingParser(BaseParserAdapter):
    """Docling 的预留入口。"""

    PARSER_ID = DOCLING_ID
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
        """调用 Docling 或读取 sidecar，并归一化为统一文档包。"""

        bundle = self.normalize_native_result(
            self.build_native_result(request, signals),
            request,
            signals,
        )
        return _align_docling_table_markdown(bundle)
