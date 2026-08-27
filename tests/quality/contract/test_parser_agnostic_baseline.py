"""P0 parser-agnostic quality baseline.

The matrix is intentionally derived from ParsedDocument evidence, not from
parser-specific quality branches.  Adding or replacing an archived fixture
requires an explicit expected-baseline update.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pytest

from document_parser.core.contracts import ParsedDocument

from quality import run_quality
from quality.packaging.hashing import sha256_bytes, sha256_text, stable_json_bytes


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "parsed_documents"
FIXTURE_PATHS = tuple(sorted(FIXTURES.glob("*.json")))

FRONTEND_PARSER_FAMILIES = frozenset(
    {"microsoft.markitdown", "docling", "mineru", "ocr", "anydoc"}
)
PROVENANCE_TO_FAMILY = {
    "microsoft.markitdown": "microsoft.markitdown",
    "docling-local": "docling",
    "mineru-cloud": "mineru",
    "pdfplumber-fallback": "fallback",
}
DOCUMENTED_FIXTURE_GAPS = frozenset({"ocr", "anydoc"})


@dataclass(frozen=True)
class ParserBaseline:
    fixture_count: int
    fixtures_with_tables: int
    fixtures_with_html_tables: int
    fixtures_with_cell_tables: int
    fixtures_with_ocr_spans: int
    page_bbox_states: frozenset[str]
    table_cell_states: frozenset[str]
    ocr_confidence_states: frozenset[str]


EXPECTED_BASELINE = {
    "microsoft.markitdown": ParserBaseline(
        fixture_count=1,
        fixtures_with_tables=0,
        fixtures_with_html_tables=0,
        fixtures_with_cell_tables=0,
        fixtures_with_ocr_spans=0,
        page_bbox_states=frozenset({"undeclared"}),
        table_cell_states=frozenset({"undeclared"}),
        ocr_confidence_states=frozenset({"undeclared"}),
    ),
    "docling": ParserBaseline(
        fixture_count=12,
        fixtures_with_tables=12,
        fixtures_with_html_tables=0,
        fixtures_with_cell_tables=12,
        fixtures_with_ocr_spans=0,
        page_bbox_states=frozenset({"available"}),
        table_cell_states=frozenset({"available"}),
        ocr_confidence_states=frozenset({"unavailable"}),
    ),
    "mineru": ParserBaseline(
        fixture_count=12,
        fixtures_with_tables=12,
        fixtures_with_html_tables=12,
        fixtures_with_cell_tables=12,
        fixtures_with_ocr_spans=0,
        page_bbox_states=frozenset({"available", "partial"}),
        table_cell_states=frozenset({"available"}),
        ocr_confidence_states=frozenset({"available", "unavailable"}),
    ),
    "fallback": ParserBaseline(
        fixture_count=8,
        fixtures_with_tables=3,
        fixtures_with_html_tables=0,
        fixtures_with_cell_tables=3,
        fixtures_with_ocr_spans=0,
        page_bbox_states=frozenset({"available"}),
        table_cell_states=frozenset({"partial"}),
        ocr_confidence_states=frozenset({"unavailable"}),
    ),
}


def _load(path: Path) -> ParsedDocument:
    return ParsedDocument.model_validate_json(path.read_text(encoding="utf-8"))


def _capability_state(document: ParsedDocument, name: str) -> str:
    capability = document.capabilities.get(name)
    return capability.state.value if capability is not None else "undeclared"


def _family(document: ParsedDocument) -> str:
    parser_id = document.provenance.parser_id
    try:
        return PROVENANCE_TO_FAMILY[parser_id]
    except KeyError as error:
        raise AssertionError(
            f"fixture uses undocumented parser provenance: {parser_id}"
        ) from error


def _summarize() -> dict[str, ParserBaseline]:
    grouped: dict[str, list[ParsedDocument]] = defaultdict(list)
    for path in FIXTURE_PATHS:
        document = _load(path)
        grouped[_family(document)].append(document)

    result: dict[str, ParserBaseline] = {}
    for family, documents in grouped.items():
        result[family] = ParserBaseline(
            fixture_count=len(documents),
            fixtures_with_tables=sum(bool(document.tables) for document in documents),
            fixtures_with_html_tables=sum(
                any(table.html for table in document.tables)
                for document in documents
            ),
            fixtures_with_cell_tables=sum(
                any(table.cells for table in document.tables)
                for document in documents
            ),
            fixtures_with_ocr_spans=sum(bool(document.ocr_spans) for document in documents),
            page_bbox_states=frozenset(
                _capability_state(document, "page_bbox")
                for document in documents
            ),
            table_cell_states=frozenset(
                _capability_state(document, "table_cells")
                for document in documents
            ),
            ocr_confidence_states=frozenset(
                _capability_state(document, "ocr_confidence")
                for document in documents
            ),
        )
    return result


def test_fixture_evidence_matrix_is_stable():
    assert len(FIXTURE_PATHS) == 33
    assert _summarize() == EXPECTED_BASELINE

    covered_frontend_families = set(_summarize()) & FRONTEND_PARSER_FAMILIES
    assert FRONTEND_PARSER_FAMILIES - covered_frontend_families == DOCUMENTED_FIXTURE_GAPS


@pytest.mark.parametrize("fixture_path", FIXTURE_PATHS, ids=lambda path: path.stem)
def test_every_archived_parser_fixture_runs_through_quality_unchanged(
    fixture_path: Path,
):
    source = fixture_path.read_bytes()
    document = ParsedDocument.model_validate_json(source.decode("utf-8"))

    package = run_quality(document)

    # Quality processing must not mutate the archived parser result.
    assert fixture_path.read_bytes() == source
    assert package.document_id == document.document_id
    assert package.canonical_document.document_id == document.document_id
    assert package.quality_report.document_id == document.document_id
    assert (
        package.package_manifest.artifacts["optimized.md"]
        == sha256_text(package.optimized_markdown)
    )
    assert (
        package.package_manifest.artifacts["canonical_document.json"]
        == sha256_bytes(stable_json_bytes(package.canonical_document))
    )

    # One trailing space is non-semantic and must not survive optimization.
    # Two or more spaces and tabs are preserved because they can carry Markdown
    # hard-break or code semantics.
    assert all(
        not (line.endswith(" ") and not line.endswith("  "))
        for line in package.optimized_markdown.splitlines()
    )
