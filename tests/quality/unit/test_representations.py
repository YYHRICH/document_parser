"""P2 representation inventory tests."""

from __future__ import annotations

from pathlib import Path

from document_parser.core.contracts import (
    AssetKind,
    DocumentAsset,
    EvidenceAvailability,
    NativeArtifact,
    ParsedDocument,
)

from quality.evidence.context import EvidenceContext
from quality.evidence.requirements import EvidenceRequirement
from quality.packaging.hashing import sha256_bytes, sha256_text
from quality.representations import (
    QualityInputAdapter,
    RepresentationFidelity,
    RepresentationKind,
)


FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "quality"
    / "fixtures"
    / "parsed_documents"
)


def _load(sample: str) -> ParsedDocument:
    return ParsedDocument.model_validate_json(
        (FIXTURES / f"{sample}.json").read_text(encoding="utf-8")
    )


def test_mineru_inventory_uses_table_fields_not_parser_specific_logic():
    document = _load("sdp-001-mineru")
    inventory = QualityInputAdapter.from_parsed_document(document)

    assert inventory.parser_id == "mineru-cloud"
    assert len(inventory.for_kind(RepresentationKind.DOCUMENT_MARKDOWN)) == 1
    assert len(inventory.for_kind(RepresentationKind.BLOCK_MARKDOWN)) == len(document.blocks)
    assert len(inventory.for_kind(RepresentationKind.TABLE_HTML)) == len(document.tables)
    assert len(inventory.for_kind(RepresentationKind.TABLE_MARKDOWN)) == len(document.tables)
    assert len(inventory.for_kind(RepresentationKind.TABLE_CELLS)) == len(document.tables)

    table = document.tables[0]
    html = inventory.require(
        RepresentationKind.TABLE_HTML,
        object_id=table.table_id,
        field_path="html",
    )
    assert html.target.object_type == "table"
    assert html.target.object_id == table.table_id
    assert html.content_sha256 == sha256_text(table.html or "")
    assert html.fidelity == RepresentationFidelity.LOSSLESS
    assert html.evidence_refs[0].value_sha256 == html.content_sha256


def test_docling_and_fallback_table_evidence_is_derived_from_fields():
    docling = QualityInputAdapter.from_parsed_document(_load("sdp-004-docling"))
    fallback = QualityInputAdapter.from_parsed_document(_load("sdp-004-fallback"))

    assert not docling.for_kind(RepresentationKind.TABLE_HTML)
    assert docling.table_cells_status == (EvidenceAvailability.AVAILABLE, None)
    assert fallback.table_cells_status[0] == EvidenceAvailability.PARTIAL
    assert fallback.for_kind(RepresentationKind.TABLE_MARKDOWN)
    assert not fallback.for_kind(RepresentationKind.TABLE_HTML)


def test_markitdown_inventory_is_compatible_when_capabilities_are_undeclared():
    document = _load("p0-markitdown")
    inventory = QualityInputAdapter.from_parsed_document(document)

    markdown = inventory.require(
        RepresentationKind.DOCUMENT_MARKDOWN,
        object_id=str(document.document_id),
        field_path="markdown",
    )
    assert markdown.availability == EvidenceAvailability.AVAILABLE
    assert not inventory.for_kind(RepresentationKind.TABLE_CELLS)
    assert inventory.ocr_spans_status[0] == EvidenceAvailability.UNAVAILABLE


def test_inventory_tracks_assets_and_native_artifacts_as_exact_targets():
    base = _load("p0-markitdown")
    asset = DocumentAsset(
        path="assets/p0.png",
        kind=AssetKind.IMAGE,
        file_type="image/png",
        content=b"p0-asset",
    )
    artifact_hash = sha256_text("{}")
    artifact = NativeArtifact(
        artifact_id="p0-native",
        artifact_type="structured_content",
        path="native/p0.json",
        file_type="application/json",
        size_bytes=2,
        sha256=artifact_hash,
    )
    inventory = QualityInputAdapter.from_parsed_document(
        base.model_copy(
            update={
                "assets": [asset],
                "native_artifacts": [artifact],
            }
        )
    )

    asset_descriptor = inventory.require(
        RepresentationKind.ASSET,
        object_id=asset.path,
        field_path="content",
    )
    native_descriptor = inventory.require(
        RepresentationKind.NATIVE_ARTIFACT,
        object_id=artifact.artifact_id,
        field_path="path",
    )
    assert asset_descriptor.content_sha256 == sha256_bytes(asset.content)
    assert native_descriptor.content_sha256 == sha256_text(artifact.path)
    assert native_descriptor.metadata["declared_sha256"] == artifact.sha256


def test_declared_ocr_without_spans_is_unavailable_for_quality_requirements():
    document = next(
        _load(path.stem)
        for path in sorted(FIXTURES.glob("*-mineru.json"))
        if not _load(path.stem).ocr_spans
        and _load(path.stem).capabilities["ocr_confidence"].state
        == EvidenceAvailability.AVAILABLE
    )

    context = EvidenceContext(document)
    check = context.check_requirements(
        (EvidenceRequirement(kind="ocr_spans", required_state="available"),)
    )[0]

    assert context.representations.ocr_spans_status[0] == EvidenceAvailability.UNAVAILABLE
    assert check.state == EvidenceAvailability.UNAVAILABLE
    assert check.blocked
    assert "ocr_spans" in (check.reason or "")


def test_missing_cells_cannot_be_rescued_by_an_available_capability_declaration():
    document = _load("sdp-004-docling")
    incomplete = document.tables[0].model_copy(update={"cells": []})
    context = EvidenceContext(
        document.model_copy(update={"tables": [incomplete, *document.tables[1:]]})
    )

    full_requirement = (
        EvidenceRequirement(kind="table_cells", required_state="available"),
    )
    partial_requirement = (
        EvidenceRequirement(kind="table_cells", required_state="partial_allowed"),
    )
    assert context.check_requirements(full_requirement)[0].blocked
    partial_check = context.check_requirements(partial_requirement)[0]
    assert partial_check.limited
    assert partial_check.state == EvidenceAvailability.PARTIAL
