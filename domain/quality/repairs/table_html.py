"""MinerU HTML table 到 Markdown 的安全质量修复。"""

from __future__ import annotations

from dataclasses import dataclass
import re

from document_parser.domain.model.contracts import DocumentBlock, ParsedTable

from ..renderers.table_markdown import HtmlTableParseError, RenderedTable, render_html_table


@dataclass(frozen=True)
class TableHtmlRepair:
    """一张表的转换结果；失败时由调用方保留原始 table。"""

    table: ParsedTable
    block: DocumentBlock | None
    before_markdown: str
    after_markdown: str
    representation_loss: bool


def table_needs_html_conversion(table: ParsedTable) -> bool:
    """只有 Markdown 缺失或仍是 HTML 时才申请转换。"""

    html = (table.html or "").strip()
    markdown = (table.markdown or "").strip().lower()
    return bool(html) and (not markdown or "<table" in markdown)


def _normalized_cells(values: list[str]) -> list[str]:
    return [re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip() for value in values]


def _compatible_cells(existing: ParsedTable, rendered: RenderedTable) -> bool:
    """已有结构证据存在时，只允许 HTML 与其单元格文本一致。"""

    if not existing.cells:
        return True
    if len(existing.cells) != len(rendered.cells):
        return False
    for left, right in zip(existing.cells, rendered.cells):
        if _normalized_cells([left.text]) != _normalized_cells([right.text]):
            return False
        if (
            left.start_row,
            left.start_col,
            left.row_span,
            left.col_span,
        ) != (
            right.start_row,
            right.start_col,
            right.row_span,
            right.col_span,
        ):
            return False
    return True


def convert_table_html(
    table: ParsedTable,
    block: DocumentBlock | None = None,
) -> TableHtmlRepair:
    """将单表 HTML 转换为 Markdown，并同步 table 的结构字段。"""

    if not table_needs_html_conversion(table):
        return TableHtmlRepair(
            table=table,
            block=block,
            before_markdown=table.markdown or (block.markdown if block else ""),
            after_markdown=table.markdown or (block.markdown if block else ""),
            representation_loss=False,
        )
    html = (table.html or "").strip()
    rendered = render_html_table(html)
    if not _compatible_cells(table, rendered):
        raise HtmlTableParseError(
            f"table {table.table_id} 的 HTML 单元格与已有结构证据不一致。"
        )
    new_cells = table.cells or list(rendered.cells)
    new_table = table.model_copy(
        update={
            "markdown": rendered.markdown,
            "cells": new_cells,
            "num_rows": table.num_rows or rendered.num_rows,
            "num_cols": table.num_cols or rendered.num_cols,
            "metadata": {
                **table.metadata,
                "markdown_representation_loss": rendered.markdown_representation_loss,
                "markdown_renderer": "deterministic_html_table",
            },
        }
    )
    old_markdown = table.markdown or (block.markdown if block else "")
    new_block = (
        block.model_copy(update={"markdown": rendered.markdown})
        if block is not None
        else None
    )
    return TableHtmlRepair(
        table=new_table,
        block=new_block,
        before_markdown=old_markdown,
        after_markdown=rendered.markdown,
        representation_loss=rendered.markdown_representation_loss,
    )
