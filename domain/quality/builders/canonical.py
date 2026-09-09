"""将修复后的统一文档投影为 Wiki 可消费的规范文档图。"""

from __future__ import annotations

from uuid import UUID

from document_parser.domain.model.contracts import (
    CanonicalBlock,
    CanonicalDocument,
    CanonicalRelation,
    CanonicalSourceLocator,
    CanonicalTable,
    ParsedTable,
    QualityCapabilityState,
    TableCell,
    TableFieldBinding,
    TableGridSlot,
    TableSlotKind,
)

from ..evidence.context import EvidenceContext
from ..ids import binding_id, block_id, relation_id
from ..rules.tables import analyze_grid
from ..table_storage import TABLE_INDEX_NAME, uses_external_table_index

QUALITY_PIPELINE_VERSION = "quality-structured-repair"


def _document_key(parsed) -> str:
    """稳定 document key：优先 source_sha256，其次 document_id。"""
    return parsed.source_sha256 or str(parsed.document_id)


def _canonical_cells(table: ParsedTable) -> list[TableCell]:
    cells: list[TableCell] = []
    for cell in table.cells:
        cell_id = cell.cell_id or f"{table.table_id}:r{cell.start_row}c{cell.start_col}"
        roles = list(cell.roles)
        if cell.column_header and "column_header" not in roles:
            roles.append("column_header")
        if cell.row_header and "row_header" not in roles:
            roles.append("row_header")
        cells.append(
            cell.model_copy(
                update={
                    "cell_id": cell_id,
                    "raw_value": cell.raw_value,
                    "display_value": cell.display_value if cell.display_value is not None else cell.text,
                    "normalized_value": (
                        cell.normalized_value
                        if cell.normalized_value is not None
                        else cell.text.strip()
                    ),
                    "roles": roles,
                }
            )
        )
    return cells


def _derived_grid(table: ParsedTable, cells: list[TableCell]) -> list[list[TableGridSlot]]:
    if table.grid:
        return [list(row) for row in table.grid]
    rows = table.num_rows or max((cell.start_row + cell.row_span for cell in cells), default=0)
    cols = table.num_cols or max((cell.start_col + cell.col_span for cell in cells), default=0)
    if rows == 0 or cols == 0:
        return []
    slots: list[list[TableGridSlot | None]] = [[None for _ in range(cols)] for _ in range(rows)]
    for cell in cells:
        assert cell.cell_id is not None
        for row in range(cell.start_row, cell.start_row + cell.row_span):
            for col in range(cell.start_col, cell.start_col + cell.col_span):
                if row >= rows or col >= cols or slots[row][col] is not None:
                    return []
                slots[row][col] = TableGridSlot(
                    kind=TableSlotKind.ORIGIN,
                    cell_id=cell.cell_id,
                ) if (row, col) == (cell.start_row, cell.start_col) else TableGridSlot(
                    kind=TableSlotKind.COVERED,
                    origin_cell_id=cell.cell_id,
                )
    if any(slot is None for row in slots for slot in row):
        return []
    return [[slot for slot in row if slot is not None] for row in slots]


