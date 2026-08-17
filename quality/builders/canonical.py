"""Canonical Document 构建（M1 blocks 投影 + M2 relations）。

M4 将扩展 table_bindings；D-07：content 默认保留输入 markdown。
"""

from __future__ import annotations

from uuid import UUID

from document_parser.core.contracts import (
    CanonicalBlock,
    CanonicalDocument,
    CanonicalRelation,
    CanonicalSourceLocator,
    QualityCapabilityState,
)

from quality.evidence.context import EvidenceContext
from quality.ids import block_id, relation_id

QUALITY_PIPELINE_VERSION = "quality-mvp-0.1.0"


def _document_key(parsed) -> str:
    """稳定 document key：优先 source_sha256，其次 document_id。"""
    return parsed.source_sha256 or str(parsed.document_id)


def build_canonical_document(
    context: EvidenceContext,
    relation_candidates: tuple | None = None,
) -> CanonicalDocument:
    """从 EvidenceContext 构建 CanonicalDocument（blocks 投影 + relations）。"""
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
                if block.source_block_id
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
                block_id=block_id(doc_key, block.source_block_id or str(block.id), block.order_index or 0),
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
                    "",
                ),
                relation_type=candidate.relation_type,
                from_id=from_id,
                to_id=to_id,
                status=candidate.state,
                evidence={
                    "refs": [
                        {
                            "object_type": ref.object_type,
                            "object_id": ref.object_id,
                            "field_path": ref.field_path,
                        }
                        for ref in candidate.evidence_refs
                    ]
                },
            )
        )
    return CanonicalDocument(
        document_id=context.parsed.document_id,
        blocks=blocks,
        table_bindings=[],
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
        )
        for b in context.parsed.blocks
    }
