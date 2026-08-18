"""单文档 revision 存储、候选物化和结构 Patch 应用。"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from document_parser.core.contracts import ParsedDocument, TableCell

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
        next_revision = DocumentRevision(
            revision_id=document_digest(document, relation_overrides),
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

    document = revision.document
    blocks = list(document.blocks)
    block_index = {str(block.id): index for index, block in enumerate(blocks)}
    tables = list(document.tables)
    assets = list(document.assets)
    relation_overrides = list(revision.relation_overrides)

    for block_id, markdown in candidate.block_markdown.items():
        index = block_index.get(block_id)
        if index is None:
            raise ValueError(f"未知 block ID：{block_id}")
        blocks[index] = blocks[index].model_copy(update={"markdown": markdown})

    reordered = False
    for operation in candidate.operations:
        if operation.operation == "update_block_markdown":
            _update_block_markdown(blocks, operation)
        elif operation.operation == "move_block":
            _move_block(blocks, operation)
            reordered = True
        elif operation.operation == "update_heading_level":
            _update_heading_level(blocks, operation)
        elif operation.operation == "remove_block":
            _remove_block(blocks, operation)
            reordered = True
        elif operation.operation == "replace_table_cells":
            _replace_table_cells(tables, operation)
        elif operation.operation in {"upsert_relation", "remove_relation"}:
            _apply_relation_patch(relation_overrides, operation.relation)
        elif operation.operation == "update_asset_references":
            _update_asset_references(assets, operation)
            _sync_asset_relation_patches(relation_overrides, document, operation)

    if reordered:
        blocks = [
            block.model_copy(update={"order_index": index})
            for index, block in enumerate(blocks)
        ]

    markdown = (
        document.markdown
        if candidate.repaired_markdown is None
        else candidate.repaired_markdown
    )
    materialized = document.model_copy(
        update={"markdown": markdown, "blocks": blocks, "tables": tables, "assets": assets}
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

def _update_block_markdown(blocks, operation: RepairOperation) -> None:
    index = _find_block_index(blocks, operation.block_id)
    blocks[index] = blocks[index].model_copy(update={"markdown": operation.markdown})


def _update_heading_level(blocks, operation: RepairOperation) -> None:
    index = _find_block_index(blocks, operation.block_id)
    block = blocks[index]
    if block.kind.value != "heading":
        raise ValueError(f"block {operation.block_id} 不是标题块。")
    blocks[index] = block.model_copy(update={"heading_level": operation.heading_level})


def _remove_block(blocks, operation: RepairOperation) -> None:
    index = _find_block_index(blocks, operation.block_id)
    blocks.pop(index)


def _move_block(blocks, operation: RepairOperation) -> None:
    source_index = _find_block_index(blocks, operation.block_id)
    block = blocks.pop(source_index)
    if operation.before_block_id is None:
        blocks.append(block)
        return
    target_index = _find_block_index(blocks, operation.before_block_id)
    blocks.insert(target_index, block)


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