def build_canonical_document(
    context: EvidenceContext,
    relation_candidates: tuple | None = None,
    binding_candidates: tuple | None = None,
) -> CanonicalDocument:
    """从 EvidenceContext 构建 CanonicalDocument（blocks + relations + bindings）。"""
    doc_key = _document_key(context.parsed)
    blocks: list[CanonicalBlock] = []
    for block in context.ordered_blocks():
        anchor = block.anchor
        source_locator = CanonicalSourceLocator(
            source_block_id=block.source_block_id or "",
            page_number=anchor.page_number,
            bbox=anchor.bbox,
            bbox_granularity=anchor.bbox_granularity,
            container=anchor.container,
            container_name=anchor.container_name,
            cell_ref=anchor.cell_ref,
            range_ref=anchor.range_ref,
            table_cell=anchor.table_cell,
            provenance_status=(
                QualityCapabilityState.VERIFIED
                if block.source_block_id and (anchor.page_number is not None or anchor.bbox is not None)
                else QualityCapabilityState.INFERRED
            ),
        )
        metadata: dict = {}
        if block.heading_level is not None:
            metadata["heading_level"] = block.heading_level
        if block.kind.value == "table" and block.metadata.get("table_id"):
            metadata["table_id"] = block.metadata["table_id"]
        blocks.append(
            CanonicalBlock(
                block_id=block_id(
                    doc_key,
                    block.source_block_id or str(block.id),
                    block.order_index or 0,
                    block_uuid=str(block.id),
                ),
                kind=block.kind.value,
                order_index=block.order_index if block.order_index is not None else 0,
                content=block.markdown,  # D-07：默认保留输入 markdown
                source_locator=source_locator,
                metadata=metadata,
            )
        )
    # 规范表格：保存真实网格、span、视图语义和来源；Markdown 只是派生表示。
    block_map = _id_map(context)
    parsed_table_cells = {
        table.table_id: {
            cell.cell_id or f"{table.table_id}:r{cell.start_row}c{cell.start_col}"
            for cell in table.cells
        }
        for table in context.parsed.tables
    }
    canonical_tables: list[CanonicalTable] = []
    for table in context.parsed.tables:
        canonical_block_id = block_map.get(str(table.block_id))
        block = context.block(str(table.block_id))
        if canonical_block_id is None:
            continue
        cells = _canonical_cells(table)
        external_index = uses_external_table_index(table)
        grid = [] if external_index else _derived_grid(table, cells)
        analysis = analyze_grid(table)
        rows = table.num_rows or max((cell.start_row + cell.row_span for cell in cells), default=0)
        cols = table.num_cols or max((cell.start_col + cell.col_span for cell in cells), default=0)
        source_locator = CanonicalSourceLocator(
            source_block_id=block.source_block_id if block and block.source_block_id else "",
            page_number=table.page_number,
            bbox=table.bbox,
            bbox_granularity="table" if table.bbox is not None else None,
            container=table.source_container,
            container_name=table.source_container_name,
            range_ref=table.source_range,
            provenance_status=(
                QualityCapabilityState.VERIFIED
                if cells and (grid or (external_index and analysis.valid))
                else QualityCapabilityState.INFERRED
            ),
        )
        parent_reference_valid = (
            table.parent_table_id is None
            or (
                table.parent_table_id in parsed_table_cells
                and table.parent_cell_id in parsed_table_cells[table.parent_table_id]
            )
        )
        table_metadata = dict(table.metadata)
        if external_index:
            table_metadata["table_storage"] = {
                "mode": "sqlite",
                "file": TABLE_INDEX_NAME,
                "cell_count": len(cells),
                "inline_cells": False,
                "inline_grid": False,
                "inline_bindings": False,
            }
        if not parent_reference_valid:
            table_metadata["invalid_parent_reference"] = {
                "parent_table_id": table.parent_table_id,
                "parent_cell_id": table.parent_cell_id,
            }
        canonical_tables.append(
            CanonicalTable(
                table_id=table.table_id,
                block_id=canonical_block_id,
                table_kind=table.table_kind,
                source_locator=source_locator,
                num_rows=rows,
                num_cols=cols,
                header_rows=table.header_rows,
                header_row_indices=list(analysis.header_rows),
                title_row_indices=list(analysis.title_rows),
                header_state=(
                    QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                    if not analysis.valid
                    else QualityCapabilityState.INFERRED
                    if analysis.header_inferred
                    else QualityCapabilityState.VERIFIED
                ),
                row_header_columns=list(analysis.row_header_columns),
                view_scope=table.view_scope,
                source_has_filter=table.source_has_filter,
                source_row_count=table.source_row_count,
                emitted_row_count=table.emitted_row_count,
                hidden_row_count=table.hidden_row_count,
                cells=cells,
                grid=grid,
                parent_table_id=table.parent_table_id if parent_reference_valid else None,
                parent_cell_id=table.parent_cell_id if parent_reference_valid else None,
                nesting_depth=table.nesting_depth if parent_reference_valid else 0,
                metadata=table_metadata,
            )
        )

    # 关系：from_id/to_id 是 ParsedDocument block UUID，映射到 canonical block_id
    relations: list[CanonicalRelation] = []
    for candidate in relation_candidates or ():
        from_id = block_map.get(candidate.from_id)
        to_id = block_map.get(candidate.to_id)
        if from_id is None or to_id is None:
            continue  # 无法映射的关系不输出（避免悬挂引用）
        relations.append(
            CanonicalRelation(
                relation_id=relation_id(
                    doc_key,
                    candidate.relation_type,
                    from_id,
                    to_id,
                    candidate.marker_key,
                ),
                relation_type=candidate.relation_type,
                from_id=from_id,
                to_id=to_id,
                status=candidate.state,
                evidence={
                    **candidate.evidence,
                    "refs": [
                        {
                            "object_type": ref.object_type,
                            "object_id": ref.object_id,
                            "field_path": ref.field_path,
                        }
                        for ref in candidate.evidence_refs
                    ],
                },
            )
        )
    # 表格字段绑定
    block_map = _id_map(context)
    canonical_table_cells = {
        table.table_id: {cell.cell_id for cell in table.cells if cell.cell_id}
        for table in canonical_tables
    }
    table_bindings: list[TableFieldBinding] = []
    for candidate in binding_candidates or ():
        canonical_block_id = block_map.get(candidate.block_id)
        cell_ids = canonical_table_cells.get(candidate.table_id)
        referenced_cell_ids = {
            *candidate.row_cell_ids,
            *candidate.column_cell_ids,
            *([candidate.value_cell_id] if candidate.value_cell_id else []),
        }
        if (
            canonical_block_id is None
            or cell_ids is None
            or not referenced_cell_ids.issubset(cell_ids)
        ):
            continue
        table_bindings.append(
            TableFieldBinding(
                binding_id=binding_id(
                    doc_key,
                    candidate.table_id,
                    candidate.cell_key or "cell",
                    candidate.row_key,
                    candidate.column_path,
                ),
                table_id=candidate.table_id,
                block_id=canonical_block_id,
                row_key=candidate.row_key,
                row_path=list(candidate.row_path),
                column_path=list(candidate.column_path),
                row_cell_ids=list(candidate.row_cell_ids),
                column_cell_ids=list(candidate.column_cell_ids),
                value_cell_id=candidate.value_cell_id,
                value=candidate.value,
                source_locator=candidate.source_locator,
                status=candidate.source_locator.provenance_status,
                evidence={
                    **candidate.evidence,
                    "refs": [
                        {
                            "object_type": ref.object_type,
                            "object_id": ref.object_id,
                            "field_path": ref.field_path,
                        }
                        for ref in candidate.evidence_refs
                    ],
                },
            )
        )
    return CanonicalDocument(
        document_id=context.parsed.document_id,
        blocks=blocks,
        tables=canonical_tables,
        table_bindings=table_bindings,
        relations=relations,
        metadata={"quality_pipeline_version": QUALITY_PIPELINE_VERSION},
    )


def _id_map(context: EvidenceContext) -> dict:
    """parsed block UUID -> canonical block_id（relation 端点映射用）。"""
    doc_key = _document_key(context.parsed)
    return {
        str(b.id): block_id(
            doc_key,
            b.source_block_id or str(b.id),
            b.order_index or 0,
            block_uuid=str(b.id),
        )
        for b in context.parsed.blocks
    }
