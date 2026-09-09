"""解析器适配器的共享归一化基础设施。

统一解析器能力描述、原生结果映射、稳定 ID 和缺失证据声明；当真实解析器
不可用时提供不伪造内容的受控降级结果。
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
from abc import ABC
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from uuid import UUID

from ...domain.model.contracts import (
    BlockKind,
    DocumentBlock,
    DocumentSignals,
    EvidenceCapability,
    NativeArtifact,
    OcrSpan,
    ParseConfidence,
    ParsedDocument,
    ParsedTable,
    ParseRequest,
    ParserNativeResult,
    ParserCapability,
    RoutingDecision,
    RoutingMode,
    SourceAnchor,
    TableCell,
    TableGridSlot,
    TableSlotKind,
    TableViewScope,
)
from ...domain.normalization import (
    ParserNormalizationBundle,
    make_stable_table_id,
    make_stable_block_id,
    make_stable_document_id,
    unavailable_capability,
    partial_capability,
    available_capability,
)


class BaseParserAdapter(ABC):
    """解析器适配器的公共协议和归一化实现。"""

    PARSER_ID: str = "unimplemented"
    PROVIDER: str = "document_parser"
    DISPLAY_NAME: str = "未实现解析器"
    NATIVE_FORMATS: set[str] = set()
    MODEL_VERSIONS: list[str] = []
    DEFAULT_MODEL_VERSION: str | None = None
    REQUIRES_NETWORK: bool = False
    REQUIRES_GPU: bool = False
    UNAVAILABLE_REASON: str = "解析器骨架已创建，尚未接入实际实现。"
    TEXT_EXTENSIONS: set[str] = {".md", ".txt"}

    @property
    def capability(self) -> ParserCapability:
        """返回解析器静态能力与当前可用状态。"""

        return ParserCapability(
            parser_id=self.PARSER_ID,
            provider=self.PROVIDER,
            display_name=self.DISPLAY_NAME,
            formats=self.NATIVE_FORMATS,
            model_versions=self.MODEL_VERSIONS,
            default_model_version=self.DEFAULT_MODEL_VERSION,
            requires_network=self.REQUIRES_NETWORK,
            requires_gpu=self.REQUIRES_GPU,
            available=False,
            unavailable_reason=self.UNAVAILABLE_REASON,
        )

    def normalize(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNormalizationBundle:
        """把解析器原始输出翻译成统一中间包。"""

        raise NotImplementedError(self.UNAVAILABLE_REASON)

    def build_native_result(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNativeResult:
        """产出解析器原生结果。"""

        raise NotImplementedError(self.UNAVAILABLE_REASON)

    def normalize_native_result(
        self,
        native_result: ParserNativeResult,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNormalizationBundle:
        """把原生结果翻译成统一中间包。"""

        markdown = native_result.markdown or ""
        routing_decision = self._routing_decision(request, signals)
        blocks = self._blocks_from_payload(native_result.document_id, native_result.payload)
        if not blocks:
            blocks = self._blocks_from_markdown(native_result.document_id, markdown)
        tables, table_blocks = self._tables_from_payload(
            native_result.document_id,
            native_result.payload,
            existing_blocks=blocks,
        )
        if table_blocks:
            blocks.extend(table_blocks)
            blocks.sort(key=lambda block: block.order_index if block.order_index is not None else 10**9)
        ocr_spans = self._ocr_spans_from_payload(native_result.payload)
        capabilities = self._default_capabilities(
            missing_reason=f"{self.DISPLAY_NAME}原生结果未提供对应证据。",
            text_available=bool(markdown),
        )
        capabilities.update(native_result.capabilities)
        capabilities.update(
            self._capabilities_from_normalized_evidence(
                blocks=blocks,
                tables=tables,
                ocr_spans=ocr_spans,
                has_native_artifacts=bool(native_result.native_artifacts),
            )
        )
        warnings = [
            f"{self.DISPLAY_NAME}已进入原生结果归一化阶段。",
            *native_result.warnings,
        ]
        if not markdown:
            warnings.append("原生结果未提供可直接落地的 markdown。")

        bundle = ParserNormalizationBundle.from_minimal_markdown(
            document_id=native_result.document_id,
            filename=native_result.filename,
            file_type=native_result.file_type,
            markdown=markdown,
            parser_id=native_result.parser_id,
            parser_version=native_result.parser_version,
            parser_parameters={
                **self._public_options(request.options),
                **self._public_options(native_result.options),
            },
            routing_decision=routing_decision,
            source_size_bytes=native_result.source_size_bytes,
            source_sha256=native_result.source_sha256,
            blocks=blocks,
            tables=tables,
            ocr_spans=ocr_spans,
            confidence=ParseConfidence(
                text=1.0 if markdown else 0.0,
                layout=0.7 if any(block.anchor.bbox for block in blocks) else 0.0,
                reading_order=0.8 if any(block.order_index is not None for block in blocks) else 0.0,
                table=1.0 if tables and all(table.cells for table in tables) else (0.4 if tables else 0.0),
                overall=0.4 if blocks or tables or ocr_spans else (0.2 if markdown else 0.0),
            ),
            capabilities=capabilities,
            warnings=warnings,
            native_artifacts=native_result.native_artifacts,
            native_files=native_result.native_files,
        )
        provenance_updates: dict[str, Any] = {}
        if routing_decision is not None:
            provenance_updates["requested_parser_id"] = routing_decision.requested_parser_id
            provenance_updates["routing_mode"] = routing_decision.mode
        if provenance_updates:
            bundle = bundle.model_copy(
                update={
                    "provenance": bundle.provenance.model_copy(update=provenance_updates)
                }
            )
        return bundle

    def normalize_unimplemented(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
        *,
        parser_version: str | None = None,
        warnings: list[str] | None = None,
    ) -> ParserNormalizationBundle:
        """生成可校验的降级结果，并明确标出本次解析未产出的证据。

        这个方法用于解析器尚未接入、依赖不可用或调用失败的场景。它不会从 PDF、
        图片或 Office 二进制中猜造文本、表格、bbox 或 OCR 结果；只有原始输入本身
        就是可直接读取的文本时，才把该文本作为 markdown 透传。
        """
        return self.normalize_native_result(
            self._build_placeholder_native_result(
                request,
                signals,
                parser_version=parser_version,
                warnings=warnings,
            ),
            request,
            signals,
        )

    def _build_placeholder_native_result(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
        *,
        parser_version: str | None = None,
        warnings: list[str] | None = None,
    ) -> ParserNativeResult:
        """生成解析器不可用时可复用的原生降级对象。"""

        version = parser_version or self.DEFAULT_MODEL_VERSION or "adapter-skeleton"
        source_sha256 = hashlib.sha256(request.content).hexdigest()
        document_id = make_stable_document_id(
            source_sha256=source_sha256,
            parser_id=self.PARSER_ID,
            parser_version=version,
        )
        markdown = self._decode_direct_text(request, signals)
        generated_warnings = [
            f"{self.DISPLAY_NAME}本次未产生可用原生结果；"
            "缺失字段已通过 capabilities 标记，不会伪造解析证据。",
        ]
        if not markdown:
            generated_warnings.append(
                "输入不是可直接透传的文本格式，markdown 保持为空。"
            )
        if warnings:
            generated_warnings.extend(warnings)
        return ParserNativeResult(
            document_id=document_id,
            parser_id=self.PARSER_ID,
            parser_version=version,
            filename=request.filename,
            file_type=request.file_type,
            source_size_bytes=len(request.content),
            source_sha256=source_sha256,
            options=self._public_options(request.options),
            markdown=markdown or None,
            payload={},
            warnings=generated_warnings,
            capabilities=self._default_capabilities(
                missing_reason=f"{self.DISPLAY_NAME}本次未产生该类原始证据。",
                text_available=bool(markdown),
            ),
        )

    def _build_native_result_from_options(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
        *,
        parser_version: str | None = None,
    ) -> ParserNativeResult | None:
        """从调用方传入的真实 sidecar 构造原生结果。

        这个入口用于联调已经跑完的 Docling/MinerU/OCR 结果目录，或者后端 worker 把
        原生 JSON/Markdown 直接传进来的场景；它不猜测缺失证据。
        """

        output_dir = request.options.get("native_output_dir")
        if output_dir:
            return self._build_native_result_from_output_dir(
                request,
                signals,
                Path(str(output_dir)),
                parser_version=parser_version,
            )

        native_markdown = request.options.get("native_markdown")
        native_html = request.options.get("native_html")
        native_payload = request.options.get("native_payload")
        raw_native_files = request.options.get("native_files")
        if not any([native_markdown, native_html, native_payload, raw_native_files]):
            return None

        version = parser_version or self.DEFAULT_MODEL_VERSION or "native-sidecar"
        source_sha256 = hashlib.sha256(request.content).hexdigest()
        document_id = make_stable_document_id(
            source_sha256=source_sha256,
            parser_id=self.PARSER_ID,
            parser_version=version,
        )
        native_files: dict[str, bytes] = {}
        artifacts: list[NativeArtifact] = []

        def add_file(
            relative_path: str,
            content: bytes,
            *,
            artifact_type: str,
            file_type: str | None = None,
            required_for_quality: bool = False,
        ) -> None:
            path = self._native_path(relative_path)
            native_files[path] = content
            artifacts.append(
                self._native_artifact(
                    path=path,
                    content=content,
                    artifact_type=artifact_type,
                    file_type=file_type,
                    required_for_quality=required_for_quality,
                )
            )

        if isinstance(native_markdown, str):
            add_file(
                "full.md",
                native_markdown.encode("utf-8"),
                artifact_type="parser_markdown",
                file_type="text/markdown",
            )
        if isinstance(native_html, str):
            add_file(
                "document.html",
                native_html.encode("utf-8"),
                artifact_type="parser_html",
                file_type="text/html",
            )
        payload: dict[str, Any] = {}
        if isinstance(native_payload, dict):
            payload = native_payload
            add_file(
                "result.json",
                json.dumps(native_payload, ensure_ascii=False, indent=2).encode("utf-8"),
                artifact_type="structured_content",
                file_type="application/json",
                required_for_quality=True,
            )
        elif isinstance(native_payload, list):
            payload = {"items": native_payload}
            add_file(
                "result.json",
                json.dumps(native_payload, ensure_ascii=False, indent=2).encode("utf-8"),
                artifact_type="structured_content",
                file_type="application/json",
                required_for_quality=True,
            )
        if isinstance(raw_native_files, dict):
            for raw_path, raw_content in raw_native_files.items():
                content = (
                    raw_content
                    if isinstance(raw_content, bytes)
                    else str(raw_content).encode("utf-8")
                )
                add_file(
                    str(raw_path),
                    content,
                    artifact_type=self._artifact_type_for_path(str(raw_path)),
                    file_type=self._file_type_for_path(str(raw_path)),
                )

        return ParserNativeResult(
            document_id=document_id,
            parser_id=self.PARSER_ID,
            parser_version=version,
            filename=request.filename,
            file_type=request.file_type,
            source_size_bytes=len(request.content),
            source_sha256=source_sha256,
            options=self._public_options(request.options),
            markdown=native_markdown if isinstance(native_markdown, str) else None,
            html=native_html if isinstance(native_html, str) else None,
            payload=payload,
            native_artifacts=artifacts,
            native_files=native_files,
            capabilities=self._default_capabilities(
                missing_reason=f"{self.DISPLAY_NAME}原生 sidecar 未提供该类证据。",
                text_available=isinstance(native_markdown, str) and bool(native_markdown),
            ),
        )

    def _build_native_result_from_output_dir(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
        output_dir: Path,
        *,
        parser_version: str | None = None,
    ) -> ParserNativeResult:
        """读取真实解析器已经生成的输出目录，归档为原生结果。"""

        if not output_dir.is_dir():
            raise FileNotFoundError(f"原生输出目录不存在：{output_dir}")

        version = parser_version or self.DEFAULT_MODEL_VERSION or "native-sidecar"
        source_sha256 = hashlib.sha256(request.content).hexdigest()
        document_id = make_stable_document_id(
            source_sha256=source_sha256,
            parser_id=self.PARSER_ID,
            parser_version=version,
        )
        native_files: dict[str, bytes] = {}
        artifacts: list[NativeArtifact] = []
        payload: dict[str, Any] = {}
        markdown: str | None = None
        html: str | None = None

        files = [path for path in output_dir.rglob("*") if path.is_file()]
        for file_path in files:
            relative = file_path.relative_to(output_dir).as_posix()
            content = file_path.read_bytes()
            native_path = self._native_path(relative)
            native_files[native_path] = content
            artifacts.append(
                self._native_artifact(
                    path=native_path,
                    content=content,
                    artifact_type=self._artifact_type_for_path(relative),
                    file_type=self._file_type_for_path(relative),
                    required_for_quality=file_path.suffix.lower() == ".json",
                )
            )

        markdown_path = self._first_existing(files, {".md", ".markdown"})
        if markdown_path is not None:
            markdown = markdown_path.read_text(encoding="utf-8", errors="replace")
        html_path = self._first_existing(files, {".html", ".htm"})
        if html_path is not None:
            html = html_path.read_text(encoding="utf-8", errors="replace")
        json_path = self._first_existing(files, {".json"})
        if json_path is not None:
            raw_payload = json.loads(json_path.read_text(encoding="utf-8"))
            payload = raw_payload if isinstance(raw_payload, dict) else {"items": raw_payload}

        return ParserNativeResult(
            document_id=document_id,
            parser_id=self.PARSER_ID,
            parser_version=version,
            filename=request.filename,
            file_type=request.file_type,
            source_size_bytes=len(request.content),
            source_sha256=source_sha256,
            options=self._public_options(request.options),
            markdown=markdown,
            html=html,
            payload=payload,
            native_artifacts=artifacts,
            native_files=native_files,
            capabilities=self._default_capabilities(
                missing_reason=f"{self.DISPLAY_NAME}原生输出目录未提供该类证据。",
                text_available=bool(markdown),
            ),
        )

    def parse(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParsedDocument:
        """统一入口：先归一化，再产出最终 ``ParsedDocument``。"""

        return self.normalize(request, signals).to_parsed_document()

    def _native_path(self, relative_path: str) -> str:
        normalized = relative_path.replace("\\", "/").lstrip("/")
        if not normalized.startswith("native/"):
            normalized = f"native/{normalized}"
        return normalized

    def _native_artifact(
        self,
        *,
        path: str,
        content: bytes,
        artifact_type: str,
        file_type: str | None = None,
        required_for_quality: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> NativeArtifact:
        digest = hashlib.sha256(content).hexdigest()
        return NativeArtifact(
            artifact_id=self._artifact_id(path),
            artifact_type=artifact_type,
            path=path,
            file_type=file_type or self._file_type_for_path(path),
            size_bytes=len(content),
            sha256=digest,
            required_for_quality=required_for_quality,
            metadata=metadata or {},
        )

    def _artifact_id(self, path: str) -> str:
        normalized = path.replace("\\", "/").removeprefix("native/")
        stem = Path(normalized).stem or "artifact"
        return f"{self.PARSER_ID}-{stem}".replace("/", "-").replace("_", "-")

    def _artifact_type_for_path(self, path: str) -> str:
        suffix = Path(path).suffix.lower()
        if suffix == ".json":
            return "structured_content"
        if suffix in {".md", ".markdown"}:
            return "parser_markdown"
        if suffix in {".html", ".htm"}:
            return "parser_html"
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            return "page_or_region_image"
        if suffix in {".csv", ".xlsx", ".xls"}:
            return "table_export"
        if suffix in {".log", ".txt"}:
            return "parser_log"
        return "native_file"

    def _file_type_for_path(self, path: str) -> str:
        suffix = Path(path).suffix.lower()
        explicit = {
            ".md": "text/markdown",
            ".markdown": "text/markdown",
            ".json": "application/json",
            ".html": "text/html",
            ".htm": "text/html",
        }
        if suffix in explicit:
            return explicit[suffix]
        return mimetypes.guess_type(path)[0] or "application/octet-stream"

    def _first_existing(self, files: list[Path], suffixes: set[str]) -> Path | None:
        preferred_names = (
            "content_list.json",
            "docling_document.json",
            "mineru_result.json",
            "ocr_result.json",
            "result.json",
            "document.json",
            "full.md",
            "output.md",
            "document.md",
            "document.html",
            "output.html",
        )
        lower_by_name = {path.name.lower(): path for path in files}
        for name in preferred_names:
            path = lower_by_name.get(name)
            if path is not None and path.suffix.lower() in suffixes:
                return path
        return next((path for path in files if path.suffix.lower() in suffixes), None)

    def _public_options(self, options: dict[str, Any]) -> dict[str, Any]:
        """Strip secrets before persisting parser parameters or sidecar metadata."""

        redacted_keys = {
            "api_token",
            "authorization",
            "bearer_token",
            "mineru_api_token",
            "_routing_decision",
        }
        return {
            key: value
            for key, value in options.items()
            if key not in redacted_keys
        }

    def _installed_version(self, package_name: str, fallback: str) -> str:
        try:
            return version(package_name)
        except PackageNotFoundError:
            return fallback

    def _blocks_from_payload(
        self,
        document_id: UUID,
        payload: dict[str, Any],
    ) -> list[DocumentBlock]:
        blocks: list[DocumentBlock] = []
        section_path: list[str] = []
        page_sizes = self._page_sizes(payload)
        for order_index, item in enumerate(self._payload_items(payload)):
            if not isinstance(item, dict):
                continue
            kind = self._block_kind(item)
            text = self._item_text(item)
            markdown = self._item_markdown(item, kind=kind, text=text)
            if not text and not markdown:
                continue
            heading_level = self._heading_level(item, kind=kind)
            if kind == BlockKind.HEADING and text:
                section_path[:] = section_path[: max(0, (heading_level or 1) - 1)]
                section_path.append(text)
            source_block_id = str(
                item.get("source_block_id")
                or item.get("id")
                or item.get("self_ref")
                or f"{self.PARSER_ID}-native-{order_index:04d}"
            )
            blocks.append(
                DocumentBlock(
                    id=make_stable_block_id(
                        document_id=document_id,
                        source_block_id=source_block_id,
                        order_index=order_index,
                        kind=kind.value,
                        text=text,
                    ),
                    source_block_id=source_block_id,
                    order_index=int(item.get("order_index", order_index)),
                    kind=kind,
                    native_type=str(item.get("native_type") or item.get("type") or item.get("label") or kind.value),
                    text=text or None,
                    heading_level=heading_level,
                    markdown=markdown,
                    anchor=self._anchor_from_item(
                        item,
                        section_path=section_path,
                        page_sizes=page_sizes,
                    ),
                    metadata={
                        key: value
                        for key, value in item.items()
                        if key
                        not in {
                            "text",
                            "markdown",
                            "html",
                            "bbox",
                            "page_number",
                            "page_idx",
                            "type",
                            "label",
                            "cells",
                        }
                    },
                )
            )
        return blocks

    def _tables_from_payload(
        self,
        document_id: UUID,
        payload: dict[str, Any],
        *,
        existing_blocks: list[DocumentBlock],
    ) -> tuple[list[ParsedTable], list[DocumentBlock]]:
        tables: list[ParsedTable] = []
        created_blocks: list[DocumentBlock] = []
        page_sizes = self._page_sizes(payload)
        block_by_source = {
            block.source_block_id: block for block in existing_blocks if block.source_block_id
        }
        for index, item in enumerate(self._payload_tables(payload)):
            if not isinstance(item, dict):
                continue
            raw_cells = self._raw_table_cells(item)
            table_text = self._item_text(item) or self._table_text_from_cells(raw_cells)
            markdown = self._item_markdown(item, kind=BlockKind.TABLE, text=table_text)
            source_block_id = str(
                item.get("source_block_id")
                or item.get("block_id")
                or item.get("id")
                or f"{self.PARSER_ID}-table-{index:04d}"
            )
            block = block_by_source.get(source_block_id)
            if block is None:
                order_index = len(existing_blocks) + len(created_blocks)
                block = DocumentBlock(
                    id=make_stable_block_id(
                        document_id=document_id,
                        source_block_id=source_block_id,
                        order_index=order_index,
                        kind=BlockKind.TABLE.value,
                        text=table_text,
                    ),
                    source_block_id=source_block_id,
                    order_index=order_index,
                    kind=BlockKind.TABLE,
                    native_type=str(item.get("native_type") or item.get("type") or "table"),
                    text=table_text or None,
                    markdown=markdown,
                    anchor=self._anchor_from_item(
                        item,
                        section_path=[],
                        page_sizes=page_sizes,
                    ),
                    metadata={},
                )
                created_blocks.append(block)
            table_id = make_stable_table_id(
                document_id=document_id,
                source_table_id=str(item.get("table_id") or item.get("id") or ""),
                block_id=block.id,
            )
            source = self._position_source(item)
            page_number = self._page_number(item)
            page_height = (
                (page_sizes.get(page_number) or (None, None))[1]
                if page_number is not None
                else None
            )
            coordinate_system = self._coordinate_system(
                source.get("coordinate_system")
                or self._bbox_coordinate_system(source.get("bbox"))
            )
            cells = self._table_cells_from_payload(
                raw_cells,
                table_id=table_id,
                coordinate_system=coordinate_system,
                page_height=page_height,
            )
            data = item.get("data") if isinstance(item.get("data"), dict) else {}
            grid = self._table_grid_from_payload(item.get("grid"), cells=cells)
            metadata = {
                "native_source": self.PARSER_ID,
                **(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
            }
            tables.append(
                ParsedTable(
                    table_id=table_id,
                    block_id=block.id,
                    html=item.get("html") if isinstance(item.get("html"), str) else None,
                    markdown=markdown or None,
                    caption=item.get("caption") if isinstance(item.get("caption"), str) else None,
                    image_path=item.get("image_path") if isinstance(item.get("image_path"), str) else None,
                    page_number=page_number,
                    bbox=self._normalized_bbox(
                        source.get("bbox"),
                        coordinate_system=coordinate_system,
                        page_height=page_height,
                    ),
                    num_rows=item.get("num_rows")
                    if isinstance(item.get("num_rows"), int)
                    else data.get("num_rows")
                    if isinstance(data.get("num_rows"), int)
                    else None,
                    num_cols=item.get("num_cols")
                    if isinstance(item.get("num_cols"), int)
                    else data.get("num_cols")
                    if isinstance(data.get("num_cols"), int)
                    else None,
                    table_kind=str(item.get("table_kind") or data.get("kind") or "data"),
                    source_container=item.get("source_container")
                    if isinstance(item.get("source_container"), str)
                    else None,
                    source_container_name=item.get("source_container_name")
                    if isinstance(item.get("source_container_name"), str)
                    else None,
                    source_range=item.get("source_range")
                    if isinstance(item.get("source_range"), str)
                    else None,
                    header_rows=item.get("header_rows")
                    if isinstance(item.get("header_rows"), int)
                    else None,
                    row_header_columns=[
                        value
                        for value in item.get("row_header_columns", [])
                        if isinstance(value, int) and value >= 0
                    ],
                    view_scope=self._table_view_scope(item.get("view_scope")),
                    source_has_filter=item.get("source_has_filter")
                    if isinstance(item.get("source_has_filter"), bool)
                    else None,
                    source_row_count=item.get("source_row_count")
                    if isinstance(item.get("source_row_count"), int)
                    else None,
                    emitted_row_count=item.get("emitted_row_count")
                    if isinstance(item.get("emitted_row_count"), int)
                    else None,
                    hidden_row_count=item.get("hidden_row_count")
                    if isinstance(item.get("hidden_row_count"), int)
                    else None,
                    cells=cells,
                    grid=grid,
                    parent_table_id=item.get("parent_table_id")
                    if isinstance(item.get("parent_table_id"), str)
                    else None,
                    parent_cell_id=item.get("parent_cell_id")
                    if isinstance(item.get("parent_cell_id"), str)
                    else None,
                    nesting_depth=item.get("nesting_depth")
                    if isinstance(item.get("nesting_depth"), int)
                    else 0,
                    metadata=metadata,
                )
            )
        return tables, created_blocks

    def _ocr_spans_from_payload(self, payload: dict[str, Any]) -> list[OcrSpan]:
        spans: list[OcrSpan] = []
        raw_spans = payload.get("ocr_spans") or payload.get("spans") or payload.get("ocr")
        if not isinstance(raw_spans, list):
            return spans
        for item in raw_spans:
            if not isinstance(item, dict):
                continue
            source = self._position_source(item)
            page_number = self._page_number(item)
            page_height = (
                (self._page_sizes(payload).get(page_number) or (None, None))[1]
                if page_number is not None
                else None
            )
            coordinate_system = self._coordinate_system(
                source.get("coordinate_system")
                or self._bbox_coordinate_system(source.get("bbox"))
            )
            bbox = self._normalized_bbox(
                source.get("bbox"),
                coordinate_system=coordinate_system,
                page_height=page_height,
            )
            text = self._item_text(item)
            if bbox is None or not text:
                continue
            confidence = item.get("confidence")
            spans.append(
                OcrSpan(
                    level=str(item.get("level") or "span"),
                    text=text,
                    bbox=bbox,
                    confidence=confidence if isinstance(confidence, (int, float)) else None,
                    page_number=page_number,
                    rotation_angle=item.get("rotation_angle")
                    if isinstance(item.get("rotation_angle"), (int, float))
                    else None,
                )
            )
        return spans

    def _capabilities_from_normalized_evidence(
        self,
        *,
        blocks: list[DocumentBlock],
        tables: list[ParsedTable],
        ocr_spans: list[OcrSpan],
        has_native_artifacts: bool,
    ) -> dict[str, EvidenceCapability]:
        capabilities: dict[str, EvidenceCapability] = {}
        if any(block.anchor.page_number or block.anchor.bbox for block in blocks):
            capabilities["page_bbox"] = available_capability(
                granularity="block",
                evidence={"anchored_block_count": sum(1 for block in blocks if block.anchor.page_number or block.anchor.bbox)},
            )
        if tables:
            if all(table.cells for table in tables):
                capabilities["table_cells"] = available_capability(
                    granularity="cell",
                    evidence={"table_count": len(tables)},
                )
            else:
                capabilities["table_cells"] = partial_capability(
                    "原生结果包含表格，但未为所有表格提供物理网格 cells。",
                    granularity="table",
                    evidence={"table_count": len(tables)},
                )
        if ocr_spans:
            capabilities["ocr_confidence"] = available_capability(
                granularity="span",
                evidence={"span_count": len(ocr_spans)},
            )
        if has_native_artifacts:
            capabilities["native_artifacts"] = available_capability(
                evidence={"source": "native_sidecar"},
            )
        return capabilities

    def _payload_items(self, payload: dict[str, Any]) -> list[Any]:
        for key in ("blocks", "content", "content_list", "items", "elements", "texts"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []

    def _payload_tables(self, payload: dict[str, Any]) -> list[Any]:
        tables = payload.get("tables")
        if isinstance(tables, list):
            return tables
        return [
            item
            for item in self._payload_items(payload)
            if isinstance(item, dict) and self._block_kind(item) == BlockKind.TABLE
        ]

    def _block_kind(self, item: dict[str, Any]) -> BlockKind:
        raw = str(
            item.get("kind")
            or item.get("type")
            or item.get("label")
            or item.get("category")
            or ""
        ).lower()
        if any(token in raw for token in ("title", "heading", "section_header")):
            return BlockKind.HEADING
        if "table" in raw:
            return BlockKind.TABLE
        if any(token in raw for token in ("image", "picture", "figure")):
            return BlockKind.IMAGE
        if "formula" in raw or "equation" in raw:
            return BlockKind.FORMULA
        if "list" in raw:
            return BlockKind.LIST
        if "footnote" in raw:
            return BlockKind.FOOTNOTE
        if "reference" in raw or raw in {"ref", "ref_text"}:
            return BlockKind.REFERENCE
        if "header" in raw:
            return BlockKind.HEADER
        if "footer" in raw:
            return BlockKind.FOOTER
        if "page" in raw and "number" in raw:
            return BlockKind.PAGE_NUMBER
        return BlockKind.PARAGRAPH

    def _item_text(self, item: dict[str, Any]) -> str:
        for key in ("text", "content", "value", "ocr_text"):
            value = item.get(key)
            if isinstance(value, str):
                return value.strip()
        text_lines = item.get("text_lines")
        if isinstance(text_lines, list):
            parts = [
                line.get("text", "")
                for line in text_lines
                if isinstance(line, dict) and isinstance(line.get("text"), str)
            ]
            return "\n".join(part for part in parts if part).strip()
        return ""

    def _item_markdown(
        self,
        item: dict[str, Any],
        *,
        kind: BlockKind,
        text: str,
    ) -> str:
        markdown = item.get("markdown") or item.get("md")
        if isinstance(markdown, str):
            return markdown.strip()
        html = item.get("html")
        if kind == BlockKind.TABLE and isinstance(html, str):
            return html.strip()
        if kind == BlockKind.HEADING and text:
            return f"{'#' * (self._heading_level(item, kind=kind) or 1)} {text}"
        return text

    def _heading_level(self, item: dict[str, Any], *, kind: BlockKind) -> int | None:
        if kind != BlockKind.HEADING:
            return None
        for key in ("heading_level", "level", "text_level"):
            value = item.get(key)
            if isinstance(value, int) and value >= 1:
                return value
        return 1

    def _anchor_from_item(
        self,
        item: dict[str, Any],
        *,
        section_path: list[str],
        page_sizes: dict[int, tuple[float, float]] | None = None,
    ) -> SourceAnchor:
        anchor = item.get("anchor")
        source = self._position_source(item)
        if isinstance(anchor, dict):
            merged = {**source, **item, **anchor}
        else:
            merged = {**source, **item}
        raw_coordinate_system = merged.get("coordinate_system") or self._bbox_coordinate_system(merged.get("bbox"))
        coordinate_system = self._coordinate_system(raw_coordinate_system)
        page_number = self._page_number(merged)
        page_width = self._number(merged.get("page_width") or merged.get("width"))
        page_height = self._number(merged.get("page_height") or merged.get("height"))
        if (page_width is None or page_height is None) and page_number is not None:
            size = (page_sizes or {}).get(page_number)
            if size is not None:
                page_width, page_height = size
        bbox = self._normalized_bbox(
            merged.get("bbox"),
            coordinate_system=coordinate_system,
            page_height=page_height,
        )
        return SourceAnchor(
            page_number=page_number,
            bbox=bbox,
            page_width=page_width,
            page_height=page_height,
            coordinate_system=(
                "top_left_absolute"
                if coordinate_system == "bottom_left_absolute" and page_height is not None
                else coordinate_system
            ),
            bbox_granularity=merged.get("bbox_granularity")
            if isinstance(merged.get("bbox_granularity"), str)
            else ("block" if bbox else None),
            provenance_status=merged.get("provenance_status")
            if isinstance(merged.get("provenance_status"), str)
            else ("available" if page_number or bbox else "unavailable"),
            section_path=merged.get("section_path")
            if isinstance(merged.get("section_path"), list)
            else section_path.copy(),
            table_cell=merged.get("table_cell") if isinstance(merged.get("table_cell"), str) else None,
            container=merged.get("container")
            if isinstance(merged.get("container"), str)
            else merged.get("source_container")
            if isinstance(merged.get("source_container"), str)
            else None,
            container_name=merged.get("container_name")
            if isinstance(merged.get("container_name"), str)
            else merged.get("source_container_name")
            if isinstance(merged.get("source_container_name"), str)
            else None,
            cell_ref=merged.get("cell_ref") if isinstance(merged.get("cell_ref"), str) else None,
            range_ref=merged.get("range_ref")
            if isinstance(merged.get("range_ref"), str)
            else merged.get("source_range")
            if isinstance(merged.get("source_range"), str)
            else None,
            source_object_id=merged.get("source_object_id")
            if isinstance(merged.get("source_object_id"), str)
            else None,
            original_text=merged.get("original_text")
            if isinstance(merged.get("original_text"), str)
            else self._item_text(item) or None,
        )

    def _page_number(self, item: dict[str, Any]) -> int | None:
        value = item.get("page_number") or item.get("page")
        if isinstance(value, int) and value >= 1:
            return value
        page_idx = item.get("page_idx")
        if isinstance(page_idx, int) and page_idx >= 0:
            return page_idx + 1
        prov = item.get("prov")
        if isinstance(prov, list) and prov:
            first = prov[0]
            if isinstance(first, dict):
                page_no = first.get("page_no")
                if isinstance(page_no, int) and page_no >= 1:
                    return page_no
        return None

    def _position_source(self, item: dict[str, Any]) -> dict[str, Any]:
        prov = item.get("prov")
        if isinstance(prov, list) and prov:
            first = prov[0]
            if isinstance(first, dict):
                source = dict(first)
                bbox = first.get("bbox")
                if isinstance(bbox, dict):
                    source["bbox"] = [bbox.get("l"), bbox.get("t"), bbox.get("r"), bbox.get("b")]
                    coord_origin = bbox.get("coord_origin")
                    if isinstance(coord_origin, str):
                        source["coordinate_system"] = coord_origin.lower()
                return source
        return item

    def _page_sizes(self, payload: dict[str, Any]) -> dict[int, tuple[float, float]]:
        pages = payload.get("pages")
        sizes: dict[int, tuple[float, float]] = {}
        if not isinstance(pages, dict):
            return sizes
        for key, value in pages.items():
            if not isinstance(value, dict):
                continue
            page_no = value.get("page_no")
            if not isinstance(page_no, int):
                try:
                    page_no = int(key)
                except (TypeError, ValueError):
                    continue
            size = value.get("size")
            if not isinstance(size, dict):
                continue
            width = size.get("width")
            height = size.get("height")
            if isinstance(width, (int, float)) and isinstance(height, (int, float)):
                sizes[page_no] = (float(width), float(height))
        return sizes

    def _bbox(self, value: Any) -> tuple[float, float, float, float] | None:
        if isinstance(value, dict):
            value = [value.get("l"), value.get("t"), value.get("r"), value.get("b")]
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            return None
        try:
            left, top, right, bottom = (float(item) for item in value)
        except (TypeError, ValueError):
            return None
        return (left, top, right, bottom)

    def _coordinate_system(self, value: Any) -> str | None:
        """Return a stable coordinate-system name for locator normalization."""
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "bottomleft": "bottom_left_absolute",
            "bottom_left": "bottom_left_absolute",
            "bottomleft_absolute": "bottom_left_absolute",
            "bottom_left_absolute": "bottom_left_absolute",
            "topleft": "top_left_absolute",
            "top_left": "top_left_absolute",
            "top_left_absolute": "top_left_absolute",
        }
        return aliases.get(normalized, normalized)

    def _bbox_coordinate_system(self, value: Any) -> str | None:
        """Read a coordinate origin embedded in a native bbox object."""
        if not isinstance(value, dict):
            return None
        return value.get("coordinate_system") or value.get("coord_origin")

    def _normalized_bbox(
        self,
        value: Any,
        *,
        coordinate_system: str | None = None,
        page_height: float | None = None,
    ) -> tuple[float, float, float, float] | None:
        """Normalize native bbox values to the contract's top-left coordinates."""
        bbox = self._bbox(value)
        if bbox is None:
            return None
        coordinate_system = self._coordinate_system(
            coordinate_system or self._bbox_coordinate_system(value)
        )
        if coordinate_system != "bottom_left_absolute" or page_height is None:
            return bbox
        left, upper_y, right, lower_y = bbox
        return (left, page_height - upper_y, right, page_height - lower_y)

    def _number(self, value: Any) -> float | None:
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
        return None

    def _table_text_from_cells(self, raw_cells: Any) -> str:
        if not isinstance(raw_cells, list):
            return ""
        values = [
            str(cell.get("text") or cell.get("value") or "").strip()
            for cell in raw_cells
            if isinstance(cell, dict)
        ]
        return " | ".join(value for value in values if value)

    def _table_cells_from_payload(
        self,
        raw_cells: Any,
        *,
        table_id: str = "table",
        coordinate_system: str | None = None,
        page_height: float | None = None,
    ) -> list[TableCell]:
        cells: list[TableCell] = []
        if not isinstance(raw_cells, list):
            return cells
        for raw in raw_cells:
            if not isinstance(raw, dict):
                continue
            row = raw.get(
                "start_row",
                raw.get("row", raw.get("row_index", raw.get("start_row_offset_idx"))),
            )
            col = raw.get(
                "start_col",
                raw.get("col", raw.get("col_index", raw.get("start_col_offset_idx"))),
            )
            if not isinstance(row, int) or not isinstance(col, int):
                continue
            end_row = raw.get("end_row_offset_idx")
            end_col = raw.get("end_col_offset_idx")
            row_span = raw.get("row_span")
            col_span = raw.get("col_span")
            if not isinstance(row_span, int) and isinstance(end_row, int):
                row_span = max(1, end_row - row)
            if not isinstance(col_span, int) and isinstance(end_col, int):
                col_span = max(1, end_col - col)
            raw_bbox = raw.get("bbox")
            cell_coordinate_system = self._coordinate_system(
                raw.get("coordinate_system")
                or self._bbox_coordinate_system(raw_bbox)
                or coordinate_system
            )
            # raw_value 只能来自解析器或源文件预检的明确证据，不能用显示文本回填。
            raw_value = raw.get("raw_value") if "raw_value" in raw else None
            display_value = raw.get("display_value")
            if not isinstance(display_value, str):
                display_source = (
                    raw.get("text")
                    if raw.get("text") is not None
                    else raw.get("value")
                    if raw.get("value") is not None
                    else raw_value
                    if raw_value is not None
                    else ""
                )
                display_value = str(display_source)
            source_anchor = raw.get("source_anchor")
            if isinstance(source_anchor, dict):
                cell_anchor = self._anchor_from_item(
                    source_anchor,
                    section_path=[],
                    page_sizes={},
                )
            else:
                cell_anchor = None
            cells.append(
                TableCell(
                    cell_id=str(raw.get("cell_id") or f"{table_id}:r{row}c{col}"),
                    text=display_value,
                    raw_value=raw_value,
                    display_value=display_value,
                    normalized_value=raw.get("normalized_value")
                    if isinstance(raw.get("normalized_value"), str)
                    else None,
                    value_type=raw.get("value_type")
                    if isinstance(raw.get("value_type"), str)
                    else None,
                    formula=raw.get("formula") if isinstance(raw.get("formula"), str) else None,
                    start_row=row,
                    start_col=col,
                    row_span=row_span if isinstance(row_span, int) else 1,
                    col_span=col_span if isinstance(col_span, int) else 1,
                    column_header=bool(raw.get("column_header", False)),
                    row_header=bool(raw.get("row_header", False)),
                    roles=[str(role) for role in raw.get("roles", [])]
                    if isinstance(raw.get("roles"), list)
                    else [],
                    visible=raw.get("visible") if isinstance(raw.get("visible"), bool) else None,
                    bbox=self._normalized_bbox(
                        raw_bbox,
                        coordinate_system=cell_coordinate_system,
                        page_height=page_height,
                    ),
                    source_anchor=cell_anchor,
                )
            )
        return cells

    def _table_grid_from_payload(
        self,
        raw_grid: Any,
        *,
        cells: list[TableCell],
    ) -> list[list[TableGridSlot]]:
        if not isinstance(raw_grid, list):
            return []
        known = {cell.cell_id for cell in cells if cell.cell_id}
        grid: list[list[TableGridSlot]] = []
        for raw_row in raw_grid:
            if not isinstance(raw_row, list):
                continue
            row: list[TableGridSlot] = []
            for raw_slot in raw_row:
                if not isinstance(raw_slot, dict):
                    continue
                kind = str(raw_slot.get("kind") or "")
                if kind == TableSlotKind.ORIGIN.value:
                    cell_id = raw_slot.get("cell_id")
                    if isinstance(cell_id, str) and cell_id in known:
                        row.append(TableGridSlot(kind=TableSlotKind.ORIGIN, cell_id=cell_id))
                elif kind == TableSlotKind.COVERED.value:
                    origin_cell_id = raw_slot.get("origin_cell_id")
                    if isinstance(origin_cell_id, str) and origin_cell_id in known:
                        row.append(
                            TableGridSlot(
                                kind=TableSlotKind.COVERED,
                                origin_cell_id=origin_cell_id,
                            )
                        )
            grid.append(row)
        return grid

    def _table_view_scope(self, raw_scope: Any) -> TableViewScope:
        """把解析器的开放字符串安全收敛为统一枚举。"""

        try:
            return TableViewScope(str(raw_scope or TableViewScope.UNKNOWN.value))
        except ValueError:
            return TableViewScope.UNKNOWN

    def _raw_table_cells(self, item: dict[str, Any]) -> list[Any]:
        cells = item.get("cells")
        if isinstance(cells, list):
            return cells
        data = item.get("data")
        if isinstance(data, dict):
            table_cells = data.get("table_cells")
            if isinstance(table_cells, list):
                return table_cells
        return []

    def _decode_direct_text(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> str:
        """只透传明确文本格式，避免把二进制内容当成解析结果。"""

        file_type = request.file_type.lower()
        extension = (signals.extension or Path(request.filename).suffix).lower()
        if extension not in self.TEXT_EXTENSIONS and not file_type.startswith("text/"):
            return ""
        try:
            return request.content.decode("utf-8")
        except UnicodeDecodeError:
            return ""

    def _default_capabilities(
        self,
        *,
        missing_reason: str,
        text_available: bool,
    ) -> dict[str, object]:
        return {
            "text_content": (
                available_capability(
                    granularity="document",
                    evidence={"source": "native_markdown" if text_available else "direct_text_input"},
                )
                if text_available
                else unavailable_capability(
                    "真实解析器尚未接入，不能从该输入格式提取正文。",
                    granularity="document",
                )
            ),
            "page_bbox": unavailable_capability(
                missing_reason,
                granularity="block",
            ),
            "table_cells": unavailable_capability(
                missing_reason,
                granularity="table",
            ),
            "assets": unavailable_capability(
                missing_reason,
            ),
            "ocr_confidence": unavailable_capability(
                "未执行 OCR，未产生 OCR span 或置信度。",
                granularity="span",
            ),
            "native_artifacts": unavailable_capability(
                "真实解析器尚未接入，未归档原生 JSON、HTML、截图或日志。",
            ),
        }

    def _blocks_from_markdown(
        self,
        document_id: UUID,
        markdown: str,
    ) -> list[DocumentBlock]:
        """为直接文本输入生成稳定 block；复杂结构留给真实解析器。"""

        blocks: list[DocumentBlock] = []
        section_path: list[str] = []
        paragraph_lines: list[str] = []

        def append_block(
            *,
            kind: BlockKind,
            text: str,
            block_markdown: str,
            order_index: int,
            heading_level: int | None = None,
        ) -> None:
            source_block_id = f"{self.PARSER_ID}-placeholder-{order_index:04d}"
            blocks.append(
                DocumentBlock(
                    id=make_stable_block_id(
                        document_id=document_id,
                        source_block_id=source_block_id,
                        order_index=order_index,
                        kind=kind.value,
                        text=text,
                    ),
                    source_block_id=source_block_id,
                    order_index=order_index,
                    kind=kind,
                    native_type=f"placeholder_{kind.value}",
                    text=text,
                    heading_level=heading_level,
                    markdown=block_markdown,
                    anchor=SourceAnchor(
                        section_path=section_path.copy(),
                        original_text=text,
                        provenance_status="unavailable",
                    ),
                    metadata={"normalization_source": "direct_text_input"},
                )
            )

        def flush_paragraph() -> None:
            if not paragraph_lines:
                return
            paragraph = "\n".join(paragraph_lines).strip()
            append_block(
                kind=BlockKind.PARAGRAPH,
                text=paragraph,
                block_markdown=paragraph,
                order_index=len(blocks),
            )
            paragraph_lines.clear()

        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            if not line:
                flush_paragraph()
                continue
            if line.startswith("#"):
                flush_paragraph()
                level = len(line) - len(line.lstrip("#"))
                title = line[level:].strip()
                section_path[:] = section_path[: max(0, level - 1)]
                section_path.append(title)
                append_block(
                    kind=BlockKind.HEADING,
                    text=title,
                    block_markdown=line,
                    order_index=len(blocks),
                    heading_level=level,
                )
            else:
                paragraph_lines.append(line)
        flush_paragraph()
        return blocks

    def _routing_decision(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> RoutingDecision:
        """为尚未接入路由层的 adapter 调用保留统一路由记录。"""

        internal = request.options.get("_routing_decision")
        if isinstance(internal, RoutingDecision):
            return internal
        if isinstance(internal, dict):
            return RoutingDecision.model_validate(internal)

        manual = request.parser_id == self.PARSER_ID
        return RoutingDecision(
            mode=RoutingMode.MANUAL if manual else RoutingMode.AUTO,
            requested_parser_id=request.parser_id,
            selected_parser_id=self.PARSER_ID,
            reason="adapter skeleton normalization",
            signals=signals,
            parser_options=self._public_options(request.options),
            allow_automatic_fallback=not manual,
        )
