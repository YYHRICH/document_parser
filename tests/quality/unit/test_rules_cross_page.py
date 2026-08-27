"""QL-TBL-007 跨页续表规则单元测试。"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from document_parser.core.contracts import (
    ParsedDocument,
    ParsedTable,
    QualityCapabilityState,
    TableCell,
)

from quality.evidence.context import EvidenceContext
from quality.rules.cross_page import QL_TBL_007_CrossPageContinuation, QL_TBL_008_ColumnDrift

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "quality" / "fixtures" / "parsed_documents"


def _load(sample: str) -> ParsedDocument:
    return ParsedDocument.model_validate_json(
        (FIXTURES / f"{sample}.json").read_text(encoding="utf-8")
    )


def _cell(text: str, r: int, c: int, col_hdr=False) -> TableCell:
    return TableCell(
        text=text, start_row=r, start_col=c,
        row_span=1, col_span=1,
        column_header=col_hdr, row_header=False,
    )


def _table(table_id: str, page: int, headers: list[str], rows: int) -> ParsedTable:
    cells = [_cell(h, 0, i, col_hdr=True) for i, h in enumerate(headers)]
    for r in range(1, rows):
        for c in range(len(headers)):
            cells.append(_cell(f"v{r}c{c}", r, c))
    return ParsedTable(
        table_id=table_id,
        block_id=uuid4(),
        num_rows=rows,
        num_cols=len(headers),
        cells=cells,
        page_number=page,
        bbox=(10.0, 10.0, 500.0, 300.0),
    )


def _doc_with_tables(*tables: ParsedTable) -> ParsedDocument:
    doc = _load("sdp-005-mineru")
    # 同步生成 table blocks
    from document_parser.core.contracts import BlockKind, DocumentBlock, SourceAnchor

    blocks = list(doc.blocks)
    for t in tables:
        blocks.append(
            DocumentBlock(
                id=t.block_id,
                source_block_id=f"tbl-{t.table_id}",
                order_index=len(blocks),
                kind=BlockKind.TABLE,
                text="| table |",
                markdown="| table |",
                anchor=SourceAnchor(page_number=t.page_number),
                metadata={"table_id": t.table_id},
            )
        )
    return doc.model_copy(update={"blocks": blocks, "tables": list(tables)})


def test_exact_header_continuation_verified():
    """表头完全一致 + 相邻页 + 列数一致 → verified continuation。"""
    t1 = _table("t-a", 1, ["行号", "物料", "数量"], 3)
    t2 = _table("t-b", 2, ["行号", "物料", "数量"], 3)
    result = QL_TBL_007_CrossPageContinuation().execute(
        EvidenceContext(_doc_with_tables(t1, t2))
    )
    assert len(result.relation_candidates) == 1
    rel = result.relation_candidates[0]
    assert rel.relation_type == "table_continuation"
    assert rel.state == QualityCapabilityState.VERIFIED


def test_partial_header_with_hint_manual():
    """表头部分一致 + '续行'标志 → manual_review_required。"""
    t1 = _table("t-a", 3, ["行号", "物料描述", "数量", "单价", "小计"], 3)
    t2 = _table("t-b", 4, ["标记", "物料描述续行", "数量", "单价", "小计"], 3)
    result = QL_TBL_007_CrossPageContinuation().execute(
        EvidenceContext(_doc_with_tables(t1, t2))
    )
    assert len(result.relation_candidates) == 1
    assert (
        result.relation_candidates[0].state
        == QualityCapabilityState.MANUAL_REVIEW_REQUIRED
    )


def test_single_column_overlap_not_paired():
    """只有'行号'等泛用列重叠 → 不配对（防过度）。"""
    t1 = _table("t-a", 2, ["行号", "物料名称", "期初"], 3)
    t2 = _table("t-b", 3, ["行号", "物料描述", "数量"], 3)
    result = QL_TBL_007_CrossPageContinuation().execute(
        EvidenceContext(_doc_with_tables(t1, t2))
    )
    assert result.relation_candidates == ()


def test_non_adjacent_pages_not_paired():
    t1 = _table("t-a", 1, ["行号", "物料", "数量"], 3)
    t2 = _table("t-b", 3, ["行号", "物料", "数量"], 3)
    result = QL_TBL_007_CrossPageContinuation().execute(
        EvidenceContext(_doc_with_tables(t1, t2))
    )
    assert result.relation_candidates == ()


def test_column_count_mismatch_not_paired():
    t1 = _table("t-a", 1, ["行号", "物料", "数量"], 3)
    t2 = _table("t-b", 2, ["行号", "物料", "数量", "单价"], 3)
    result = QL_TBL_007_CrossPageContinuation().execute(
        EvidenceContext(_doc_with_tables(t1, t2))
    )
    assert result.relation_candidates == ()


def test_unrelated_table_between_pages_not_paired():
    t1 = _table("t-a", 1, ["行号", "物料", "数量"], 3)
    tm = _table("t-mid", 1, ["其他", "字段", "列"], 3)
    t2 = _table("t-b", 2, ["行号", "物料", "数量"], 3)
    result = QL_TBL_007_CrossPageContinuation().execute(EvidenceContext(_doc_with_tables(t1, tm, t2)))
    assert result.relation_candidates == ()


def test_unknown_page_is_not_adjacent():
    t1 = _table("t-a", 1, ["行号", "物料", "数量"], 3).model_copy(update={"page_number": None})
    t2 = _table("t-b", 2, ["行号", "物料", "数量"], 3)
    result = QL_TBL_007_CrossPageContinuation().execute(EvidenceContext(_doc_with_tables(t1, t2)))
    assert result.relation_candidates == ()


def test_column_drift_rule_detects_header_order_change():
    t1 = _table("t-a", 1, ["行号", "物料", "数量"], 3)
    t2 = _table("t-b", 2, ["行号", "数量", "物料"], 3)
    result = QL_TBL_008_ColumnDrift().execute(EvidenceContext(_doc_with_tables(t1, t2)))
    assert any(i.category == "column_drift" for i in result.issues)


def test_column_drift_ignores_unrelated_adjacent_tables():
    t1 = _table("t-a", 1, ["项目", "华东精工", "北辰机电", "远景自动化"], 3)
    t2 = _table("t-b", 2, ["供应商", "技术符合", "价格", "交付", "服务", "总分"], 3)
    result = QL_TBL_008_ColumnDrift().execute(EvidenceContext(_doc_with_tables(t1, t2)))
    assert not any(i.category == "column_drift" for i in result.issues)

def test_table_body_text_does_not_create_continuation_hint():
    t1 = _table("t-a", 1, ["测试面", "PDF证据", "质量行为", "状态"], 3)
    t1 = t1.model_copy(update={
        "cells": [
            cell.model_copy(update={"text": "跨页关系仅是业务描述"}) if cell.start_row == 1 and cell.start_col == 0 else cell
            for cell in t1.cells
        ]
    })
    t2 = _table("t-b", 2, ["字段", "测试值"], 3)
    result = QL_TBL_007_CrossPageContinuation().execute(EvidenceContext(_doc_with_tables(t1, t2)))
    assert result.relation_candidates == ()


def test_rule_id_is_stable():
    assert QL_TBL_007_CrossPageContinuation.rule_id == "QL-TBL-007"
    assert QL_TBL_008_ColumnDrift.rule_id == "QL-TBL-008"
