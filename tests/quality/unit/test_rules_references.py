"""QL-REF-* 数字引用规则单元测试。"""

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
from quality.rules.references import (
    QL_REF_001_ReferenceIndex,
    QL_REF_004_BindCitations,
    build_reference_index,
    _expand_marker,
)

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "quality" / "fixtures" / "parsed_documents"


def _load(sample: str) -> ParsedDocument:
    return ParsedDocument.model_validate_json(
        (FIXTURES / f"{sample}.json").read_text(encoding="utf-8")
    )


def _h(text: str, order: int) -> DocumentBlock:
    return DocumentBlock(
        id=uuid4(),
        source_block_id=f"h-{order}",
        order_index=order,
        kind=BlockKind.HEADING,
        text=text,
        heading_level=2,
        markdown=f"## {text}",
        anchor=SourceAnchor(),
    )


def _p(text: str, order: int, source_id: str | None = None) -> DocumentBlock:
    return DocumentBlock(
        id=uuid4(),
        source_block_id=source_id or f"p-{order}",
        order_index=order,
        kind=BlockKind.PARAGRAPH,
        text=text,
        markdown=text,
        anchor=SourceAnchor(),
    )


def _list(text: str, order: int, marker: str) -> DocumentBlock:
    return DocumentBlock(
        id=uuid4(),
        source_block_id=f"list-{order}",
        order_index=order,
        kind=BlockKind.LIST,
        text=text,
        markdown=text,
        anchor=SourceAnchor(),
        metadata={"marker": marker},
    )


def _doc(*blocks: DocumentBlock) -> ParsedDocument:
    base = _load("sdp-006-mineru")
    return base.model_copy(update={"blocks": list(blocks)})


# ---------- marker 展开 ----------

def test_expand_single():
    assert _expand_marker("1") == [1]


def test_expand_list():
    assert _expand_marker("1, 3, 5") == [1, 3, 5]


def test_expand_range():
    assert _expand_marker("2-4") == [2, 3, 4]
    assert _expand_marker("2–4") == [2, 3, 4]


def test_expand_invalid():
    assert _expand_marker("") is None
    assert _expand_marker("1-") is None
    assert _expand_marker("5-2") is None  # 反向范围


def test_expand_rejects_huge_range():
    assert _expand_marker("1-1000") is None


# ---------- 参考索引 ----------

def test_reference_index_from_headings():
    doc = _doc(
        _h("正文", 0),
        _p("正文内容 [1]。", 1),
        _h("参考文献", 2),
        _p("Li, M. 2023. 文献一", 3),
        _p("王伟, 陈晨. 2023. 文献二", 4),
    )
    index = build_reference_index(EvidenceContext(doc))
    assert [e.key for e in index] == ["1", "2"]
    assert index[0].text.startswith("Li, M.")


def test_reference_index_accepts_docling_list_items_and_marker():
    doc = _doc(
        _h("References", 0),
        _list("First paper", 1, "1."),
        _list("Second paper", 2, "2."),
    )
    index = build_reference_index(EvidenceContext(doc))
    assert [entry.key for entry in index] == ["1", "2"]


def test_list_reference_binds_citation_by_marker():
    doc = _doc(
        _p("见文献 [2]。", 0),
        _h("References", 1),
        _list("Second paper", 2, "2."),
    )
    result = QL_REF_004_BindCitations().execute(EvidenceContext(doc))
    assert not result.issues
    assert len(result.relation_candidates) == 1
    assert result.relation_candidates[0].evidence["target_key"] == "2"


def test_reference_index_skips_explanatory_line():
    doc = _doc(
        _h("参考文献", 0),
        _p("引用规则：正文中的 [1-2] 指向参考文献 1 和 2。", 1),
        _p("Li, M. 2023. 文献一", 2),
    )
    index = build_reference_index(EvidenceContext(doc))
    assert [e.key for e in index] == ["1"]
    assert index[0].text.startswith("Li, M.")


def test_reference_index_no_heading_empty():
    doc = _doc(_p("没有参考文献标题", 0))
    assert build_reference_index(EvidenceContext(doc)) == []


