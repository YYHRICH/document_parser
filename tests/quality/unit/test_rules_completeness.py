"""QL-CONT-* 完整性规则单元测试（用真实 fixtures + 合成场景）。"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from document_parser.domain.model.contracts import (
    BlockKind,
    DocumentBlock,
    IssueSeverity,
    ParsedDocument,
    QualityCapabilityState,
    SourceAnchor,
)

from document_parser.domain.quality.evidence.context import EvidenceContext
from document_parser.domain.quality.rules.completeness import (
    QL_CONT_001_BlocksExist,
    QL_CONT_002_OrderIndex,
    QL_CONT_003_KindContent,
)

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "quality" / "fixtures" / "parsed_documents"


def _load(sample: str) -> ParsedDocument:
    return ParsedDocument.model_validate_json(
        (FIXTURES / f"{sample}.json").read_text(encoding="utf-8")
    )


def _make_doc(*blocks: DocumentBlock, tables: list | None = None) -> ParsedDocument:
    """构造最小 ParsedDocument（真实样式的占位字段）。"""
    base = _load("sdp-004-mineru")
    return base.model_copy(
        update={
            "blocks": list(blocks),
            "tables": tables if tables is not None else [],
        }
    )


# ---------- QL-CONT-001 ----------

def test_cont001_clean_document_verified():
    doc = _load("sdp-004-mineru")
    result = QL_CONT_001_BlocksExist().execute(EvidenceContext(doc))
    assert result.issues == ()
    obs = result.capability_observations[0]
    assert obs.capability_name == "content_complete"
    assert obs.observed_state == QualityCapabilityState.VERIFIED


def test_cont001_empty_blocks_critical():
    doc = _load("sdp-004-mineru").model_copy(update={"blocks": []})
    result = QL_CONT_001_BlocksExist().execute(EvidenceContext(doc))
    assert len(result.issues) == 1
    assert result.issues[0].severity == IssueSeverity.CRITICAL
    assert (
        result.capability_observations[0].observed_state
        == QualityCapabilityState.REJECTED
    )


def test_cont001_duplicate_block_id_critical():
    doc = _load("sdp-004-mineru")
    blocks = doc.blocks + [doc.blocks[0]]
    result = QL_CONT_001_BlocksExist().execute(EvidenceContext(doc.model_copy(update={"blocks": blocks})))
    assert any(i.severity == IssueSeverity.CRITICAL for i in result.issues)
    assert (
        result.capability_observations[0].observed_state
        == QualityCapabilityState.REJECTED
    )


# ---------- QL-CONT-002 ----------

def test_cont002_clean_order_verified():
    doc = _load("sdp-004-mineru")
    result = QL_CONT_002_OrderIndex().execute(EvidenceContext(doc))
    assert result.issues == ()
    assert (
        result.capability_observations[0].observed_state
        == QualityCapabilityState.VERIFIED
    )


def test_cont002_duplicate_order_index_warning():
    doc = _load("sdp-004-mineru")
    block = doc.blocks[0].model_copy(update={"id": uuid4()})
    blocks = doc.blocks + [block]  # 同 order_index 的两个块
    result = QL_CONT_002_OrderIndex().execute(EvidenceContext(doc.model_copy(update={"blocks": blocks})))
    assert any(i.severity == IssueSeverity.WARNING for i in result.issues)
    assert (
        result.capability_observations[0].observed_state
        == QualityCapabilityState.MANUAL_REVIEW_REQUIRED
    )


def test_cont002_missing_order_index_warning():
    doc = _load("sdp-004-mineru")
    block = doc.blocks[0].model_copy(update={"order_index": None})
    blocks = [block] + doc.blocks[1:]
    result = QL_CONT_002_OrderIndex().execute(EvidenceContext(doc.model_copy(update={"blocks": blocks})))
    assert any(i.category == "reading_order" for i in result.issues)


# ---------- QL-CONT-003 ----------

def test_cont003_heading_without_level_warning():
    heading_no_level = DocumentBlock(
        id=uuid4(),
        source_block_id="h-no-level",
        order_index=0,
        kind=BlockKind.HEADING,
        text="未定级标题",
        heading_level=None,
        markdown="未定级标题",
        anchor=SourceAnchor(),
    )
    doc = _make_doc(heading_no_level)
    result = QL_CONT_003_KindContent().execute(EvidenceContext(doc))
    heading_missing = [
        i for i in result.issues if i.category == "heading_structure"
    ]
    assert heading_missing, "缺 heading_level 的 heading 应产生问题"


def test_cont003_table_block_without_parsedtable_warning():
    orphan_table = DocumentBlock(
        id=uuid4(),
        source_block_id="orphan-table",
        order_index=99,
        kind=BlockKind.TABLE,
        markdown="| a |\n|---|\n| 1 |",
        anchor=SourceAnchor(),
    )
    doc = _make_doc(orphan_table)
    result = QL_CONT_003_KindContent().execute(EvidenceContext(doc))
    assert any(i.category == "table_structure" for i in result.issues)


def test_cont003_empty_text_info():
    empty = DocumentBlock(
        id=uuid4(),
        source_block_id="empty-p",
        order_index=0,
        kind=BlockKind.PARAGRAPH,
        text="   ",
        markdown="",
        anchor=SourceAnchor(),
    )
    doc = _make_doc(empty)
    result = QL_CONT_003_KindContent().execute(EvidenceContext(doc))
    assert any(i.severity == IssueSeverity.INFO for i in result.issues)


def test_cont003_markdown_is_used_when_text_missing():
    block = DocumentBlock(
        id=uuid4(),
        source_block_id="markdown-only",
        order_index=0,
        kind=BlockKind.PARAGRAPH,
        text=None,
        markdown="markdown 中有正文",
        anchor=SourceAnchor(),
    )
    result = QL_CONT_003_KindContent().execute(
        EvidenceContext(_make_doc(block))
    )

    assert not any(i.category == "content_completeness" for i in result.issues)


def test_cont003_clean_state_verified():
    doc = _load("sdp-004-mineru")
    result = QL_CONT_003_KindContent().execute(EvidenceContext(doc))
    assert (
        result.capability_observations[0].observed_state
        == QualityCapabilityState.VERIFIED
    )


def test_rule_ids_are_stable():
    assert QL_CONT_001_BlocksExist.rule_id == "QL-CONT-001"
    assert QL_CONT_002_OrderIndex.rule_id == "QL-CONT-002"
    assert QL_CONT_003_KindContent.rule_id == "QL-CONT-003"
