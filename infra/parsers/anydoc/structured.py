"""AnyDoc Document 模型到项目统一 payload 的适配。

第三方对象只在基础设施层出现。输出使用通用 blocks/tables/cells/grid 形状，
领域质量规则不依赖 AnyDoc 的 ``origin``/``covered`` 私有类型。
"""

from __future__ import annotations

from typing import Any


def _inline_text(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        if kind in {"text", "math"} and isinstance(item.get("text"), str):
            parts.append(item["text"])
        elif kind == "lineBreak":
            parts.append("\n")
        elif kind == "link":
            parts.append(_inline_text(item.get("content")))
        elif kind == "image" and isinstance(item.get("alt"), str):
            parts.append(item["alt"])
    return "".join(parts)


def _block_text(block: Any) -> str:
    if not isinstance(block, dict):
        return ""
    kind = str(block.get("kind") or "")
    if kind in {"heading", "paragraph"}:
        return _inline_text(block.get("content")).strip()
    if kind in {"codeBlock", "math"} and isinstance(block.get("text"), str):
        return block["text"]
    if kind == "blockQuote":
        return "\n".join(filter(None, (_block_text(item) for item in block.get("blocks", []))))
    if kind == "list":
        raw_list = block.get("list") if isinstance(block.get("list"), dict) else {}
        lines: list[str] = []
        for item in raw_list.get("items", []):
            if not isinstance(item, dict):
                continue
            text = " ".join(filter(None, (_block_text(child) for child in item.get("blocks", []))))
            if text:
                lines.append(text)
        return "\n".join(lines)
    return ""


def _cell_text(cell: Any) -> str:
    if not isinstance(cell, dict):
        return ""
    # 表格 block 单独建模，不把子表内容重复并入父单元格文本。
    return "\n".join(
        filter(
            None,
            (
                _block_text(block)
                for block in cell.get("blocks", [])
                if isinstance(block, dict) and block.get("kind") != "table"
            ),
        )
    ).strip()


def _escape_markdown(value: str) -> str:
    return value.replace("|", r"\|").replace("\r\n", "<br>").replace("\r", "<br>").replace("\n", "<br>")


def _anchor_copy_markdown(grid: list[list[dict[str, Any]]], cells: dict[str, dict[str, Any]]) -> str:
    if not grid:
        return ""
    width = max((len(row) for row in grid), default=0)
    lines: list[str] = []
    for row_index, row in enumerate(grid):
        values: list[str] = []
        for col_index in range(width):
            if col_index >= len(row):
                values.append("")
                continue
            slot = row[col_index]
            cell_id = slot.get("cell_id") or slot.get("origin_cell_id")
            values.append(_escape_markdown(str(cells.get(str(cell_id), {}).get("text") or "")))
        lines.append("| " + " | ".join(values) + " |")
        if row_index == 0:
            lines.append("| " + " | ".join("---" for _ in range(width)) + " |")
    return "\n".join(lines)


def anydoc_document_to_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """把桥接脚本保存的 AnyDoc Document 转成统一 payload。"""

    if payload.get("schema_name") != "AnyDocDocumentSidecar":
        return payload
    document = payload.get("document")
    if not isinstance(document, dict):
        return {
            "blocks": [],
            "tables": [],
            "anydoc_structured_error": payload.get("structured_error"),
        }

    normalized_blocks: list[dict[str, Any]] = []
    normalized_tables: list[dict[str, Any]] = []
    current_heading = ""
    order_counter = 0

    def add_table(
        block: dict[str, Any],
        *,
        parent_table_id: str | None = None,
        parent_cell_id: str | None = None,
        nesting_depth: int = 0,
    ) -> None:
        nonlocal order_counter
        table = block.get("table") if isinstance(block.get("table"), dict) else {}
        raw_grid = table.get("grid") if isinstance(table.get("grid"), list) else []
        table_index = len(normalized_tables)
        table_id = f"anydoc-table-{table_index:04d}"
        source_block_id = f"anydoc-table-block-{table_index:04d}"
        header_rows = table.get("headerRows") if isinstance(table.get("headerRows"), int) else None
        cells: list[dict[str, Any]] = []
        cell_by_id: dict[str, dict[str, Any]] = {}
        origin_ids: dict[tuple[int, int], str] = {}

        for row_index, row in enumerate(raw_grid):
            if not isinstance(row, list):
                continue
            for col_index, slot in enumerate(row):
                if not isinstance(slot, dict) or slot.get("kind") != "origin":
                    continue
                raw_cell = slot.get("cell") if isinstance(slot.get("cell"), dict) else {}
                cell_id = f"{table_id}:r{row_index}c{col_index}"
                origin_ids[(row_index, col_index)] = cell_id
                roles = ["column_header"] if header_rows is not None and row_index < header_rows else []
                cell = {
                    "cell_id": cell_id,
                    "text": _cell_text(raw_cell),
                    "display_value": _cell_text(raw_cell),
                    "start_row": row_index,
                    "start_col": col_index,
                    "row_span": raw_cell.get("rowSpan", 1),
                    "col_span": raw_cell.get("colSpan", 1),
                    "column_header": "column_header" in roles,
                    "row_header": False,
                    "roles": roles,
                    "source_anchor": {
                        "container": "sheet" if current_heading else "document",
                        "container_name": current_heading or None,
                        "table_cell": f"r{row_index}c{col_index}",
                        "provenance_status": "partial",
                    },
                }
                cells.append(cell)
                cell_by_id[cell_id] = cell

        grid: list[list[dict[str, Any]]] = []
        for row_index, row in enumerate(raw_grid):
            normalized_row: list[dict[str, Any]] = []
            if not isinstance(row, list):
                grid.append(normalized_row)
                continue
            for col_index, slot in enumerate(row):
                if not isinstance(slot, dict):
                    continue
                if slot.get("kind") == "origin":
                    normalized_row.append(
                        {"kind": "origin", "cell_id": origin_ids.get((row_index, col_index))}
                    )
                else:
                    origin_row = slot.get("originRow")
                    origin_col = slot.get("originCol")
                    normalized_row.append(
                        {
                            "kind": "covered",
                            "origin_cell_id": origin_ids.get((origin_row, origin_col)),
                        }
                    )
            grid.append(normalized_row)

        markdown = _anchor_copy_markdown(grid, cell_by_id)
        table_payload = {
            "table_id": table_id,
            "source_block_id": source_block_id,
            "kind": "table",
            "native_type": "anydoc_table",
            "table_kind": str(table.get("kind") or "data"),
            "text": " | ".join(cell["text"] for cell in cells if cell["text"]),
            "markdown": markdown,
            "num_rows": len(grid),
            "num_cols": max((len(row) for row in grid), default=0),
            "header_rows": header_rows,
            "row_header_columns": [],
            "source_container": "sheet" if current_heading else "document",
            "source_container_name": current_heading or None,
            "view_scope": "unknown",
            "emitted_row_count": len(grid),
            "cells": cells,
            "grid": grid,
            "parent_table_id": parent_table_id,
            "parent_cell_id": parent_cell_id,
            "nesting_depth": nesting_depth,
            "metadata": {
                "native_source": "anydoc",
                "structured_source": "toDocument",
                "markdown_rendering": "anchor_copy",
            },
        }
        normalized_tables.append(table_payload)
        normalized_blocks.append(
            {
                "source_block_id": source_block_id,
                "order_index": order_counter,
                "kind": "table",
                "native_type": "anydoc_table",
                "text": table_payload["text"],
                "markdown": markdown,
                "table_id": table_id,
                "container_name": current_heading or None,
            }
        )
        order_counter += 1

        # AnyDoc 的 Cell.blocks 能明确表达真嵌套表；子表独立建模并回指父单元格。
        for row_index, row in enumerate(raw_grid):
            if not isinstance(row, list):
                continue
            for col_index, slot in enumerate(row):
                if not isinstance(slot, dict) or slot.get("kind") != "origin":
                    continue
                raw_cell = slot.get("cell") if isinstance(slot.get("cell"), dict) else {}
                for child in raw_cell.get("blocks", []):
                    if not isinstance(child, dict) or child.get("kind") != "table":
                        continue
                    add_table(
                        child,
                        parent_table_id=table_id,
                        parent_cell_id=origin_ids.get((row_index, col_index)),
                        nesting_depth=nesting_depth + 1,
                    )

    for block in document.get("blocks", []):
        if not isinstance(block, dict):
            continue
        kind = str(block.get("kind") or "paragraph")
        if kind == "heading":
            current_heading = _block_text(block) or current_heading
        if kind == "table":
            add_table(block)
            continue
        text = _block_text(block)
        if not text:
            continue
        normalized_blocks.append(
            {
                "source_block_id": f"anydoc-block-{order_counter:04d}",
                "order_index": order_counter,
                "kind": kind,
                "level": block.get("level"),
                "text": text,
            }
        )
        order_counter += 1

    return {
        "blocks": normalized_blocks,
        "tables": normalized_tables,
        "anydoc_assets": payload.get("assets", []),
        "anydoc_structured_error": payload.get("structured_error"),
    }
