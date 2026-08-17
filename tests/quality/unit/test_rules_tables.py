"""QL-TBL-* 表格规则单元测试。"""

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
from quality.rules.tables import (
    QL_TBL_004_ColumnPath,
    QL_TBL_006_BuildBindings,
    analyze_grid,
)

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "quality" / "fixtures" / "parsed_documents"


def _load(sample: str) -> ParsedDocument:
    return ParsedDocument.model_validate_json(
        (FIXTURES / f"{sample}.json").read_text(encoding="utf-8")
    )


def _table(table_id: str, cells: list[TableCell], rows: int, cols: int) -> ParsedTable:
    return ParsedTable(
        table_id=table_id,
        block_id=uuid4(),
        num_rows=rows,
        num_cols=cols,
        cells=cells,
        page_number=1,
        bbox=(10.0, 10.0, 500.0, 300.0),
    )


def _cell(text: str, r: int, c: int, *, col_hdr=False, row_hdr=False, row_span=1, col_span=1) -> TableCell:
    return TableCell(
        text=text,
        start_row=r,
        start_col=c,
        row_span=row_span,
        col_span=col_span,
        column_header=col_hdr,
        row_header=row_hdr,
    )


def _doc_with_table(table: ParsedTable) -> ParsedDocument:
    doc = _load("sdp-004-mineru")
    return doc.model_copy(update={"tables": [table]})


# 多级表头正例（docling 风格）
def _merged_header_table() -> ParsedTable:
    return _table(
        "t1",
        [
            _cell("供应商", 0, 0, col_hdr=True),
            _cell("型号", 0, 1, col_hdr=True),
            _cell("技术参数", 0, 2, col_hdr=True, col_span=2),
            _cell("商务条款", 0, 4, col_hdr=True, col_span=2),
            _cell("额定电压", 1, 2, col_hdr=True),
            _cell("温度范围", 1, 3, col_hdr=True),
            _cell("含税单价", 1, 4, col_hdr=True),
            _cell("质保月", 1, 5, col_hdr=True),
            _cell("华东精工", 2, 0, row_hdr=True),
            _cell("FAN-A", 2, 1),
            _cell("12 V", 2, 2),
            _cell("-20-70", 2, 3),
            _cell("186.00", 2, 4),
            _cell("18", 2, 5),
        ],
        rows=3,
        cols=6,
    )


def test_grid_analysis_header_rows_include_second_level():
    analysis = analyze_grid(_merged_header_table())
    assert analysis.header_rows == [0, 1]
    assert analysis.valid


def test_grid_analysis_overlap_conflict():
    t = _table(
        "t1",
        [
            _cell("a", 0, 0, col_hdr=True),
            _cell("b", 0, 0, col_hdr=True),  # 重叠
            _cell("c", 1, 0),
        ],
        rows=2,
        cols=1,
    )
    analysis = analyze_grid(t)
    assert not analysis.valid
    assert any("占位冲突" in i.message for i in analysis.issues)


def test_grid_analysis_cell_beyond_declared_size():
    t = _table(
        "t1",
        [
            _cell("a", 0, 0, col_hdr=True),
            _cell("b", 1, 0),
            _cell("c", 2, 0),  # 越界（rows=2）
        ],
        rows=2,
        cols=1,
    )
    analysis = analyze_grid(t)
    assert not analysis.valid
    assert any("越过声明尺寸" in i.message for i in analysis.issues)


def test_column_path_multilevel_not_flattened():
    """多级表头保留完整路径（合并表头按 cell identity 去重，不拍平）。"""
    result = QL_TBL_006_BuildBindings().execute(
        EvidenceContext(_doc_with_table(_merged_header_table()))
    )
    paths = {tuple(b.column_path) for b in result.binding_candidates}
    assert ("技术参数", "额定电压") in paths
    assert ("技术参数", "温度范围") in paths
    assert ("商务条款", "含税单价") in paths
    # 不允许拍平（缺父级）或丢层级
    assert ("额定电压",) not in paths


def test_row_key_from_row_header_verified():
    result = QL_TBL_006_BuildBindings().execute(
        EvidenceContext(_doc_with_table(_merged_header_table()))
    )
    verified = [b for b in result.binding_candidates if b.row_key == "华东精工"]
    assert verified
    assert all(
        b.source_locator.provenance_status == QualityCapabilityState.VERIFIED
        for b in verified
    )
    assert all(b.value in {"FAN-A", "12 V", "-20-70", "186.00", "18"} for b in verified)


def test_row_key_inferred_without_mark():
    """无 row_header 标记 → row_key 首列推断 → binding inferred。"""
    table = _merged_header_table().model_copy()
    cells = [c.model_copy(update={"row_header": False}) for c in table.cells]
    table = table.model_copy(update={"cells": cells})
    result = QL_TBL_006_BuildBindings().execute(EvidenceContext(_doc_with_table(table)))
    assert result.binding_candidates
    assert all(
        b.source_locator.provenance_status == QualityCapabilityState.INFERRED
        for b in result.binding_candidates
    )


def test_no_binding_without_row_key():
    """row_key 为空 → 安全降级，不生成 binding。"""
    table = _table(
        "t1",
        [
            _cell("H", 0, 0, col_hdr=True),
            _cell("", 1, 0),  # 空行首
            _cell("val", 1, 1),
        ],
        rows=2,
        cols=2,
    )
    result = QL_TBL_006_BuildBindings().execute(EvidenceContext(_doc_with_table(table)))
    assert result.binding_candidates == ()


def test_mutually_exclusive_headers_not_verified():
    """同一表头行两个 cell 覆盖同一列 → 互斥 → column_path 无法确定。"""
    table = _table(
        "t1",
        [
            _cell("a", 0, 0, col_hdr=True, col_span=2),
            _cell("b", 0, 1, col_hdr=True),  # 与 a 的展开重叠
            _cell("x", 1, 0),
        ],
        rows=2,
        cols=2,
    )
    result = QL_TBL_006_BuildBindings().execute(EvidenceContext(_doc_with_table(table)))
    assert result.binding_candidates == ()


def test_source_locator_uses_table_bbox_only():
    """来源只有表级 bbox → 保留表级来源，不伪造 cell bbox。"""
    result = QL_TBL_006_BuildBindings().execute(
        EvidenceContext(_doc_with_table(_merged_header_table()))
    )
    for b in result.binding_candidates:
        assert b.source_locator.bbox == (10.0, 10.0, 500.0, 300.0)
        assert b.source_locator.bbox_granularity == "table"


def test_column_path_rule_observations():
    result = QL_TBL_004_ColumnPath().execute(
        EvidenceContext(_doc_with_table(_merged_header_table()))
    )
    obs = result.capability_observations[0]
    assert obs.capability_name == "table_grid_reliable"
    assert obs.observed_state == QualityCapabilityState.VERIFIED


def test_rule_ids_are_stable():
    assert QL_TBL_004_ColumnPath.rule_id == "QL-TBL-004"
    assert QL_TBL_006_BuildBindings.rule_id == "QL-TBL-006"