# ---------- 引用绑定 ----------

def test_citations_bind_verified_when_unique():
    doc = _doc(
        _p("已有方法见文献 [1]。", 0),
        _h("参考文献", 1),
        _p("Li, M. 2023. 文献一", 2),
        _p("王伟, 陈晨. 2023. 文献二", 3),
    )
    result = QL_REF_004_BindCitations().execute(EvidenceContext(doc))
    relations = result.relation_candidates
    assert len(relations) == 1
    assert relations[0].relation_type == "reference_of"
    assert relations[0].state == QualityCapabilityState.VERIFIED
    assert (
        result.capability_observations[0].observed_state
        == QualityCapabilityState.VERIFIED
    )


def test_range_citation_binds_all():
    doc = _doc(
        _p("见 [1-2]。", 0),
        _h("参考文献", 1),
        _p("A. 2023. one", 2),
        _p("B. 2023. two", 3),
    )
    result = QL_REF_004_BindCitations().execute(EvidenceContext(doc))
    assert len(result.relation_candidates) == 2


def test_missing_target_never_verified():
    """编号在索引中不存在 → 只出 issue，不创建 verified 关系。"""
    doc = _doc(
        _p("见 [3]。", 0),
        _h("参考文献", 1),
        _p("A. 2023. one", 2),
    )
    result = QL_REF_004_BindCitations().execute(EvidenceContext(doc))
    assert result.relation_candidates == ()
    assert any(i.category == "citation_binding" for i in result.issues)


def test_explanatory_text_not_treated_as_citation():
    doc = _doc(
        _p("引用规则：正文中的 [1-2] 指向参考文献 1 和 2。", 0),
        _h("参考文献", 1),
        _p("A. 2023. one", 2),
        _p("B. 2023. two", 3),
    )
    result = QL_REF_004_BindCitations().execute(EvidenceContext(doc))
    assert result.relation_candidates == ()
    assert result.issues == ()


def test_no_reference_heading_no_binding():
    doc = _doc(_p("见 [1]。", 0), _p("普通段落", 1))
    result = QL_REF_004_BindCitations().execute(EvidenceContext(doc))
    assert result.relation_candidates == ()


def test_rule_ids_are_stable():
    assert QL_REF_001_ReferenceIndex.rule_id == "QL-REF-001"
    assert QL_REF_004_BindCitations.rule_id == "QL-REF-004"


def test_explicit_reference_label_is_preserved():
    doc = _doc(_p("见 [3]。", 0), _h("参考文献", 1), _p("[3] C. 2023", 2))
    result = QL_REF_004_BindCitations().execute(EvidenceContext(doc))
    assert len(result.relation_candidates) == 1
    assert result.relation_candidates[0].state == QualityCapabilityState.VERIFIED
    assert result.relation_candidates[0].evidence["normalized_labels"] == ["3"]


def test_same_marker_in_multiple_blocks_is_not_deduplicated():
    doc = _doc(_p("见 [1]。", 0), _p("再见 [1]。", 1), _h("参考文献", 2), _p("A. 2023", 3))
    result = QL_REF_004_BindCitations().execute(EvidenceContext(doc))
    assert len(result.relation_candidates) == 2
    assert {r.from_id for r in result.relation_candidates} == {str(doc.blocks[0].id), str(doc.blocks[1].id)}


def test_markdown_link_is_not_citation():
    doc = _doc(_p("链接 [1](https://example.com)", 0), _h("参考文献", 1), _p("A. 2023", 2))
    result = QL_REF_004_BindCitations().execute(EvidenceContext(doc))
    assert result.relation_candidates == ()


def test_duplicate_reference_labels_are_ambiguous():
    doc = _doc(_p("见 [1]。", 0), _h("参考文献", 1), _p("[1] A", 2), _p("[1] B", 3))
    result = QL_REF_004_BindCitations().execute(EvidenceContext(doc))
    assert result.relation_candidates == ()
    assert any(i.category == "ambiguous_target" for i in result.issues)
