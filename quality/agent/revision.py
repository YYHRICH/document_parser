"""单文档 revision 存储、候选物化和结构 Patch 应用。"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import re
from uuid import UUID

from document_parser.core.contracts import ParsedDocument, TableCell

from quality.agent.markdown_projection import (
    MarkdownProjectionError,
    build_markdown_projection,
    replace_block_source,
)
from quality.agent.models import CandidateValidation, RelationPatch, RepairOperation, RepairedDocumentCandidate
from quality.packaging.hashing import sha256_bytes, stable_json_bytes


@dataclass(frozen=True)
class DocumentRevision:
    """不可变的文档工作版本。"""

    revision_id: str
    document: ParsedDocument
    parent_revision_id: str | None = None
    attempt: int = 0
    relation_overrides: tuple[RelationPatch, ...] = ()


@dataclass
class InMemoryRevisionStore:
    """单文档质量修复 Agent 开发期 revision store；生产期可替换为持久化实现。"""

    _revisions: dict[str, DocumentRevision] = field(default_factory=dict)
    _attempts: list[tuple[str, RepairedDocumentCandidate, CandidateValidation]] = field(
        default_factory=list
    )

    def open(self, document: ParsedDocument) -> DocumentRevision:
        revision = DocumentRevision(
            revision_id=document_digest(document),
            document=document,
        )
        self._revisions[revision.revision_id] = revision
        return revision

    def record_attempt(
        self,
        revision: DocumentRevision,
        candidate: RepairedDocumentCandidate,
        validation: CandidateValidation,
    ) -> None:
        self._attempts.append((revision.revision_id, candidate, validation))

    def commit(
        self,
        revision: DocumentRevision,
        document: ParsedDocument,
        candidate: RepairedDocumentCandidate,
        relation_overrides: tuple[RelationPatch, ...] = (),
    ) -> DocumentRevision:
        next_revision_id = document_digest(document, relation_overrides)
        if next_revision_id == revision.revision_id:
            return revision
        next_revision = DocumentRevision(
            revision_id=next_revision_id,
            document=document,
            parent_revision_id=revision.revision_id,
            attempt=revision.attempt + 1,
            relation_overrides=relation_overrides,
        )
        self._revisions[next_revision.revision_id] = next_revision
        return next_revision

    @property
    def attempts(self) -> tuple[tuple[str, RepairedDocumentCandidate, CandidateValidation], ...]:
        return tuple(self._attempts)


def document_digest(
    document: ParsedDocument,
    relation_overrides: tuple[RelationPatch, ...] = (),
) -> str:
    """对文档及已验证关系覆盖做稳定摘要，作为 revision ID。"""

    if not relation_overrides:
        return sha256_bytes(stable_json_bytes(document))
    payload = {
        "document": document.model_dump(mode="json"),
        "relation_overrides": [
            patch.model_dump(mode="json") for patch in relation_overrides
        ],
    }
    return sha256_bytes(stable_json_bytes(payload))


def materialize_candidate(
    document: ParsedDocument,
    candidate: RepairedDocumentCandidate,
) -> ParsedDocument:
    """在当前文档上应用候选的文档结构 Patch。"""

    materialized, _ = materialize_revision_candidate(
        DocumentRevision(revision_id="materialize", document=document), candidate
    )
    return materialized


def materialize_revision_candidate(
    revision: DocumentRevision,
    candidate: RepairedDocumentCandidate,
) -> tuple[ParsedDocument, tuple[RelationPatch, ...]]:
    """同时物化文档结构、资源归属和关系覆盖。"""

    source_document = revision.document
    document = source_document
    tables = list(document.tables)
    assets = list(document.assets)
    relation_overrides = list(revision.relation_overrides)
    root_affecting_patch = False

    for block_id, markdown in candidate.block_markdown.items():
        document = _replace_block_markdown(document, block_id, markdown)
        root_affecting_patch = True

    for operation in candidate.operations:
        if operation.operation == "update_block_markdown":
            document = _replace_block_markdown(
                document, operation.block_id, operation.markdown or ""
            )
            root_affecting_patch = True
        elif operation.operation == "move_block":
            document = _move_block(document, operation)
            root_affecting_patch = True
        elif operation.operation == "update_heading_level":
            document = _update_heading_level(document, operation)
            root_affecting_patch = True
        elif operation.operation == "remove_block":
            document = _remove_block(document, operation)
            root_affecting_patch = True
        elif operation.operation == "replace_table_cells":
            _replace_table_cells(tables, operation)
        elif operation.operation == "update_table_cell_layout":
            _update_table_cell_layout(tables, operation)
        elif operation.operation in {"upsert_relation", "remove_relation"}:
            _apply_relation_patch(relation_overrides, operation.relation)
        elif operation.operation == "update_asset_references":
            _update_asset_references(assets, operation)
            _sync_asset_relation_patches(
                relation_overrides, source_document, operation
            )

    markdown = document.markdown
    if candidate.repaired_markdown is not None:
        if root_affecting_patch:
            if candidate.repaired_markdown not in {
                source_document.markdown,
                document.markdown,
            }:
                raise MarkdownProjectionError(
                    "repaired_markdown 与宿主根据 block operations 生成的根 Markdown 冲突。"
                )
        else:
            markdown = candidate.repaired_markdown

    materialized = document.model_copy(
        update={"markdown": markdown, "tables": tables, "assets": assets}
    )
    return materialized, tuple(relation_overrides)


def _apply_relation_patch(
    relation_overrides: list[RelationPatch], patch: RelationPatch | None
) -> None:
    if patch is None:
        raise ValueError("关系操作缺少 relation。")
    relation_overrides[:] = [
        existing
        for existing in relation_overrides
        if existing.key() != patch.key()
    ]
    # remove 也必须保留为 tombstone，才能遮蔽规则重新推导出的关系。
    relation_overrides.append(patch)


def _update_asset_references(assets, operation: RepairOperation) -> None:
    for index, asset in enumerate(assets):
        if asset.path == operation.asset_path:
            assets[index] = asset.model_copy(
                update={"referenced_by_block_ids": list(operation.referenced_by_block_ids)}
            )
            return
    raise ValueError(f"未知 asset path：{operation.asset_path}")


def _sync_asset_relation_patches(
    relation_overrides: list[RelationPatch],
    document: ParsedDocument,
    operation: RepairOperation,
) -> None:
    current = next(
        (asset for asset in document.assets if asset.path == operation.asset_path), None
    )
    if current is None:
        raise ValueError(f"未知 asset path：{operation.asset_path}")
    old_ids = set(current.referenced_by_block_ids)
    new_ids = set(operation.referenced_by_block_ids)
    for block_id in old_ids - new_ids:
        _apply_relation_patch(
            relation_overrides,
            RelationPatch(
                action="remove",
                relation_type="asset_referenced_by",
                from_id=operation.asset_path or "",
                to_id=block_id,
            ),
        )
    for block_id in new_ids - old_ids:
        _apply_relation_patch(
            relation_overrides,
            RelationPatch(
                action="upsert",
                relation_type="asset_referenced_by",
                from_id=operation.asset_path or "",
                to_id=block_id,
            ),
        )

def _replace_block_markdown(
    document: ParsedDocument,
    block_id: str | None,
    markdown: str,
) -> ParsedDocument:
    index = _find_block_index(document.blocks, block_id)
    block = document.blocks[index]
    if block.markdown == markdown:
        return document
    updated_markdown = replace_block_source(document, str(block.id), markdown)
    blocks = list(document.blocks)
    blocks[index] = block.model_copy(update={"markdown": markdown})
    return document.model_copy(
        update={"markdown": updated_markdown, "blocks": blocks}
    )


def _update_heading_level(
    document: ParsedDocument,
    operation: RepairOperation,
) -> ParsedDocument:
    index = _find_block_index(document.blocks, operation.block_id)
    block = document.blocks[index]
    if block.kind.value != "heading":
        raise ValueError(f"block {operation.block_id} 不是标题块。")
    heading_level = operation.heading_level or 1
    body = re.sub(r"^\s{0,3}#{1,6}(?:[ \t]+|$)", "", block.markdown, count=1)
    markdown = f"{'#' * heading_level} {body.lstrip()}"
    updated = _replace_block_markdown(document, operation.block_id, markdown)
    blocks = list(updated.blocks)
    updated_index = _find_block_index(blocks, operation.block_id)
    blocks[updated_index] = blocks[updated_index].model_copy(
        update={"heading_level": heading_level}
    )
    return updated.model_copy(update={"blocks": blocks})


def _remove_block(
    document: ParsedDocument,
    operation: RepairOperation,
) -> ParsedDocument:
    index = _find_block_index(document.blocks, operation.block_id)
    block = document.blocks[index]
    projection = build_markdown_projection(document)
    span = projection.spans.get(str(block.id))
    markdown = document.markdown
    if span is not None:
        span = projection.require_source(str(block.id))
        markdown = document.markdown[: span.edit_start] + document.markdown[span.edit_end :]
    else:
        remaining_blocks = list(document.blocks)
        remaining_blocks.pop(index)
        projected_remaining = document.model_copy(
            update={"blocks": _reindex_blocks(remaining_blocks)}
        )
        remaining_projection = build_markdown_projection(projected_remaining)
        represented_duplicate = any(
            other.id != block.id
            and other.markdown == block.markdown
            and str(other.id) in remaining_projection.spans
            for other in remaining_blocks
        )
        if not represented_duplicate:
            raise MarkdownProjectionError(
                f"block {block.id} 无法映射，且根 Markdown 中没有已映射的完全重复副本。"
            )
    blocks = list(document.blocks)
    blocks.pop(index)
    blocks = _reindex_blocks(blocks)
    return document.model_copy(update={"markdown": markdown, "blocks": blocks})


def _move_block(
    document: ParsedDocument,
    operation: RepairOperation,
) -> ParsedDocument:
    source_index = _find_block_index(document.blocks, operation.block_id)
    projection = build_markdown_projection(document)
    source_span = projection.require_source(operation.block_id or "")
    target_span = (
        None
        if operation.before_block_id is None
        else projection.require_source(operation.before_block_id)
    )
    if operation.before_block_id == operation.block_id:
        return document

    segment = document.markdown[source_span.edit_start : source_span.edit_end]
    without_source = (
        document.markdown[: source_span.edit_start]
        + document.markdown[source_span.edit_end :]
    )
    if target_span is None:
        insertion_at = len(without_source)
    else:
        insertion_at = target_span.edit_start
        if target_span.edit_start > source_span.edit_start:
            insertion_at -= source_span.edit_end - source_span.edit_start
    markdown = _insert_source_segment(without_source, insertion_at, segment)

    blocks = list(document.blocks)
    block = blocks.pop(source_index)
    if operation.before_block_id is None:
        blocks.append(block)
    else:
        target_index = _find_block_index(blocks, operation.before_block_id)
        blocks.insert(target_index, block)
    return document.model_copy(
        update={"markdown": markdown, "blocks": _reindex_blocks(blocks)}
    )


def _insert_source_segment(markdown: str, index: int, segment: str) -> str:
    prefix = markdown[:index]
    suffix = markdown[index:]
    insertion = segment
    if prefix and not prefix.endswith(("\n", "\r")) and not insertion.startswith(
        ("\n", "\r")
    ):
        insertion = "\n\n" + insertion
    if suffix and not insertion.endswith(("\n", "\r")) and not suffix.startswith(
        ("\n", "\r")
    ):
        insertion += "\n\n"
    return prefix + insertion + suffix


def _reindex_blocks(blocks):
    return [
        block.model_copy(update={"order_index": index})
        for index, block in enumerate(blocks)
    ]


def _replace_table_cells(tables, operation: RepairOperation) -> None:
    for index, table in enumerate(tables):
        if table.table_id != operation.table_id:
            continue
        cells = [TableCell.model_validate(cell.model_dump()) for cell in operation.cells]
        num_rows = max(
            (cell.start_row + cell.row_span for cell in cells),
            default=0,
        )
        num_cols = max(
            (cell.start_col + cell.col_span for cell in cells),
            default=0,
        )
        tables[index] = table.model_copy(
            update={"cells": cells, "num_rows": num_rows, "num_cols": num_cols}
        )
        return
    raise ValueError(f"未知 table ID：{operation.table_id}")


def _update_table_cell_layout(tables, operation: RepairOperation) -> None:
    """只更新已有 cell 的布局字段，正文始终从源表复制。"""

    for index, table in enumerate(tables):
        if table.table_id != operation.table_id:
            continue
        cells = list(table.cells)
        for patch in operation.cell_layout_patches:
            if patch.cell_index >= len(cells):
                raise ValueError(
                    f"table {operation.table_id} 的 cell_index 越界：{patch.cell_index}"
                )
            current = cells[patch.cell_index]
            if patch.expected_text_sha256 is not None:
                actual_hash = sha256(
                    current.text.encode("utf-8", errors="replace")
                ).hexdigest()
                if actual_hash != patch.expected_text_sha256:
                    raise ValueError(
                        f"table {operation.table_id} 的 cell {patch.cell_index} "
                        "正文指纹与候选不一致。"
                    )
            cells[patch.cell_index] = current.model_copy(
                update={
                    "start_row": patch.start_row,
                    "start_col": patch.start_col,
                    "row_span": patch.row_span,
                    "col_span": patch.col_span,
                    "column_header": patch.column_header,
                    "row_header": patch.row_header,
                }
            )
        num_rows = max(
            (cell.start_row + cell.row_span for cell in cells),
            default=0,
        )
        num_cols = max(
            (cell.start_col + cell.col_span for cell in cells),
            default=0,
        )
        tables[index] = table.model_copy(
            update={"cells": cells, "num_rows": num_rows, "num_cols": num_cols}
        )
        return
    raise ValueError(f"未知 table ID：{operation.table_id}")


def _find_block_index(blocks, block_id: str | None) -> int:
    if not block_id:
        raise ValueError("结构操作缺少 block_id。")
    for index, block in enumerate(blocks):
        if str(block.id) == block_id:
            return index
    raise ValueError(f"未知 block ID：{block_id}")


def parse_block_id(value: str) -> UUID | None:
    """把候选 block ID 转成 UUID；非法值由验证器报告。"""

    try:
        return UUID(value)
    except (ValueError, TypeError, AttributeError):
        return None
