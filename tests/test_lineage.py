from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.backend.lineage import (  # noqa: E402
    DifferentSourceIdentityError,
    build_lineage_snapshot,
    build_same_source_comparison,
    resolve_lineage,
    same_source_identity,
    summarize_document_structure,
)
from document_parser.core.contracts import (  # noqa: E402
    AssetKind,
    BlockKind,
    DocumentAsset,
    DocumentBlock,
    OcrSpan,
    ParseConfidence,
    ParsedDocument,
    ParsedTable,
    ParserProvenance,
)
from document_parser.orchestration import ParseAttemptRecord, ParseJob  # noqa: E402


def _job(
    parse_id: str,
    *,
    source_sha256: str = "a" * 64,
    source_file_type: str = "text/markdown",
    options: dict[str, object] | None = None,
    requested_parser_id: str | None = "docling",
    attempts: list[ParseAttemptRecord] | None = None,
) -> ParseJob:
    created_at = datetime(2026, 8, 26, 1, 0, tzinfo=UTC)
    return ParseJob(
        parse_id=parse_id,
        source_sha256=source_sha256,
        source_filename="internal-name.md",
        source_file_type=source_file_type,
        source_size_bytes=24,
        requested_parser_id=requested_parser_id,
        options=options or {},
        attempts=attempts or [],
        created_at=created_at,
        updated_at=created_at + timedelta(seconds=2),
    )


def _document() -> ParsedDocument:
    heading_id = uuid4()
    table_block_id = uuid4()
    return ParsedDocument(
        filename="private-source.md",
        file_type="text/markdown",
        source_size_bytes=24,
        source_sha256="a" * 64,
        markdown="# Private heading\n\nVery private body",
        blocks=[
            DocumentBlock(
                id=heading_id,
                kind=BlockKind.HEADING,
                text="Private heading",
                markdown="# Private heading",
            ),
            DocumentBlock(
                id=table_block_id,
                kind=BlockKind.TABLE,
                text="very private cell",
                markdown="| A |\n| - |\n| B |",
            ),
        ],
        assets=[
            DocumentAsset(
                path="private-image.png",
                kind=AssetKind.IMAGE,
                file_type="image/png",
                content=b"image-bytes",
            )
        ],
        tables=[ParsedTable(table_id="table-1", block_id=table_block_id)],
        ocr_spans=[OcrSpan(level="word", text="private OCR", bbox=(0, 0, 1, 1))],
        confidence=ParseConfidence(),
        provenance=ParserProvenance(parser_id="docling"),
        warnings=["private warning"],
    )


def test_same_source_comparison_is_content_free_and_reports_structural_deltas() -> None:
    left = _job(
        "left",
        options={
            "language": "zh",
            "apiToken": "ultra-secret-option-value",
            "nested": {"password": "also-private"},
        },
        attempts=[
            ParseAttemptRecord(parser_id="docling", status="succeeded", duration_ms=120),
        ],
    )
    right = _job(
        "right",
        options={"language": "en"},
        requested_parser_id="mineru",
        attempts=[
            ParseAttemptRecord(parser_id="mineru", status="failed", duration_ms=200),
        ],
    )
    left_counts = summarize_document_structure(_document())
    right_counts = dict(left_counts)
    right_counts["block_count"] = 3
    right_counts["table_count"] = 2

    comparison = build_same_source_comparison(
        left,
        right,
        structural_counts_by_parse_id={"left": left_counts, "right": right_counts},
    )

    serialized = json.dumps(comparison, sort_keys=True)
    assert comparison["same_source"] is True
    assert comparison["differences"]["requested_parser_changed"] is True
    assert comparison["differences"]["options_changed"] is True
    assert comparison["differences"]["structural_counts_delta"]["block_count"] == 1
    assert comparison["differences"]["structural_counts_delta"]["table_count"] == 1
    assert comparison["left"]["request"]["options"]["keys"] == [
        "<redacted>",
        "language",
        "nested",
    ]
    assert "ultra-secret-option-value" not in serialized
    assert "also-private" not in serialized
    assert "private heading" not in serialized
    assert "private-source.md" not in serialized
    assert "source_sha256" not in serialized
    assert "package_path" not in serialized
    assert comparison["left"]["structural_counts"]["block_kind_counts"] == {
        "heading": 1,
        "table": 1,
    }


def test_comparison_requires_digest_size_and_file_type_identity() -> None:
    left = _job("left")
    different_type = _job("right", source_file_type="application/pdf")
    different_digest = _job("other", source_sha256="b" * 64)

    assert same_source_identity(left, different_type) is False
    assert same_source_identity(left, different_digest) is False
    with pytest.raises(DifferentSourceIdentityError):
        build_same_source_comparison(left, different_digest)

def test_resolve_lineage_only_walks_the_parent_chain_and_stops_safely() -> None:
    root = _job("root")
    child = _job("child").model_copy(update={"parent_parse_id": root.parse_id})
    unrelated = _job("unrelated")
    lookup = {root.parse_id: root, child.parse_id: child, unrelated.parse_id: unrelated}
    calls: list[str] = []

    def load_job(parse_id: str) -> ParseJob:
        calls.append(parse_id)
        return lookup[parse_id]

    resolution = resolve_lineage(child, load_job)
    assert [job.parse_id for job in resolution.jobs] == [root.parse_id, child.parse_id]
    assert resolution.complete is True
    assert resolution.integrity == "verified"
    assert calls == [root.parse_id]

    bounded = resolve_lineage(child, load_job, max_depth=1)
    assert [job.parse_id for job in bounded.jobs] == [child.parse_id]
    assert bounded.complete is False
    assert bounded.integrity == "depth_limit_reached"
    bounded_snapshot = build_lineage_snapshot(
        child,
        bounded.jobs,
        lineage_complete=bounded.complete,
        lineage_integrity=bounded.integrity,
    )
    assert bounded_snapshot["root_parse_id"] is None

    cyclic_root = root.model_copy(update={"parent_parse_id": child.parse_id})
    cycle_lookup = {cyclic_root.parse_id: cyclic_root, child.parse_id: child}
    cyclic = resolve_lineage(child, cycle_lookup.__getitem__)
    assert [job.parse_id for job in cyclic.jobs] == [cyclic_root.parse_id, child.parse_id]
    assert cyclic.complete is False
    assert cyclic.integrity == "cycle_detected"

    missing = resolve_lineage(child, lambda _: (_ for _ in ()).throw(FileNotFoundError()))
    assert [job.parse_id for job in missing.jobs] == [child.parse_id]
    assert missing.complete is False
    assert missing.integrity == "parent_not_found"

