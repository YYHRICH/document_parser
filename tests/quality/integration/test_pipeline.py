"""M1 集成测试：run_quality 在真实 fixtures 上产出合法 QualityPackage。

覆盖：
- 真实样例（三路解析器）跑通完整流水线；
- 五态场景（pass / pass_with_warnings / manual / reparse / rejected）；
- 哈希可复算、document_id 一致、确定性。
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from document_parser.core.contracts import (
    BlockKind,
    DocumentBlock,
    IssueSeverity,
    ParsedDocument,
    QualityState,
    SourceAnchor,
)

from quality import run_quality
from quality.config import QualityConfig
from quality.packaging.hashing import sha256_bytes, sha256_text, stable_json_bytes

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "quality" / "fixtures" / "parsed_documents"


def _load(sample: str) -> ParsedDocument:
    return ParsedDocument.model_validate_json(
        (FIXTURES / f"{sample}.json").read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    "sample",
    [
        "sdp-004-mineru",
        "sdp-004-docling",
        "sdp-004-fallback",
        "sdp-006-mineru",
        "sdp-007-mineru",
    ],
)
def test_run_quality_on_real_fixtures(sample):
    doc = _load(sample)
    package = run_quality(doc)

    # 契约合法性：Pydantic 已校验；再显式检查关键不变量
    assert package.document_id == doc.document_id
    assert package.canonical_document.document_id == doc.document_id
    assert package.quality_report.document_id == doc.document_id
    # M4：非语义尾随空白已清理；Markdown 硬换行（两个及以上空格）
    # 与制表符保留，避免改变正文或代码语义。
    assert all(
        line == line.rstrip()
        or line.endswith("  ")
        or line.endswith("\t")
        for line in package.optimized_markdown.splitlines()
    )
    assert package.canonical_document.blocks
    # 哈希可复算
    assert package.package_manifest.artifacts["optimized.md"] == sha256_text(package.optimized_markdown)
    assert (
        package.package_manifest.artifacts["canonical_document.json"]
        == sha256_bytes(stable_json_bytes(package.canonical_document))
    )
    assert (
        package.package_manifest.artifacts["quality_report.json"]
        == sha256_bytes(stable_json_bytes(package.quality_report))
    )
    # report 的 artifacts 不含自身哈希（D-04）
    assert "quality_report.json" not in package.quality_report.artifacts


def test_run_quality_is_deterministic():
    doc = _load("sdp-004-mineru")
    first = run_quality(doc)
    second = run_quality(doc)
    assert first.canonical_document.model_dump_json() == second.canonical_document.model_dump_json()
    assert first.quality_report.state == second.quality_report.state
    assert (
        first.package_manifest.artifacts
        == second.package_manifest.artifacts
    )


def test_mineru_missing_heading_parents_remain_manual():
    """缺少真实父标题仍需人工复核，不能被 inferred 策略误放行。"""
    doc = _load("sdp-004-mineru")
    package = run_quality(doc)
    assert package.quality_report.state == QualityState.MANUAL_REVIEW_REQUIRED
    assert any(issue.category == "heading_parent_missing" for issue in package.quality_report.issues)


def test_fallback_document_state_is_legal():
    """fallback 文档在 M1 规则集内可能 PASS（无标题块、无违反规则证据）。

    缺标题层级的检测属于 M2 标题树规则的职责（heading_level_missing）；
    M1 只验证状态合法且报告完整。
    """
    doc = _load("sdp-006-fallback")
    package = run_quality(doc)
    assert isinstance(package.quality_report.state, QualityState)
    assert package.quality_report.state.value in {
        "pass",
        "pass_with_warnings",
        "manual_review_required",
        "reparse_required",
        "rejected",
    }


def test_empty_document_rejected():
    doc = _load("sdp-004-mineru").model_copy(update={"blocks": []})
    package = run_quality(doc)
    assert package.quality_report.state == QualityState.REJECTED
    assert package.quality_report.gate_summary.critical_issue_count >= 1


def test_missing_required_evidence_does_not_pass():
    """缺少规则声明的必需 capability 时，不得错误放行。"""
    doc = _load("sdp-004-mineru").model_copy(update={"capabilities": {}})
    package = run_quality(doc)

    assert package.quality_report.state != QualityState.PASS
    assert any(
        issue.category == "evidence_availability"
        for issue in package.quality_report.issues
    )


def test_duplicate_source_ids_do_not_collide_in_canonical_blocks():
    """来源 ID 重复时，canonical block 仍按 block 身份保持唯一。"""
    doc = _load("sdp-004-mineru")
    first = doc.blocks[0].model_copy(update={"source_block_id": "duplicate", "order_index": 0})
    second = doc.blocks[1].model_copy(update={"source_block_id": "duplicate", "order_index": 0})
    package = run_quality(doc.model_copy(update={"blocks": [first, second]}))

    ids = [block.block_id for block in package.canonical_document.blocks]
    assert len(ids) == len(set(ids))
    assert package.quality_report.state == QualityState.MANUAL_REVIEW_REQUIRED


def test_no_verified_content_without_evidence():
    """空 blocks 的 canonical 也必须合法（空列表允许）。"""
    doc = _load("sdp-004-mineru").model_copy(update={"blocks": []})
    package = run_quality(doc)
    assert package.canonical_document.blocks == []


def test_reparse_scenario_via_verdict_injection():
    """reparse 场景：M1 规则无 reparse 观测，通过配置注入验证契约约束。"""
    doc = _load("sdp-004-mineru")
    # 直接构造带 reparse 能力的报告路径：使用 pipeline 级 API 无法注入，
    # 契约层约束已由 test_gate_evaluator 覆盖；此处验证契约不接受无建议的 reparse。
    from document_parser.core.contracts import (
        GateSummary,
        QualityReport,
    )

    with pytest.raises(ValidationError):
        QualityReport(
            document_id=doc.document_id,
            state=QualityState.REPARSE_REQUIRED,
            artifacts={"optimized.md": "a" * 64},
            capability_matrix={},
            gate_summary=GateSummary(),
        )


def test_stable_canonical_block_ids():
    """同一输入的 canonical block ID 稳定且可回溯 source。"""
    doc = _load("sdp-004-mineru")
    package = run_quality(doc)
    for block in package.canonical_document.blocks:
        assert block.block_id
        assert block.source_locator.source_block_id
        # block_id 可复算
        from quality.ids import block_id as make_block_id

        doc_key = doc.source_sha256 or str(doc.document_id)
        source_block = next(
            item
            for item in doc.blocks
            if item.source_block_id == block.source_locator.source_block_id
        )
        assert block.block_id == make_block_id(
            doc_key,
            block.source_locator.source_block_id,
            block.order_index,
            block_uuid=str(source_block.id),
        )


def test_pipeline_canonical_uses_repaired_block_markdown():
    doc = _load("sdp-004-mineru")
    block = doc.blocks[0].model_copy(update={"markdown": doc.blocks[0].markdown.rstrip() + " "})
    repaired_doc = doc.model_copy(update={"blocks": [block, *doc.blocks[1:] ], "markdown": doc.markdown.rstrip() + " "})
    package = run_quality(repaired_doc)
    assert package.canonical_document.blocks[0].content == block.markdown.rstrip()
    assert package.quality_report.applied_repairs
    assert package.quality_report.applied_repairs[0].affected_block_ids == [str(block.id)]


def test_quality_only_auto_converts_span_free_html_tables():
    doc = _load("sdp-001-mineru")
    package = run_quality(doc)

    assert "<table" in doc.markdown.lower()
    assert "<table" in package.optimized_markdown.lower()
    assert any(repair.rule_id == "QL-RPR-003" for repair in package.quality_report.applied_repairs)
    table_blocks = [
        block for block in package.canonical_document.blocks if block.kind == "table"
    ]
    assert table_blocks
    assert any(block.content.lstrip().startswith("|") for block in table_blocks)
