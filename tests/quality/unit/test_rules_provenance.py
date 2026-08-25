"""QL-PROV-* 来源规则单元测试（真实 fixtures + 合成场景）。"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from document_parser.domain.model.contracts import (
    BlockKind,
    DocumentBlock,
    EvidenceAvailability,
    EvidenceCapability,
    IssueSeverity,
    NativeArtifact,
    ParsedDocument,
    QualityCapabilityState,
    SourceAnchor,
)

from document_parser.domain.quality.evidence.context import EvidenceContext
from document_parser.domain.quality.rules.provenance import (
    QL_PROV_001_SourceTraceable,
    QL_PROV_002_AnchorValid,
    QL_PROV_003_ArtifactsValid,
    QL_PROV_004_CapabilityReasons,
)

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "quality" / "fixtures" / "parsed_documents"


def _load(sample: str) -> ParsedDocument:
    return ParsedDocument.model_validate_json(
        (FIXTURES / f"{sample}.json").read_text(encoding="utf-8")
    )


def _make_doc(*blocks: DocumentBlock, **updates) -> ParsedDocument:
    base = _load("sdp-004-mineru")
    return base.model_copy(update={"blocks": list(blocks), **updates})


def _block(source_id: str | None = "src-1", **kwargs) -> DocumentBlock:
    defaults = dict(
        id=uuid4(),
        source_block_id=source_id,
        order_index=0,
        kind=BlockKind.PARAGRAPH,
        text="text",
        markdown="text",
        anchor=SourceAnchor(),
    )
    defaults.update(kwargs)
    return DocumentBlock(**defaults)


# ---------- QL-PROV-001 ----------

def test_prov001_clean_verified():
    doc = _load("sdp-004-mineru")
    result = QL_PROV_001_SourceTraceable().execute(EvidenceContext(doc))
    assert result.issues == ()
    assert (
        result.capability_observations[0].observed_state
        == QualityCapabilityState.VERIFIED
    )


def test_prov001_missing_source_block_id_warning():
    doc = _make_doc(_block(source_id=None))
    result = QL_PROV_001_SourceTraceable().execute(EvidenceContext(doc))
    assert any(i.severity == IssueSeverity.WARNING for i in result.issues)
    assert (
        result.capability_observations[0].observed_state
        == QualityCapabilityState.MANUAL_REVIEW_REQUIRED
    )


def test_prov001_duplicated_source_id_warning():
    doc = _make_doc(_block(source_id="dup"), _block(source_id="dup"))
    result = QL_PROV_001_SourceTraceable().execute(EvidenceContext(doc))
    assert any(i.severity == IssueSeverity.WARNING for i in result.issues)


# ---------- QL-PROV-002 ----------

def test_prov002_invalid_bbox_warning():
    bad = _block(anchor=SourceAnchor(bbox=(100.0, 100.0, 50.0, 60.0)))  # r < l
    doc = _make_doc(bad)
    result = QL_PROV_002_AnchorValid().execute(EvidenceContext(doc))
    assert any(i.severity == IssueSeverity.WARNING for i in result.issues)


def test_prov002_bottomleft_bbox_uses_native_axis_order():
    block = _block(
        anchor=SourceAnchor(
            bbox=(10.0, 700.0, 100.0, 680.0),
            coordinate_system="bottom_left_absolute",
        )
    )
    result = QL_PROV_002_AnchorValid().execute(EvidenceContext(_make_doc(block)))
    assert result.issues == ()


def test_prov002_granularity_without_bbox_warning():
    inconsistent = _block(anchor=SourceAnchor(bbox_granularity="block"))
    doc = _make_doc(inconsistent)
    result = QL_PROV_002_AnchorValid().execute(EvidenceContext(doc))
    assert any(i.severity == IssueSeverity.WARNING for i in result.issues)


def test_prov002_valid_bbox_clean():
    ok = _block(anchor=SourceAnchor(bbox=(10.0, 10.0, 500.0, 300.0)))
    doc = _make_doc(ok)
    result = QL_PROV_002_AnchorValid().execute(EvidenceContext(doc))
    assert result.issues == ()


def test_prov002_invalid_table_bbox_warning():
    doc = _load("sdp-004-mineru")
    table = doc.tables[0].model_copy(update={"bbox": (500.0, 100.0, 10.0, 200.0)})
    result = QL_PROV_002_AnchorValid().execute(
        EvidenceContext(doc.model_copy(update={"tables": [table]}))
    )
    assert any(i.severity == IssueSeverity.WARNING for i in result.issues)


# ---------- QL-PROV-003 ----------

def test_prov003_bad_artifact_hash():
    """防御分支：契约校验被绕过（model_construct）时规则仍能发现坏哈希。"""
    doc = _load("sdp-004-mineru")
    bad_artifact = NativeArtifact.model_construct(
        artifact_id="bad",
        artifact_type="structured_content",
        path="native/bad.json",
        file_type="application/json",
        size_bytes=1,
        sha256="short",  # 非法哈希：正常构造会被契约 validator 拒绝
        required_for_quality=True,
    )
    result = QL_PROV_003_ArtifactsValid().execute(
        EvidenceContext(doc.model_copy(update={"native_artifacts": [bad_artifact]}))
    )
    assert any(i.severity == IssueSeverity.CRITICAL for i in result.issues)
    assert (
        result.capability_observations[0].observed_state
        == QualityCapabilityState.REJECTED
    )


def test_prov003_non_hex_artifact_hash_is_rejected():
    """防御分支：64 位但非十六进制的哈希也必须被发现。"""
    doc = _load("sdp-004-mineru")
    bad_artifact = NativeArtifact.model_construct(
        artifact_id="bad-non-hex",
        artifact_type="structured_content",
        path="native/bad.json",
        file_type="application/json",
        size_bytes=1,
        sha256="z" * 64,
        required_for_quality=True,
    )
    result = QL_PROV_003_ArtifactsValid().execute(
        EvidenceContext(doc.model_copy(update={"native_artifacts": [bad_artifact]}))
    )

    assert any(i.severity == IssueSeverity.CRITICAL for i in result.issues)
    assert result.capability_observations[0].observed_state == QualityCapabilityState.REJECTED


def test_prov003_clean_verified():
    doc = _load("sdp-004-mineru")
    result = QL_PROV_003_ArtifactsValid().execute(EvidenceContext(doc))
    assert result.issues == ()


# ---------- QL-PROV-004 ----------

def test_prov004_missing_reason_critical():
    """防御分支：契约校验被绕过（model_construct）时规则仍能发现缺 reason。"""
    doc = _load("sdp-004-mineru")
    bad_caps = {
        "ocr_confidence": EvidenceCapability.model_construct(
            state=EvidenceAvailability.UNAVAILABLE,  # 无 reason：正常构造会被拒绝
        )
    }
    result = QL_PROV_004_CapabilityReasons().execute(
        EvidenceContext(doc.model_copy(update={"capabilities": bad_caps}))
    )
    assert any(i.severity == IssueSeverity.CRITICAL for i in result.issues)


def test_prov004_with_reason_clean():
    doc = _load("sdp-004-mineru")
    caps = {
        "ocr_confidence": EvidenceCapability(
            state=EvidenceAvailability.UNAVAILABLE,
            reason="本次未启用 OCR。",
        )
    }
    result = QL_PROV_004_CapabilityReasons().execute(
        EvidenceContext(doc.model_copy(update={"capabilities": caps}))
    )
    assert result.issues == ()


def test_rule_ids_are_stable():
    assert QL_PROV_001_SourceTraceable.rule_id == "QL-PROV-001"
    assert QL_PROV_002_AnchorValid.rule_id == "QL-PROV-002"
    assert QL_PROV_003_ArtifactsValid.rule_id == "QL-PROV-003"
    assert QL_PROV_004_CapabilityReasons.rule_id == "QL-PROV-004"
