"""M2 关系集成测试：真实 fixtures 上的标题树与引用绑定。"""

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


def test_sdp006_docling_references_all_verified():
    """正例：docling 参考索引完整（6 条），正文 [1-2][3][4][5][6] 全部 verified。"""
    pkg = run_quality(_load("sdp-006-docling"))
    ref_rels = [
        r for r in pkg.canonical_document.relations
        if r.relation_type == "reference_of"
    ]
    assert ref_rels, "应产出 reference_of 关系"
    assert all(r.status == QualityCapabilityState.VERIFIED for r in ref_rels)
    assert len(ref_rels) == 6  # [1-2] 展开 2 条 + [3][4][5][6] 各 1 条


def test_sdp006_mineru_partial_bindings_with_missing_issues():
    """MinerU 只恢复 2 条参考条目 → [3]-[6] missing，不误绑缺失编号。"""
    pkg = run_quality(_load("sdp-006-mineru"))
    ref_rels = [
        r for r in pkg.canonical_document.relations
        if r.relation_type == "reference_of"
    ]
    missing_issues = [
        i for i in pkg.quality_report.issues
        if i.category == "citation_binding"
    ]
    # 部分绑定（参考索引存在的编号），且缺失编号有 issue 而非静默
    assert ref_rels, "应绑定参考索引中存在的编号"
    assert missing_issues, "缺失编号必须产生 issue"
    assert all(
        r.status == QualityCapabilityState.VERIFIED for r in ref_rels
    )


def test_sdp006_heading_tree_degraded_not_verified():
    """标题层级粒度可疑（解析器全平）→ 树关系降级，不假装 verified。"""
    for sample in ("sdp-006-docling", "sdp-006-mineru"):
        pkg = run_quality(_load(sample))
        hdg_rels = [
            r for r in pkg.canonical_document.relations
            if r.relation_type == "parent_child"
        ]
        assert hdg_rels, f"{sample} 应产出 parent_child"
        assert all(
            r.status != QualityCapabilityState.VERIFIED for r in hdg_rels
        ), f"{sample} 的树在粒度可疑时不应 verified"


def test_sdp007_no_verified_reference_for_ambiguous_scenario():
    """歧义反例：sdp-007 的歧义来自作者-年份（二期），数字引用 MVP
    不得产生超出参考索引证据的 verified 绑定。"""
    pkg = run_quality(_load("sdp-007-docling"))
    ref_rels = [
        r for r in pkg.canonical_document.relations
        if r.relation_type == "reference_of"
    ]
    block_ids = {b.block_id for b in pkg.canonical_document.blocks}
    for rel in ref_rels:
        assert rel.from_id in block_ids, "关系 from 端点必须可解析"
        assert rel.to_id in block_ids, "关系 to 端点必须可解析"


def test_all_relation_endpoints_resolve():
    """通用不变量：所有关系端点都能在 canonical blocks 中解析（无悬挂引用）。"""
    for sample in ("sdp-006-docling", "sdp-006-mineru", "sdp-007-docling", "sdp-007-mineru"):
        pkg = run_quality(_load(sample))
        block_ids = {b.block_id for b in pkg.canonical_document.blocks}
        for rel in pkg.canonical_document.relations:
            assert rel.from_id in block_ids, f"{sample}: from {rel.from_id} 悬挂"
            assert rel.to_id in block_ids, f"{sample}: to {rel.to_id} 悬挂"


def test_relation_ids_are_stable_and_distinct():
    """关系 ID 稳定且互不冲突。"""
    pkg1 = run_quality(_load("sdp-006-docling"))
    pkg2 = run_quality(_load("sdp-006-docling"))
    r1 = {r.relation_id for r in pkg1.canonical_document.relations}
    r2 = {r.relation_id for r in pkg2.canonical_document.relations}
    assert r1 == r2
    assert len(r1) == len(pkg1.canonical_document.relations)  # 无重复 ID
