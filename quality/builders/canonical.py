"""Canonical Document 构建（M1 最小版：blocks 投影）。

M4 将扩展 table_bindings / relations；D-07：content 默认保留输入 markdown。
"""

from __future__ import annotations

from uuid import UUID

from document_parser.core.contracts import (
    CanonicalBlock,
    CanonicalDocument,
    CanonicalSourceLocator,
    QualityCapabilityState,
)

from quality.evidence.context import EvidenceContext
from quality.ids import block_id

QUALITY_PIPELINE_VERSION = "quality-mvp-0.1.0"


def _document_key(parsed) -> str:
    """稳定 document key：优先 source_sha256，其次 document_id。"""
    return parsed.source_sha256 or str(parsed.document_id)


def build_canonical_document(context: EvidenceContext) -> CanonicalDocument:
    """从 EvidenceContext 构建最小 CanonicalDocument（blocks 投影）。"""
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
    return CanonicalDocument(
        document_id=context.parsed.document_id,
        blocks=blocks,
        table_bindings=[],
        relations=[],
        metadata={"quality_pipeline_version": QUALITY_PIPELINE_VERSION},
    )
