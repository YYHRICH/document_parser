"""EvidenceContext 单元测试：索引、能力判定、结构检测。

用真实解析 fixtures（MinerU/docling/pdfplumber 三路）验证可用性。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from document_parser.core.contracts import (
    BlockKind,
    EvidenceAvailability,
    ParsedDocument,
)

from quality.evidence.availability import AvailabilityResolver
from quality.evidence.context import EvidenceContext
from quality.evidence.requirements import EvidenceRequirement

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "quality" / "fixtures" / "parsed_documents"


def _load(sample: str) -> ParsedDocument:
    return ParsedDocument.model_validate_json(
        (FIXTURES / f"{sample}.json").read_text(encoding="utf-8")
    )


def test_index_blocks_by_id():
    doc = _load("sdp-004-mineru")
    ctx = EvidenceContext(doc)
    assert len(ctx.parsed.blocks) > 0
    first = ctx.parsed.blocks[0]
    assert ctx.block(str(first.id)) is first


def test_blocks_by_source_id():
    doc = _load("sdp-004-mineru")
    ctx = EvidenceContext(doc)
    source_id = doc.blocks[0].source_block_id
    found = ctx.blocks_by_source(source_id)
    assert found, "source_block_id 索引应非空"


def test_blocks_by_kind_and_tables():
    doc = _load("sdp-004-mineru")
    ctx = EvidenceContext(doc)
    assert len(ctx.blocks_by_kind(BlockKind.TABLE)) == len(doc.tables)
    for t in doc.tables:
        assert ctx.table(t.table_id) is t
        assert ctx.table_for_block(str(t.block_id)) is t


def test_duplicate_block_ids_detected():
    doc = _load("sdp-004-mineru")
    blocks = doc.blocks + [doc.blocks[0]]
    ctx = EvidenceContext(doc.model_copy(update={"blocks": blocks}))
    assert str(doc.blocks[0].id) in ctx.duplicate_block_ids


def test_ordered_blocks_deterministic():
    doc = _load("sdp-004-mineru")
    ctx = EvidenceContext(doc)
    ordered = ctx.ordered_blocks()
    indices = [b.order_index for b in ordered]
    # 稳定排序：order_index 非递减（None 排最前）
    assert indices == sorted(indices, key=lambda v: -1 if v is None else v)


# ---------- 能力判定 ----------

def test_table_cells_available_for_mineru():
    doc = _load("sdp-004-mineru")
    ctx = EvidenceContext(doc)
    req = (EvidenceRequirement(kind="table_cells", required_state="available"),)
    mode, reason = ctx.requirements_summary(req)
    assert mode == "allowed", reason


def test_table_cells_partial_for_fallback():
    doc = _load("sdp-004-fallback")
    ctx = EvidenceContext(doc)
    req = (EvidenceRequirement(kind="table_cells", required_state="available"),)
    mode, _ = ctx.requirements_summary(req)
    # fallback 声明 partial：要求 available 时 blocked
    assert mode == "blocked"
    # 允许 partial 时 limited
    req_partial = (EvidenceRequirement(kind="table_cells", required_state="partial_allowed"),)
    mode2, _ = ctx.requirements_summary(req_partial)
    assert mode2 == "limited"


def test_ocr_unavailable_with_reason():
    doc = _load("sdp-004-mineru")
    ctx = EvidenceContext(doc)
    req = (EvidenceRequirement(kind="ocr_spans", required_state="available"),)
    mode, reason = ctx.requirements_summary(req)
    assert mode == "blocked"
    assert reason, "blocked 必须带原因"


def test_table_capability_not_applicable_without_tables():
    """D-03：无表格文档中表格能力不适用，不阻塞。"""
    doc = _load("sdp-006-fallback")
    assert not doc.tables
    ctx = EvidenceContext(doc)
    req = (EvidenceRequirement(kind="table_cells", required_state="available"),)
    mode, _ = ctx.requirements_summary(req)
    assert mode == "not_applicable"
    check = ctx.check_requirements(req)[0]
    assert check.not_applicable


def test_blocks_requirement_always_available():
    doc = _load("sdp-004-docling")
    ctx = EvidenceContext(doc)
    req = (EvidenceRequirement(kind="blocks", required_state="available"),)
    assert ctx.requirements_summary(req)[0] == "allowed"


def test_availability_resolver_direct():
    resolver = AvailabilityResolver(capabilities={}, table_count=0)
    check = resolver.check(
        EvidenceRequirement(kind="table_bbox", required_state="available")
    )
    assert check.not_applicable
    assert check.allowed is False
