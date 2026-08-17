"""本地 docling 解析器（开发期第三路径）：docling 2.x → ParsedDocument 2.2。

运行前提（本机已验证）：
1. 必须用英文路径 junction 的解释器运行，否则 docling_parse 的 C++ 层
   读不了中文路径下的资源文件：
       C:/dp_venv_link/Scripts/python.exe
2. 必须设置 TORCH_COMPILE_DISABLE=1（本机无 MSVC 编译器，禁用 JIT）：
       TORCH_COMPILE_DISABLE=1 C:/dp_venv_link/Scripts/python.exe ...
3. torch==2.7.1 + torchvision==0.22.0（2.13.0 的 c10.dll 加载失败）

能力边界：
- 标题层级来自 SectionHeaderItem.level（真实模型输出）；
- 表格网格来自 TableData.grid（含 row/col span 与 header 标记）；
- bbox 由 BOTTOMLEFT 坐标系转换为 top_left_absolute。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

# 运行环境检查：必须在英文路径解释器 + 禁用 torch compile 下运行
if any(ord(ch) > 127 for ch in sys.prefix):
    raise SystemExit(
        f"docling 解析器必须在英文路径解释器下运行（C++ 层限制）。\n"
        f"当前 sys.prefix 含非 ASCII 字符: {sys.prefix}\n"
        f"请改用: C:/dp_venv_link/Scripts/python.exe 运行。"
    )
if not os.environ.get("TORCH_COMPILE_DISABLE"):
    os.environ["TORCH_COMPILE_DISABLE"] = "1"

from docling.document_converter import DocumentConverter  # noqa: E402
import hashlib
import docling  # noqa: E402

from document_parser.core.contracts import (  # noqa: E402
    BlockKind,
    DocumentBlock,
    EvidenceAvailability,
    EvidenceCapability,
    ParseConfidence,
    ParsedDocument,
    ParsedTable,
    ParserProvenance,
    RoutingMode,
    SourceAnchor,
    TableCell,
)

DOCLING_VERSION = getattr(docling, "__version__", "unknown")


def _safe_caption(item) -> str | None:
    """TableItem.caption_text 在 docling 2.x 中是方法；安全调用并限定为字符串。"""
    try:
        cap = getattr(item, "caption_text", None)
        if callable(cap):
            cap = cap()
        return cap if isinstance(cap, str) and cap else None
    except Exception:
        return None


def _bbox_to_top_left(bbox, page_height: float) -> tuple[float, float, float, float] | None:
    """docling bbox 为 BOTTOMLEFT 坐标 (l, t, r, b)，转为 top_left (l, top, r, bottom)。"""
    if bbox is None or page_height is None:
        return None
    try:
        l, t, r, b = bbox.l, bbox.t, bbox.r, bbox.b
        return (float(l), float(page_height) - float(t), float(r), float(page_height) - float(b))
    except AttributeError:
        return None


def parse_pdf(source: Path) -> ParsedDocument:
    """docling 解析 PDF → ParsedDocument（需要运行环境见文件头部说明）。"""
    source = Path(source)
    conv = DocumentConverter()
    doc = conv.convert(str(source)).document

    blocks: list[DocumentBlock] = []
    tables: list[ParsedTable] = []
    table_seq = 0
    for order_index, (item, _level) in enumerate(doc.iterate_items()):
        kind_name = type(item).__name__
        prov = item.prov[0] if item.prov else None
        page_number = prov.page_no if prov else None
        page_size = doc.pages.get(page_number).size if page_number in (doc.pages or {}) else None
        page_height = float(page_size.height) if page_size else 792.0
        bbox = _bbox_to_top_left(getattr(prov, "bbox", None), page_height)
        anchor = SourceAnchor(
            page_number=page_number,
            bbox=bbox,
            page_width=float(page_size.width) if page_size else None,
            page_height=page_height,
            coordinate_system="top_left_absolute" if bbox else None,
            bbox_granularity="block" if bbox else None,
        )
        text = getattr(item, "text", "") or ""

        if kind_name == "SectionHeaderItem":
            blocks.append(
                DocumentBlock(
                    id=uuid4(),
                    source_block_id=f"docling-{kind_name}-{order_index}",
                    order_index=order_index,
                    kind=BlockKind.HEADING,
                    text=text,
                    heading_level=getattr(item, "level", None) or None,
                    markdown=f"{'#' * ((getattr(item, 'level', None) or 1))} {text}",
                    anchor=anchor,
                )
            )
            continue

        if kind_name == "TableItem":
            table_seq += 1
            table_id = f"table-{table_seq:03d}"
            grid = item.data.grid or []
            cells = [
                TableCell(
                    text=cell.text,
                    start_row=cell.start_row_offset_idx,
                    start_col=cell.start_col_offset_idx,
                    row_span=cell.row_span,
                    col_span=cell.col_span,
                    column_header=cell.column_header,
                    row_header=cell.row_header,
                    bbox=_bbox_to_top_left(cell.bbox, page_height),
                )
                for row in grid
                for cell in row
            ]
            table_md = _grid_to_markdown(grid)
            block = DocumentBlock(
                id=uuid4(),
                source_block_id=f"docling-TableItem-{order_index}",
                order_index=order_index,
                kind=BlockKind.TABLE,
                text=table_md,
                markdown=table_md,
                anchor=anchor,
                metadata={"table_id": table_id},
            )
            blocks.append(block)
            caption = _safe_caption(item)
            tables.append(
                ParsedTable(
                    table_id=table_id,
                    block_id=block.id,
                    html=None,
                    markdown=table_md or None,
                    caption=caption,
                    page_number=page_number,
                    bbox=bbox,
                    num_rows=len(grid),
                    num_cols=max((len(row) for row in grid), default=0) if grid else None,
                    cells=cells,
                    metadata={"parser": "docling-local"},
                )
            )
            continue

        if kind_name == "PictureItem":
            blocks.append(
                DocumentBlock(
                    id=uuid4(),
                    source_block_id=f"docling-PictureItem-{order_index}",
                    order_index=order_index,
                    kind=BlockKind.IMAGE,
                    text=None,
                    markdown=f"![{getattr(item, 'caption_text', '') or ''}]({getattr(item, 'image', None) or ''})",
                    anchor=anchor,
                )
            )
            continue

        # 其余文本类（TextItem 等）统一按段落
        blocks.append(
            DocumentBlock(
                id=uuid4(),
                source_block_id=f"docling-{kind_name}-{order_index}",
                order_index=order_index,
                kind=BlockKind.PARAGRAPH,
                text=text,
                markdown=text,
                anchor=anchor,
            )
        )

    source_bytes = source.read_bytes()
    return ParsedDocument(
        document_id=uuid4(),
        filename=source.name,
        file_type="application/pdf",
        source_size_bytes=len(source_bytes),
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        markdown=doc.export_to_markdown(),
        blocks=blocks,
        tables=tables,
        confidence=ParseConfidence(text=0.9, layout=0.9, reading_order=0.85, table=0.9, overall=0.9),
        provenance=ParserProvenance(
            parser_id="docling-local",
            routing_mode=RoutingMode.AUTO,
            model="docling",
            version=DOCLING_VERSION,
        ),
        capabilities={
            "page_bbox": EvidenceCapability(
                state=EvidenceAvailability.AVAILABLE,
                granularity="block",
                reason=None,
            ),
            "table_cells": EvidenceCapability(
                state=EvidenceAvailability.AVAILABLE,
                granularity="cell_with_span",
                reason=None,
            ),
            "ocr_confidence": EvidenceCapability(
                state=EvidenceAvailability.UNAVAILABLE,
                reason="文本型 PDF 未启用 OCR。",
            ),
        },
        warnings=[],
    )


def _grid_to_markdown(grid) -> str:
    """docling TableData.grid → markdown 表格（合并单元格取左上格文本）。"""
    if not grid:
        return ""
    max_row = max(cell.start_row_offset_idx + cell.row_span for row in grid for cell in row)
    max_col = max(cell.start_col_offset_idx + cell.col_span for row in grid for cell in row)
    out: list[list[str]] = [[""] * max_col for _ in range(max_row)]
    for row in grid:
        for cell in row:
            out[cell.start_row_offset_idx][cell.start_col_offset_idx] = cell.text
    lines = ["| " + " | ".join(c or " " for c in out[0]) + " |"]
    lines.append("| " + " | ".join("---" for _ in out[0]) + " |")
    for row in out[1:]:
        lines.append("| " + " | ".join(c or " " for c in row) + " |")
    return "\n".join(lines)
