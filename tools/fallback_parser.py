"""本地兜底解析器（开发期使用）：pdfplumber → ParsedDocument 2.2。

无网络 / 无 MinerU API key 时用于生成 ParsedDocument fixtures。
能力边界：
- 提供 word/line 级真实 bbox（page_bbox available）；
- 表格通过 pdfplumber 启发式网格提取（table_cells partial：有坐标但
  header/span 语义不可靠，全部按 span=1 输出）；
- 标题按字号启发式判断（保守：不确定时不标注 heading_level）；
- 无 OCR 能力。
"""

from __future__ import annotations

import hashlib
import re
import statistics
from pathlib import Path
from uuid import uuid4

import pdfplumber

from document_parser.domain.model.contracts import (
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


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _group_words_into_lines(words: list[dict]) -> list[dict]:
    """按 top 坐标把 word 聚成行，行内按 x0 排序。"""
    if not words:
        return []
    # 按 top 排序后，与当前行 top 差小于阈值则并入当前行
    sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[dict] = []
    for word in sorted_words:
        if lines and abs(word["top"] - lines[-1]["top"]) <= 3.0:
            lines[-1]["words"].append(word)
            lines[-1]["top"] = min(lines[-1]["top"], word["top"])
            lines[-1]["bottom"] = max(lines[-1]["bottom"], word["bottom"])
            lines[-1]["x0"] = min(lines[-1]["x0"], word["x0"])
            lines[-1]["x1"] = max(lines[-1]["x1"], word["x1"])
        else:
            lines.append(
                {
                    "words": [word],
                    "top": word["top"],
                    "bottom": word["bottom"],
                    "x0": word["x0"],
                    "x1": word["x1"],
                    "sizes": [word.get("size", 0)],
                }
            )
        lines[-1]["sizes"].append(word.get("size", 0))
    return lines


def _line_text(line: dict) -> str:
    return " ".join(w["text"] for w in line["words"])


def _line_max_size(line: dict) -> float:
    return max(word.get("size", 0) for word in line["words"])


def _in_bbox(point: tuple[float, float], bbox: tuple[float, float, float, float]) -> bool:
    x, y = point
    x0, top, x1, bottom = bbox
    return x0 - 2 <= x <= x1 + 2 and top - 2 <= y <= bottom + 2


def _markdown_table(rows: list[list[str]]) -> str:
    """二维数组 → markdown 表格字符串。"""
    if not rows:
        return ""
    lines = ["| " + " | ".join(cell or "" for cell in rows[0]) + " |"]
    lines.append("| " + " | ".join("---" for _ in rows[0]) + " |")
    for row in rows[1:]:
        lines.append("| " + " | ".join(cell or "" for cell in row) + " |")
    return "\n".join(lines)


def parse_pdf(source: Path, *, file_type: str = "application/pdf") -> ParsedDocument:
    """pdfplumber 解析 PDF → ParsedDocument（尽力而为）。"""
    source = Path(source)
    blocks: list[DocumentBlock] = []
    tables: list[ParsedTable] = []
    markdown_parts: list[str] = []
    order_index = 0
    table_seq = 0

    # 先收集所有页的表格（过滤正文行时要把表格内文字排除）
    all_pages = []
    with pdfplumber.open(source) as pdf:
        for page in pdf.pages:
            tables_on_page = page.find_tables()
            page_tables = []
            for table in tables_on_page:
                page_tables.append(table)
            all_pages.append((page, page_tables))

        for page, page_tables in all_pages:
            page_number = page.page_number
            words = page.extract_words(keep_blank_chars=False, use_text_flow=True)
            lines = _group_words_into_lines(words)

            # 表格 bbox 列表
            table_boxes = [
                (table.bbox, table.extract()) for table in page_tables
            ]

            for line in lines:
                # 跳过表格 bbox 内的行（表格单独表达）
                if any(
                    _in_bbox((line["x0"], line["top"]), box)
                    and _in_bbox((line["x1"], line["bottom"]), box)
                    for box, _ in table_boxes
                ):
                    continue
                text = _line_text(line)
                if not text.strip():
                    continue
                size = _line_max_size(line)
                block = DocumentBlock(
                    id=uuid4(),
                    source_block_id=f"pdfplumber-p{page_number}-l{order_index}",
                    order_index=order_index,
                    kind=BlockKind.PARAGRAPH,
                    text=text,
                    markdown=text,
                    anchor=SourceAnchor(
                        page_number=page_number,
                        bbox=(line["x0"], line["top"], line["x1"], line["bottom"]),
                        page_width=float(page.width),
                        page_height=float(page.height),
                        coordinate_system="top_left_absolute",
                        bbox_granularity="line",
                        provenance_status="verified",
                        original_text=text,
                    ),
                )
                # 保守标题启发式：字号明显大于页面中位数时才标 heading
                sizes = [w.get("size", 0) for w in words]
                if sizes:
                    median_size = statistics.median(sizes)
                    if size >= median_size + 1.5:
                        block.kind = BlockKind.HEADING
                        block.heading_level = _guess_heading_level(size, median_size)
                        block.markdown = "# " + text
                blocks.append(block)
                markdown_parts.append(block.markdown)
                order_index += 1

            # 表格 block
            for box, rows in table_boxes:
                if not rows:
                    continue
                table_seq += 1
                table_id = f"table-{table_seq:03d}"
                table_md = _markdown_table(rows)
                table_block = DocumentBlock(
                    id=uuid4(),
                    source_block_id=f"pdfplumber-p{page_number}-t{table_seq}",
                    order_index=order_index,
                    kind=BlockKind.TABLE,
                    text=table_md,
                    markdown=table_md,
                    anchor=SourceAnchor(
                        page_number=page_number,
                        bbox=box,
                        page_width=float(page.width),
                        page_height=float(page.height),
                        coordinate_system="top_left_absolute",
                        bbox_granularity="table",
                        provenance_status="verified",
                    ),
                    metadata={"table_id": table_id},
                )
                blocks.append(table_block)
                markdown_parts.append(table_md)
                order_index += 1

                # 构造 cells：pdfplumber 的 extract() 是二维文本数组，
                # 无 span/header 语义；header 行按第一行保守猜测
                cells = [
                    TableCell(
                        text=cell or "",
                        start_row=row_idx,
                        start_col=col_idx,
                        row_span=1,
                        col_span=1,
                        column_header=row_idx == 0,
                        row_header=False,
                        bbox=None,
                    )
                    for row_idx, row in enumerate(rows)
                    for col_idx, cell in enumerate(row)
                ]
                tables.append(
                    ParsedTable(
                        table_id=table_id,
                        block_id=table_block.id,
                        html=None,
                        markdown=table_md,
                        page_number=page_number,
                        bbox=box,
                        num_rows=len(rows),
                        num_cols=max((len(r) for r in rows), default=0),
                        cells=cells,
                        metadata={"parser": "pdfplumber-fallback"},
                    )
                )

    source_bytes = source.read_bytes()
    return ParsedDocument(
        document_id=uuid4(),
        filename=source.name,
        file_type=file_type,
        source_size_bytes=len(source_bytes),
        source_sha256=_sha256(source_bytes),
        markdown="\n\n".join(markdown_parts),
        blocks=blocks,
        tables=tables,
        confidence=ParseConfidence(text=0.7, layout=0.6, reading_order=0.6, table=0.5, overall=0.6),
        provenance=ParserProvenance(
            parser_id="pdfplumber-fallback",
            routing_mode=RoutingMode.AUTO,
            model="pdfplumber",
            version="0.11",
        ),
        capabilities={
            "page_bbox": EvidenceCapability(
                state=EvidenceAvailability.AVAILABLE,
                granularity="line",
                reason=None,
            ),
            "table_cells": EvidenceCapability(
                state=EvidenceAvailability.PARTIAL,
                granularity="rowcol_only",
                reason="pdfplumber 启发式网格：无 span/header 语义，全部按 span=1。",
            ),
            "ocr_confidence": EvidenceCapability(
                state=EvidenceAvailability.UNAVAILABLE,
                reason="本地兜底解析器无 OCR 能力。",
            ),
        },
        warnings=["本地兜底解析（pdfplumber），表格结构语义不可靠。"],
    )


def _guess_heading_level(size: float, median_size: float) -> int | None:
    """按字号差保守推断标题层级；不确定返回 None。"""
    delta = size - median_size
    if delta >= 8:
        return 1
    if delta >= 4:
        return 2
    if delta >= 1.5:
        return 3
    return None
