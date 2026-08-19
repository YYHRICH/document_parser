"""ParsedDocument 的共同确定性归一入口。"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from document_parser.core.contracts import (
    DocumentBlock,
    ParsedDocument,
    ParsedTable,
)

from .tables import cells_to_markdown, normalize_table_cells
from .formulas import normalize_formula_evidence


def _norm_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def _stabilize_block_ids(
    document: ParsedDocument,
    blocks: list[DocumentBlock],
    *,
    parser_label: str,
) -> tuple[list[DocumentBlock], dict[UUID, UUID]]:
    """用输入摘要和解析器原生 ID 生成跨次解析稳定的 block UUID。"""

    source_key = document.source_sha256 or f"{document.filename}:{document.source_size_bytes or 0}"
    occurrences: dict[str, int] = {}
    id_map: dict[UUID, UUID] = {}
    stable_blocks: list[DocumentBlock] = []
    for index, block in enumerate(blocks):
        native_key = block.source_block_id or f"{block.kind}:{block.text or ''}"
        occurrence = occurrences.get(native_key, 0)
        occurrences[native_key] = occurrence + 1
        stable_id = uuid5(
            NAMESPACE_URL,
            f"document-parser/block/{source_key}/{parser_label}/{native_key}/{occurrence}",
        )
        id_map[block.id] = stable_id
        stable_blocks.append(block.model_copy(update={"id": stable_id, "order_index": index}))
    return stable_blocks, id_map


def _remap_block_ref(value: str, id_map: dict[UUID, UUID]) -> str:
    try:
        old_id = UUID(value)
    except (ValueError, AttributeError, TypeError):
        return value
    return str(id_map.get(old_id, old_id))


def _table_signature(table: ParsedTable) -> tuple[str, ...]:
    """返回第一逻辑表头行，用于保守识别跨页续表。"""
    return tuple(
        _norm_text(cell.text)
        for cell in sorted(
            (cell for cell in table.cells if cell.start_row == 0 and cell.text.strip()),
            key=lambda cell: cell.start_col,
        )
    )


def _table_boundary_pair(
    first: ParsedTable,
    second: ParsedTable,
    blocks_by_id: dict[object, DocumentBlock],
) -> bool:
    first_block = blocks_by_id.get(first.block_id)
    second_block = blocks_by_id.get(second.block_id)
    if first_block is None or second_block is None:
        return False
    if first.page_number is None or second.page_number != first.page_number + 1:
        return False
    if first_block.anchor.bbox is None or second_block.anchor.bbox is None:
        return False
    first_height = first_block.anchor.page_height
    second_height = second_block.anchor.page_height
    if not first_height or not second_height:
        return False
    return (
        first_block.anchor.bbox[3] >= first_height * 0.65
        and second_block.anchor.bbox[1] <= second_height * 0.35
    )


def _merge_table_pair(
    first: ParsedTable,
    second: ParsedTable,
    blocks_by_id: dict[object, DocumentBlock],
) -> tuple[ParsedTable, DocumentBlock] | None:
    if not _table_boundary_pair(first, second, blocks_by_id):
        return None
    if not first.cells or not second.cells or first.num_cols != second.num_cols:
        return None
    first_signature = _table_signature(first)
    if not first_signature or first_signature != _table_signature(second):
        return None
    if first.caption and second.caption and _norm_text(first.caption) != _norm_text(second.caption):
        return None

    first_rows = first.num_rows or max(
        cell.start_row + cell.row_span for cell in first.cells
    )
    merged_cells = list(first.cells)
    for cell in second.cells:
        if cell.start_row == 0:
            continue
        merged_cells.append(
            cell.model_copy(update={"start_row": cell.start_row + first_rows - 1})
        )
    normalized = normalize_table_cells(
        merged_cells,
        declared_cols=max(first.num_cols or 0, second.num_cols or 0),
    )
    merged_table = first.model_copy(
        update={
            "cells": list(normalized.cells),
            "markdown": cells_to_markdown(normalized.cells),
            "num_rows": normalized.num_rows,
            "num_cols": normalized.num_cols,
            "metadata": {
                **first.metadata,
                "merged_fragments": [
                    *first.metadata.get("merged_fragments", [first.table_id]),
                    second.table_id,
                ],
                "dropped_repeated_header_rows": 1,
            },
        }
    )
    first_block = blocks_by_id[first.block_id]
    merged_markdown = merged_table.markdown or first_block.markdown
    return merged_table, first_block.model_copy(
        update={
            "text": merged_markdown,
            "markdown": merged_markdown,
            "metadata": {**first_block.metadata, "merged_table_fragments": [second.table_id]},
        }
    )


def _merge_adjacent_table_fragments(
    blocks: list[DocumentBlock],
    tables: list[ParsedTable],
    markdown: str,
) -> tuple[list[DocumentBlock], list[ParsedTable], list[str], str]:
    """只合并证据充分的相邻跨页续表。"""
    blocks_by_id = {block.id: block for block in blocks}
    positions = {block.id: index for index, block in enumerate(blocks)}
    result_tables: list[ParsedTable] = []
    removed_block_ids: set[object] = set()
    warnings: list[str] = []
    index = 0
    while index < len(tables):
        current = tables[index]
        if index + 1 < len(tables):
            following = tables[index + 1]
            if positions.get(following.block_id) == positions.get(current.block_id, -2) + 1:
                first_block = blocks_by_id.get(current.block_id)
                following_block = blocks_by_id.get(following.block_id)
                can_project = bool(
                    first_block
                    and following_block
                    and first_block.markdown
                    and following_block.markdown
                    and first_block.markdown in markdown
                    and following_block.markdown in markdown
                )
                merged = (
                    _merge_table_pair(current, following, blocks_by_id)
                    if can_project
                    else None
                )
                if merged is not None:
                    merged_table, merged_block = merged
                    markdown = markdown.replace(
                        first_block.markdown, merged_block.markdown, 1
                    ).replace(following_block.markdown, "", 1)
                    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
                    blocks_by_id[current.block_id] = merged_block
                    removed_block_ids.add(following.block_id)
                    result_tables.append(merged_table)
                    warnings.append(
                        f"{current.table_id}: 合并跨页续表片段 {following.table_id}。"
                    )
                    index += 2
                    continue
        result_tables.append(current)
        index += 1
    result_blocks = [
        blocks_by_id[block.id]
        for block in blocks
        if block.id not in removed_block_ids
    ]
    return result_blocks, result_tables, warnings, markdown


def _reorder_two_column_pages(
    blocks: list[DocumentBlock],
) -> tuple[list[DocumentBlock], list[str]]:
    """只对 bbox 完整且存在明显分界的页面做左栏到右栏排序。"""
    result = list(blocks)
    warnings: list[str] = []
    pages: dict[int, list[tuple[int, DocumentBlock]]] = {}
    for index, block in enumerate(blocks):
        if block.anchor.page_number is not None:
            pages.setdefault(block.anchor.page_number, []).append((index, block))

    for page_number, entries in pages.items():
        if len(entries) < 4 or any(entry[1].anchor.bbox is None for entry in entries):
            continue
        page_width = next(
            (entry[1].anchor.page_width for entry in entries if entry[1].anchor.page_width),
            None,
        )
        if not page_width:
            continue
        if any(
            entry[1].anchor.bbox[2] - entry[1].anchor.bbox[0] > page_width * 0.78
            for entry in entries
        ):
            continue
        by_center = sorted(
            entries,
            key=lambda entry: (entry[1].anchor.bbox[0] + entry[1].anchor.bbox[2]) / 2,
        )
        gaps = [
            (
                (by_center[index + 1][1].anchor.bbox[0] + by_center[index + 1][1].anchor.bbox[2]) / 2
                - (by_center[index][1].anchor.bbox[0] + by_center[index][1].anchor.bbox[2]) / 2,
                index,
            )
            for index in range(len(by_center) - 1)
        ]
        gap, split_index = max(gaps, default=(0.0, 0))
        left = by_center[: split_index + 1]
        right = by_center[split_index + 1 :]
        if gap < page_width * 0.18 or len(left) < 2 or len(right) < 2:
            continue
        ordered = sorted(left, key=lambda entry: (entry[1].anchor.bbox[1], entry[0]))
        ordered += sorted(right, key=lambda entry: (entry[1].anchor.bbox[1], entry[0]))
        for (target_index, _), (_, block) in zip(sorted(entries), ordered):
            result[target_index] = block
        warnings.append(f"page {page_number}: 按左栏到右栏重排。")
    return result, warnings


def normalize_parsed_document(
    document: ParsedDocument,
    *,
    parser_label: str,
    source_path: Path | None = None,
) -> ParsedDocument:
    """归一 blocks 顺序和表格逻辑网格，保留正文与根 Markdown 原值。"""

    ordered_blocks = sorted(
        enumerate(document.blocks),
        key=lambda item: (
            item[1].order_index if item[1].order_index is not None else 10**9,
            item[0],
        ),
    )
    blocks = [
        block.model_copy(update={"order_index": index})
        for index, (_, block) in enumerate(ordered_blocks)
    ]
    blocks, block_id_map = _stabilize_block_ids(
        document,
        blocks,
        parser_label=parser_label,
    )
    warnings = list(document.warnings)
    formula_result = normalize_formula_evidence(
        blocks,
        document.markdown,
        parser_label=parser_label,
        source_path=source_path,
    )
    blocks = formula_result.blocks
    markdown = formula_result.markdown
    warnings.extend(formula_result.warnings)
    tables: list[ParsedTable] = []
    table_warnings: list[str] = []
    for table in document.tables:
        table = table.model_copy(
            update={"block_id": block_id_map.get(table.block_id, table.block_id)}
        )
        normalized = normalize_table_cells(
            table.cells,
            declared_rows=table.num_rows,
            declared_cols=table.num_cols,
        )
        table_warnings.extend(
            f"{parser_label}:{table.table_id}: {warning}"
            for warning in normalized.warnings
        )
        tables.append(
            table.model_copy(
                update={
                    "cells": list(normalized.cells),
                    "num_rows": normalized.num_rows,
                    "num_cols": normalized.num_cols,
                }
            )
        )
    warnings.extend(table_warnings)
    blocks, tables, merge_warnings, markdown = _merge_adjacent_table_fragments(
        blocks, tables, markdown
    )
    warnings.extend(merge_warnings)
    blocks, reading_order_warnings = _reorder_two_column_pages(blocks)
    warnings.extend(reading_order_warnings)
    parameters = dict(document.provenance.parameters)
    parameters["normalization"] = {
        "version": "normalization-v1",
        "parser": parser_label,
        "table_count": len(tables),
        "warning_count": len(formula_result.warnings)
        + len(table_warnings)
        + len(merge_warnings)
        + len(reading_order_warnings),
        "merged_fragment_count": len(merge_warnings),
        "reordered_page_count": len(reading_order_warnings),
        "stable_block_id_version": "uuid5-source-v1",
        "formula_token_guard_version": "formula-token-guard-v1",
        "formula_recovered_count": formula_result.recovered_count,
        "formula_incomplete_count": formula_result.incomplete_count,
        "formula_placeholder_count": formula_result.placeholder_count,
    }
    provenance = document.provenance.model_copy(update={"parameters": parameters})
    assets = [
        asset.model_copy(
            update={
                "referenced_by_block_ids": [
                    _remap_block_ref(block_id, block_id_map)
                    for block_id in asset.referenced_by_block_ids
                ]
            }
        )
        for asset in document.assets
    ]
    return document.model_copy(
        update={
            "markdown": markdown,
            "blocks": blocks,
            "tables": tables,
            "assets": assets,
            "warnings": warnings,
            "provenance": provenance,
        }
    )
