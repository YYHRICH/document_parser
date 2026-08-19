"""低成本、低风险的确定性质量预修复规则。

这里只放可以由输入结构直接证明的 Patch。无法证明的内容留给 Agent；
规则不修改正文、公式、引用文本或来源定位。
"""

from __future__ import annotations

import re

from document_parser.core.contracts import BlockKind

from quality.agent.models import (
    CandidateEvidenceRef,
    RepairOperation,
    RepairedDocumentCandidate,
)
from quality.agent.revision import DocumentRevision


_NUMBERED_HEADING = re.compile(
    r"^\s*(?P<number>(?:\d+(?:\.\d+)*|[A-Z](?:\.\d+)*))\s*[、.．:\s-]+"
)


def _heading_numbered_level(markdown: str | None, text: str | None) -> int | None:
    value = text or markdown or ""
    value = re.sub(r"^\s*#{1,6}\s*", "", value).strip()
    match = _NUMBERED_HEADING.match(value)
    if match is None:
        return None
    return min(len(match.group("number").split(".")) + 0, 6)


def build_deterministic_candidate(
    revision: DocumentRevision,
    page_number: int,
    *,
    max_operations: int = 8,
) -> RepairedDocumentCandidate | None:
    """为当前页生成确定性标题层级 Patch；没有高置信 Patch 则返回 None。

    只有以下条件同时满足才会修复：标题有明确的数字/字母编号、来源页码
    明确，且全篇标题层级呈现解析器常见的统一/混合粒度问题，或当前层级缺失。
    """

    document = revision.document
    headings = [
        block
        for block in document.blocks
        if block.kind == BlockKind.HEADING
        and block.anchor.page_number is not None
    ]
    numbered_levels = {
        str(block.id): _heading_numbered_level(block.markdown, block.text)
        for block in headings
    }
    valid_levels = [level for level in numbered_levels.values() if level is not None]
    if not valid_levels:
        return None

    parser_levels = {
        block.heading_level for block in headings if block.heading_level is not None
    }
    levels_by_parser_level: dict[int, set[int]] = {}
    for block in headings:
        inferred = numbered_levels[str(block.id)]
        if block.heading_level is not None and inferred is not None:
            levels_by_parser_level.setdefault(block.heading_level, set()).add(inferred)
    granularity_suspect = (
        len(parser_levels) == 1 and len(headings) > 1
    ) or any(len(levels) > 1 for levels in levels_by_parser_level.values())

    page_headings = [
        block for block in headings if block.anchor.page_number == page_number
    ]
    operations: list[RepairOperation] = []
    evidence_refs: list[CandidateEvidenceRef] = []
    for block in page_headings:
        inferred = numbered_levels[str(block.id)]
        if inferred is None:
            continue
        if block.heading_level is not None and not granularity_suspect:
            continue
        if block.heading_level == inferred:
            continue
        operations.append(
            RepairOperation(
                operation="update_heading_level",
                block_id=str(block.id),
                heading_level=inferred,
            )
        )
        evidence_refs.append(
            CandidateEvidenceRef(
                object_type="block",
                object_id=str(block.id),
                field_path="heading_level",
            )
        )
        if len(operations) >= max_operations:
            break

    if not operations:
        return None
    return RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        scope="page",
        scope_pages=[page_number],
        operations=operations,
        lineage=[revision.revision_id],
        evidence_refs=evidence_refs,
        change_kind="structure",
        reasoning="依据当前文档已有的编号模式确定性恢复标题层级，不修改标题文字。",
        confidence=0.92,
    )


__all__ = ["build_deterministic_candidate"]
