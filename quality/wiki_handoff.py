"""从最终 QualityPackage 生成 Wiki 侧的可追溯交接产物。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from document_parser.core.contracts import (
    QualityPackage,
    WikiCitation,
    WikiChunk,
    WikiHandoff,
)


def _issue_warning(issue: Any) -> str:
    return f"{issue.severity.value}:{issue.category}: {issue.message}"


def build_wiki_handoff(package: QualityPackage) -> WikiHandoff:
    """将质量 Agent 的最终包投影为 Wiki 可消费的证据链。"""

    citations: list[WikiCitation] = []
    chunks: list[WikiChunk] = []
    bindings_by_block: dict[str, list[Any]] = {}
    for binding in package.canonical_document.table_bindings:
        bindings_by_block.setdefault(binding.block_id, []).append(binding)

    for block in package.canonical_document.blocks:
        locator = block.source_locator
        block_citation_id = f"block:{block.block_id}"
        citations.append(
            WikiCitation(
                citation_id=block_citation_id,
                canonical_block_id=block.block_id,
                source_block_id=locator.source_block_id,
                page_number=locator.page_number,
                bbox=locator.bbox,
                provenance_status=locator.provenance_status,
            )
        )
        citation_ids = [block_citation_id]
        block_bindings = bindings_by_block.get(block.block_id, [])
        for binding in block_bindings:
            binding_citation_id = f"binding:{binding.binding_id}"
            cell_key = binding.evidence.get("cell_key")
            citations.append(
                WikiCitation(
                    citation_id=binding_citation_id,
                    canonical_block_id=binding.block_id,
                    source_block_id=binding.source_locator.source_block_id,
                    page_number=binding.source_locator.page_number,
                    bbox=binding.source_locator.bbox,
                    table_id=binding.table_id,
                    table_cell=cell_key if isinstance(cell_key, str) else None,
                    provenance_status=binding.status,
                    evidence={
                        **binding.evidence,
                        "row_key": binding.row_key,
                        "column_path": binding.column_path,
                        "value": binding.value,
                    },
                )
            )
            citation_ids.append(binding_citation_id)

        metadata = dict(block.metadata)
        if block_bindings:
            metadata["table_binding_ids"] = [binding.binding_id for binding in block_bindings]
        chunks.append(
            WikiChunk(
                chunk_id=f"block:{block.block_id}",
                kind=block.kind,
                order_index=block.order_index,
                content=block.content,
                citation_ids=citation_ids,
                evidence_status=locator.provenance_status,
                metadata=metadata,
            )
        )

    warnings = [_issue_warning(issue) for issue in package.quality_report.issues]
    return WikiHandoff(
        document_id=package.document_id,
        quality_state=package.quality_report.state,
        optimized_markdown=package.optimized_markdown,
        chunks=chunks,
        citations=citations,
        warnings=warnings,
        metadata={
            "quality_report_contract_version": package.quality_report.contract_version,
            "chunk_count": len(chunks),
            "citation_count": len(citations),
            "table_binding_count": len(package.canonical_document.table_bindings),
        },
    )


def write_wiki_handoff(
    handoff: WikiHandoff,
    output_dir: Path,
    *,
    replace_existing: bool = False,
) -> Path:
    """写出 Wiki 交接的完整文档和两个便捷索引文件。"""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "wiki_document.json": handoff.model_dump_json(indent=2) + "\n",
        "wiki_chunks.json": json.dumps(
            [chunk.model_dump(mode="json") for chunk in handoff.chunks],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "wiki_citations.json": json.dumps(
            [citation.model_dump(mode="json") for citation in handoff.citations],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    }
    for name, content in files.items():
        path = output_dir / name
        if path.exists() and not replace_existing:
            raise FileExistsError(f"Wiki 交接产物已存在: {path}")
        path.write_text(content, encoding="utf-8")
    return output_dir
