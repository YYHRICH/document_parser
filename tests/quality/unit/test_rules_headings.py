"""QL-HDG-* 标题树规则单元测试。"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from document_parser.core.contracts import (
    BlockKind,
    DocumentBlock,
    IssueSeverity,
    ParsedDocument,
    QualityCapabilityState,
    SourceAnchor,
)

from quality.evidence.context import EvidenceContext
from quality.rules.headings import QL_HDG_001_HeadingFields, QL_HDG_004_BuildTree

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "quality" / "fixtures" / "parsed_documents"


def _load(sample: str) -> ParsedDocument:
    return ParsedDocument.model_validate_json(
        (FIXTURES / f"{sample}.json").read_text(encoding="utf-8")
    )


def _h(text: str, level: int | None, order: int, source_id: str = "src") -> DocumentBlock:
    return DocumentBlock(
        id=uuid4(),
        source_block_id=f"{source_id}-{order}",
        order_index=order,
        kind=BlockKind.HEADING,
        text=text,
        heading_level=level,
        markdown=f"{'#' * (level or 1)} {text}",
        anchor=SourceAnchor(),
    )


def _p(text: str, order: int) -> DocumentBlock:
    return DocumentBlock(
        id=uuid4(),
        source_block_id=f"p-{order}",
        order_index=order,
        kind=BlockKind.PARAGRAPH,
        text=text,
        markdown=text,
        anchor=SourceAnchor(),
    )


def _doc(*blocks: DocumentBlock) -> ParsedDocument:
    base = _load("sdp-006-mineru")
    return base.model_copy(update={"blocks": list(blocks)})


# ---------- QL-HDG-001 ----------

def test_hdg001_all_levels_present_verified():
    doc = _doc(_h("文档", 1, 0), _h("1 引言", 2, 1), _h("1.1 背景", 3, 2))
    result = QL_HDG_001_HeadingFields().execute(EvidenceContext(doc))
    assert result.issues == ()
    assert (
        result.capability_observations[0].observed_state
        == QualityCapabilityState.VERIFIED
    )


def test_hdg001_heading_without_level_or_numbering_warning():
    doc = _doc(_h("无编号无层级标题", None, 0))
    result = QL_HDG_001_HeadingFields().execute(EvidenceContext(doc))
    assert any(i.category == "heading_structure" for i in result.issues)


# ---------- QL-HDG-004 ----------

def test_tree_verified_when_levels_consistent():
    doc = _doc(
        _h("文档标题", 1, 0),
        _h("1 引言", 2, 1),
        _h("1.1 背景", 3, 2),
        _h("1.2 方法", 3, 3),
        _h("2 结论", 2, 4),
    )
    result = QL_HDG_004_BuildTree().execute(EvidenceContext(doc))
    relations = result.relation_candidates
    assert len(relations) == 4
    assert all(r.state == QualityCapabilityState.VERIFIED for r in relations)
    # 父子结构验证
    by_text = {r.to_id: r for r in relations}
    assert all(r.relation_type == "parent_child" for r in relations)
    assert (
        result.capability_observations[0].observed_state
        == QualityCapabilityState.VERIFIED
    )


def test_level_jump_degrades_to_inferred():
    doc = _doc(
        _h("文档标题", 1, 0),
        _h("1 引言", 3, 1),  # 1 -> 3 跳级
    )
    result = QL_HDG_004_BuildTree().execute(EvidenceContext(doc))
    relations = result.relation_candidates
    assert relations[0].state == QualityCapabilityState.INFERRED
    assert any(i.category == "heading_level_jump" for i in result.issues)


def test_numbering_restores_level_as_inferred():
    """解析器层级全平/缺失时，编号模式恢复层级 → 只允许 inferred。"""
    doc = _doc(
        _h("1 引言", None, 0),
        _h("1.1 背景", None, 1),
        _h("1.2 方法", None, 2),
    )
    result = QL_HDG_004_BuildTree().execute(EvidenceContext(doc))
    relations = result.relation_candidates
    assert len(relations) == 2
    # 1.1 的父必须是 1（编号层级恢复）
    assert all(r.state == QualityCapabilityState.INFERRED for r in relations)
    assert (
        result.capability_observations[0].observed_state
        == QualityCapabilityState.INFERRED
    )


def test_orphan_heading_without_parent_manual():
    """第一个标题作根（level3），后续 level2 弹掉根后无父 → 孤立。"""
    doc = _doc(_h("3 摘要", 3, 0), _h("2 方法", 2, 1))
    result = QL_HDG_004_BuildTree().execute(EvidenceContext(doc))
    assert any(i.category == "heading_parent_missing" for i in result.issues)


def test_first_heading_without_h1_requires_manual_review():
    """开头直接 H2/H3 不得伪装成根节点。"""
    doc = _doc(_h("2 孤章节", 2, 0), _h("3 内容", 3, 1))
    result = QL_HDG_004_BuildTree().execute(EvidenceContext(doc))
    assert any(i.category == "heading_parent_missing" for i in result.issues)
    assert result.relation_candidates[0].state == QualityCapabilityState.MANUAL_REVIEW_REQUIRED


def test_uniform_levels_keep_parser_level_for_unnumbered_heading():
    doc = _doc(
        _h("文档标题", 1, 0),
        _h("1 章节", 1, 1),
        _h("无编号章节", 1, 2),
    )
    result = QL_HDG_004_BuildTree().execute(EvidenceContext(doc))
    assert not any(i.category == "heading_level_missing" for i in result.issues)
    assert result.relation_candidates == ()


def test_undeterminable_heading_no_relation():
    """非根标题无法确定层级 → 不创建关系 + missing issue。"""
    doc = _doc(_h("1 引言", 1, 0), _h("无层级无编号", None, 1))
    result = QL_HDG_004_BuildTree().execute(EvidenceContext(doc))
    assert all(r.to_id != str(doc.blocks[1].id) for r in result.relation_candidates)
    assert any(i.category == "heading_level_missing" for i in result.issues)


def test_rule_ids_are_stable():
    assert QL_HDG_001_HeadingFields.rule_id == "QL-HDG-001"
    assert QL_HDG_004_BuildTree.rule_id == "QL-HDG-004"


def test_markdown_only_numbered_headings_restore_levels():
    doc = _doc(
        DocumentBlock(id=uuid4(), source_block_id="m-0", order_index=0, kind=BlockKind.HEADING,
                      text=None, markdown="# 1 引言", heading_level=None, anchor=SourceAnchor()),
        DocumentBlock(id=uuid4(), source_block_id="m-1", order_index=1, kind=BlockKind.HEADING,
                      text=None, markdown="## 1.1 背景", heading_level=None, anchor=SourceAnchor()),
    )
    result = QL_HDG_004_BuildTree().execute(EvidenceContext(doc))
    assert len(result.relation_candidates) == 1
    assert result.relation_candidates[0].state == QualityCapabilityState.INFERRED


def test_duplicate_order_never_verified():
    doc = _doc(_h("文档", 1, 0), _h("1 引言", 2, 1), _p("正文", 1))
    result = QL_HDG_004_BuildTree().execute(EvidenceContext(doc))
    assert result.relation_candidates
    assert all(r.state == QualityCapabilityState.MANUAL_REVIEW_REQUIRED for r in result.relation_candidates)
    assert any(i.category == "reading_order_conflict" for i in result.issues)
