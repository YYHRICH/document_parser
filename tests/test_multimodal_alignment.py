import pytest

from document_parser.domain.model.contracts import (
    SourceAnchor,
    VisualClaim,
    VisualClaimProvenance,
    VisualEvidence,
    VisualEvidenceKind,
    VisualEvidenceProvenance,
    VisualEvidenceStatus,
)
from document_parser.infra.parsers.mmwiki_contract import MmwikiBBox, MmwikiTableContent


def test_ready_visual_evidence_preserves_model_and_claim_provenance():
    evidence = VisualEvidence(
        id="ve-asset-1-image_caption",
        kind=VisualEvidenceKind.IMAGE_CAPTION,
        text="图片中有三个模块",
        asset_id="asset-1",
        parent_item_ids=["item-p0001-b0001"],
        parent_chunk_ids=["chunk-1"],
        page_refs=[1],
        status=VisualEvidenceStatus.READY,
        searchable=True,
        provenance=VisualEvidenceProvenance(
            source="vlm", model="qwen3-vl-plus", prompt_version="v1"
        ),
        claims=[VisualClaim(statement="三个模块", provenance=VisualClaimProvenance.EXTRACTED)],
    )
    assert evidence.provenance.model == "qwen3-vl-plus"


def test_non_ready_visual_evidence_cannot_be_searchable():
    with pytest.raises(ValueError, match="searchable=false"):
        VisualEvidence(
            id="ve-asset-1-image_ocr",
            kind=VisualEvidenceKind.IMAGE_OCR,
            asset_id="asset-1",
            status=VisualEvidenceStatus.SKIPPED,
            searchable=True,
            reason="policy",
        )


def test_mmwiki_table_rows_are_a_string_matrix_and_html_is_retained():
    table = MmwikiTableContent(
        rows=[["季度", "销售额（万元）", "同比"], ["第一季度", "120", "10%"]],
        html="<table><tr><th>季度</th></tr></table>",
    )
    assert table.rows[1][2] == "10%"
    assert table.html.startswith("<table>")


def test_mmwiki_normalized_bbox_converts_using_physical_page_size():
    bbox = MmwikiBBox(
        values=(100, 200, 800, 700), page_width=595, page_height=842
    )
    assert bbox.to_page_coordinates() == pytest.approx((59.5, 168.4, 476.0, 589.4))
    anchor = SourceAnchor(
        bbox=bbox.values,
        page_width=bbox.page_width,
        page_height=bbox.page_height,
        coordinate_system=bbox.coordinate_system,
        origin=bbox.origin,
        page_unit=bbox.page_unit,
    )
    assert anchor.bbox == (100, 200, 800, 700)


def test_normalized_bbox_rejects_values_outside_0_to_1000():
    with pytest.raises(ValueError, match="0 到 1000"):
        MmwikiBBox(
            values=(0, 0, 1001, 500), page_width=595, page_height=842
        )


def test_mmwiki_bbox_without_page_size_stays_usable_but_cannot_convert():
    bbox = MmwikiBBox(values=(100, 200, 800, 700))
    assert bbox.values == (100, 200, 800, 700)
    with pytest.raises(ValueError, match="缺少 page_width/page_height"):
        bbox.to_page_coordinates()
