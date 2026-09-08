import hashlib
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from document_parser.domain.model.contracts import (
    AssetKind,
    CanonicalDocument,
    DocumentAsset,
    GateSummary,
    ParsedDocument,
    ParseConfidence,
    ParserProvenance,
    QualityPackage,
    QualityReport,
    QualityState,
)
from document_parser.infra.delivery import DeliveryRejectedError, MobileworkDeliveryAdapter


def package(state: QualityState = QualityState.PASS, markdown: str = "# Hello\n\n![图](images/a.png)"):
    document_id = uuid4()
    content = b"image"
    document = ParsedDocument(
        document_id=document_id,
        filename="hello.pdf",
        file_type="application/pdf",
        source_sha256="1" * 64,
        markdown=markdown,
        blocks=[],
        assets=[
            DocumentAsset(
                path="images/a.png",
                kind=AssetKind.IMAGE,
                file_type="image/png",
                content=content,
                sha256=hashlib.sha256(content).hexdigest(),
            )
        ],
        confidence=ParseConfidence(),
        provenance=ParserProvenance(parser_id="fake"),
    )
    report = QualityReport(
        document_id=document_id,
        state=state,
        capability_matrix={},
        gate_summary=GateSummary(),
    )
    quality = QualityPackage(
        document_id=document_id,
        optimized_markdown=markdown,
        canonical_document=CanonicalDocument(document_id=document_id, blocks=[]),
        quality_report=report,
    )
    return document, quality


def test_publish_matches_mobilework_raw_contract(tmp_path: Path):
    document, quality = package()
    adapter = MobileworkDeliveryAdapter(tmp_path)
    result = adapter.publish(source_id="src_example1", parse_id="parse-1", document=document, quality_package=quality)

    source = tmp_path / "raw" / "sources" / "hello.md"
    assert source.is_file()
    text = source.read_text(encoding="utf-8")
    assert "../assets/src_example1/images/a.png" in text
    assert (tmp_path / "raw" / "assets" / "src_example1" / "images" / "a.png").read_bytes() == b"image"
    assert result["quality_state"] == "pass"
    assert (tmp_path / "raw" / "metadata" / "src_example1" / "quality_package.json").is_file()


def test_rejected_candidate_does_not_overwrite_last_good_source(tmp_path: Path):
    adapter = MobileworkDeliveryAdapter(tmp_path)
    document, good = package()
    adapter.publish(source_id="src_example1", parse_id="parse-1", document=document, quality_package=good)
    before = (tmp_path / "raw" / "sources" / "hello.md").read_bytes()
    _, rejected = package(QualityState.REJECTED, "bad")
    rejected = rejected.model_copy(update={"document_id": document.document_id, "canonical_document": rejected.canonical_document.model_copy(update={"document_id": document.document_id}), "quality_report": rejected.quality_report.model_copy(update={"document_id": document.document_id})})
    with pytest.raises(DeliveryRejectedError):
        adapter.publish(source_id="src_example1", parse_id="parse-2", document=document, quality_package=rejected)
    assert (tmp_path / "raw" / "sources" / "hello.md").read_bytes() == before


def test_withdraw_removes_only_watched_source(tmp_path: Path):
    document, quality = package()
    adapter = MobileworkDeliveryAdapter(tmp_path)
    adapter.publish(source_id="src_example1", parse_id="parse-1", document=document, quality_package=quality)
    adapter.withdraw("src_example1")
    assert not (tmp_path / "raw" / "sources" / "hello.md").exists()
    assert (tmp_path / "raw" / "assets" / "src_example1" / "images" / "a.png").exists()


def test_status_exposes_read_only_delivery_snapshot(tmp_path: Path):
    document, quality = package()
    adapter = MobileworkDeliveryAdapter(tmp_path)
    adapter.publish(source_id="src_example1", parse_id="parse-1", document=document, quality_package=quality)

    status = adapter.status()

    assert status["active_count"] == 1
    assert status["deleted_count"] == 0
    assert status["sources"][0]["source_path"] == "raw/sources/hello.md"


def test_relocate_changes_visible_filename_without_changing_content(tmp_path: Path):
    document, quality = package()
    adapter = MobileworkDeliveryAdapter(tmp_path)
    adapter.publish(source_id="src_example1", parse_id="parse-1", document=document, quality_package=quality)
    before = (tmp_path / "raw" / "sources" / "hello.md").read_bytes()

    result = adapter.relocate("src_example1", filename="新名称.pdf")

    assert not (tmp_path / "raw" / "sources" / "hello.md").exists()
    assert (tmp_path / "raw" / "sources" / "新名称.md").read_bytes() == before
    assert result["source_path"] == "raw/sources/新名称.md"


