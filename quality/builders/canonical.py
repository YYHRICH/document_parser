"""Canonical Document 构建：blocks、relations 和 table bindings 的确定性投影。

D-07：content 默认保留输入 markdown；只有通过验证的格式修复才允许变化。
"""

from __future__ import annotations

from uuid import UUID

from document_parser.core.contracts import (
    CanonicalBlock,
    CanonicalDocument,
    CanonicalRelation,
    CanonicalSourceLocator,
    QualityCapabilityState,
    TableFieldBinding,
)

from quality.evidence.context import EvidenceContext
from quality.ids import binding_id, block_id, relation_id

QUALITY_PIPELINE_VERSION = "quality-mvp-0.1.0"


def _document_key(parsed) -> str:
    """稳定 document key：优先 source_sha256，其次 document_id。"""
    return parsed.source_sha256 or str(parsed.document_id)


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
    # 关系：from_id/to_id 是 ParsedDocument block UUID，映射到 canonical block_id
    block_map = _id_map(context)
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
                            **({"value_sha256": ref.value_sha256} if ref.value_sha256 else {}),
                        }
                        for ref in candidate.evidence_refs
                    ],
                },
            )
        )
    # 表格字段绑定
    block_map = _id_map(context)
    table_bindings: list[TableFieldBinding] = []
    for candidate in binding_candidates or ():
        canonical_block_id = block_map.get(candidate.block_id)
        if canonical_block_id is None:
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
                column_path=list(candidate.column_path),
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
                            **({"value_sha256": ref.value_sha256} if ref.value_sha256 else {}),
                        }
                        for ref in candidate.evidence_refs
                    ],
                },
            )
        )
    return CanonicalDocument(
        document_id=context.parsed.document_id,
        blocks=blocks,
        table_bindings=table_bindings,
        relations=relations,
        metadata={"quality_pipeline_version": QUALITY_PIPELINE_VERSION},
    )


def _id_map(context: EvidenceContext) -> dict:
    """parsed block UUID -> canonical block_id（relation 端点映射用）。"""
    doc_key = _document_key(context.parsed)
    result = {
        str(b.id): block_id(
            doc_key,
            b.source_block_id or str(b.id),
            b.order_index or 0,
            block_uuid=str(b.id),
        )
        for b in context.parsed.blocks
    }
    result.update({asset.path: f"asset:{asset.path}" for asset in context.parsed.assets})
    return result
