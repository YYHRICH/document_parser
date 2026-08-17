"""M3 表格绑定集成测试：真实 fixtures 上的网格与字段绑定。"""

from __future__ import annotations

from pathlib import Path

from document_parser.core.contracts import (
    ParsedDocument,
    QualityCapabilityState,
)

from quality import run_quality

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "quality" / "fixtures" / "parsed_documents"


def _load(sample: str) -> ParsedDocument:
    return ParsedDocument.model_validate_json(
        (FIXTURES / f"{sample}.json").read_text(encoding="utf-8")
    )


def test_sdp004_docling_merged_header_paths_verified():
    """正例：docling 数据有多级表头标记 → 完整 column_path + verified bindings。"""
    pkg = run_quality(_load("sdp-004-docling"))
    binds = pkg.canonical_document.table_bindings
    assert binds, "应产出表格字段绑定"
    verified = [b for b in binds if b.status == QualityCapabilityState.VERIFIED]
    assert verified, "docling 数据应有 verified 绑定"

    paths = {tuple(b.column_path) for b in verified}
    # 合并表头完整路径（技术参数 → 额定电压/温度范围；商务条款 → 含税单价/质保）
    assert ("技术参数", "额定电压") in paths
    assert ("技术参数", "温度范围") in paths
    assert ("商务条款", "含税单价（元）") in paths or ("商务条款", "含税单价") in paths
    assert ("商务条款", "质保（月）") in paths or ("商务条款", "质保") in paths


def test_sdp004_docling_no_flattened_paths():
    """合并表头不允许拍平（丢失父级表头）。"""
    pkg = run_quality(_load("sdp-004-docling"))
    paths = {tuple(b.column_path) for b in pkg.canonical_document.table_bindings}
    flat = [p for p in paths if len(p) == 1]
    # 一级路径只允许 row_key 列的表头（供应商/型号），技术参数类必须有完整两级
    assert not any(p == ("额定电压",) or p == ("含税单价（元）",) for p in flat)


def test_sdp004_mineru_bindings_inferred_not_verified():
    """MinerU 无 row_header 标记 → 绑定全部 inferred，不伪造 verified。"""
    pkg = run_quality(_load("sdp-004-mineru"))
    binds = pkg.canonical_document.table_bindings
    assert binds
    assert all(
        b.status == QualityCapabilityState.INFERRED for b in binds
    )


def test_sdp005_no_false_verified_across_pages():
    """sdp-005 跨页表格：不产生超出证据的 verified 绑定（页内确定部分除外）。"""
    pkg = run_quality(_load("sdp-005-docling"))
    binds = pkg.canonical_document.table_bindings
    verified = [b for b in binds if b.status == QualityCapabilityState.VERIFIED]
    # 一期不做跨页合并：verified 绑定只可能来自单页内明确证据；
    # 这里断言至少不出现"列漂移"导致的错误绑定（全 inferred 或已验证的页内绑定）
    for b in verified:
        assert b.source_locator.bbox_granularity == "table"


def test_sdp005_cross_page_continuation_detected():
    """sdp-005 跨页续表：表头一致 → verified；续行弱候选 → manual。"""
    pkg = run_quality(_load("sdp-005-mineru"))
    conts = [
        r for r in pkg.canonical_document.relations
        if r.relation_type == "table_continuation"
    ]
    assert conts, "应识别出跨页续表"
    assert any(r.status == QualityCapabilityState.VERIFIED for r in conts)
    # 页内确定 binding 保留（不因跨页歧义全部丢失）
    assert pkg.canonical_document.table_bindings


def test_binding_ids_stable_and_distinct():
    """binding ID 稳定、互不冲突、可复算。"""
    pkg1 = run_quality(_load("sdp-004-docling"))
    pkg2 = run_quality(_load("sdp-004-docling"))
    ids1 = [b.binding_id for b in pkg1.canonical_document.table_bindings]
    ids2 = [b.binding_id for b in pkg2.canonical_document.table_bindings]
    assert ids1 == ids2
    assert len(set(ids1)) == len(ids1)


def test_binding_endpoints_resolve():
    """binding 的 block_id 必须能在 canonical blocks 中解析。"""
    pkg = run_quality(_load("sdp-004-docling"))
    block_ids = {b.block_id for b in pkg.canonical_document.blocks}
    for b in pkg.canonical_document.table_bindings:
        assert b.block_id in block_ids, f"binding {b.binding_id} 的 block 悬挂"