def test_publish_uses_visible_name_and_disambiguates_duplicates(tmp_path: Path):
    adapter = MobileworkDeliveryAdapter(tmp_path)
    document, quality = package()
    first = adapter.publish(
        source_id="src_example1",
        parse_id="parse-1",
        document=document,
        quality_package=quality,
    )
    second_document, second_quality = package()
    second = adapter.publish(
        source_id="src_example2",
        parse_id="parse-2",
        document=second_document,
        quality_package=second_quality,
    )

    assert first["source_path"] == "raw/sources/hello.md"
    assert second["source_path"] == "raw/sources/hello--example2.md"


def test_source_rename_replaces_visible_path_and_withdraw_uses_manifest(tmp_path: Path):
    adapter = MobileworkDeliveryAdapter(tmp_path)
    document, quality = package()
    adapter.publish(
        source_id="src_example1",
        parse_id="parse-1",
        document=document,
        quality_package=quality,
    )
    renamed = document.model_copy(update={"filename": "用户可见名称.pdf"})
    adapter.publish(
        source_id="src_example1",
        parse_id="parse-2",
        document=renamed,
        quality_package=quality,
    )

    assert not (tmp_path / "raw" / "sources" / "hello.md").exists()
    assert (tmp_path / "raw" / "sources" / "用户可见名称.md").is_file()
    adapter.withdraw("src_example1")
    assert not (tmp_path / "raw" / "sources" / "用户可见名称.md").exists()


def test_real_mobilework_scanner_observes_publish_modify_and_withdraw(tmp_path: Path):
    downstream = Path(__file__).resolve().parents[2] / "llmwiki" / "mobilework"
    if not downstream.is_dir():
        pytest.skip("mobilework checkout is not available")
    sys.path.insert(0, str(downstream))
    try:
        from wiki_maintainer.core import commit, initialize, prepare, record_source

        initialize(tmp_path)
        adapter = MobileworkDeliveryAdapter(tmp_path)
        document, quality = package(markdown="# Version one")
        adapter.publish(source_id="src_example1", parse_id="parse-1", document=document, quality_package=quality)
        first = prepare(tmp_path)
        assert first is not None and first["events"][0]["kind"] == "new"
        wiki_source_id = first["events"][0]["source_id"]
        record_source(tmp_path, first["batch_id"], wiki_source_id, [])
        commit(tmp_path, first["batch_id"])

        document2, quality2 = package(markdown="# Version two")
        adapter.publish(source_id="src_example1", parse_id="parse-2", document=document2, quality_package=quality2)
        second = prepare(tmp_path)
        assert second is not None and second["events"][0]["kind"] == "modified"
        record_source(tmp_path, second["batch_id"], wiki_source_id, [])
        commit(tmp_path, second["batch_id"])

        adapter.withdraw("src_example1")
        third = prepare(tmp_path)
        assert third is not None and third["events"][0]["kind"] == "deleted"
    finally:
        sys.path.remove(str(downstream))


def test_real_mobilework_scanner_observes_visible_filename_move(tmp_path: Path):
    downstream = Path(__file__).resolve().parents[2] / "llmwiki" / "mobilework"
    if not downstream.is_dir():
        pytest.skip("mobilework checkout is not available")
    sys.path.insert(0, str(downstream))
    try:
        from wiki_maintainer.core import commit, initialize, prepare, record_source

        initialize(tmp_path)
        adapter = MobileworkDeliveryAdapter(tmp_path)
        document, quality = package(markdown="# Same content")
        adapter.publish(source_id="src_example1", parse_id="parse-1", document=document, quality_package=quality)
        first = prepare(tmp_path)
        wiki_source_id = first["events"][0]["source_id"]
        record_source(tmp_path, first["batch_id"], wiki_source_id, [])
        commit(tmp_path, first["batch_id"])

        adapter.relocate("src_example1", filename="用户可见名称.pdf")
        moved = prepare(tmp_path)

        assert len(moved["events"]) == 1
        assert moved["events"][0]["kind"] == "moved"
        assert moved["events"][0]["source_id"] == wiki_source_id
        assert moved["events"][0]["old_path"] == "raw/sources/hello.md"
        assert moved["events"][0]["path"] == "raw/sources/用户可见名称.md"
    finally:
        sys.path.remove(str(downstream))
