"""P3 tests for parser-neutral table representation resolution."""

from __future__ import annotations

from pathlib import Path

from document_parser.core.contracts import EvidenceAvailability, ParsedDocument, TableCell

from quality.representations import QualityInputAdapter
from quality.representations.table_html import convert_html_tables
from quality.representations.tables import (
    TableRepresentationResolver,
    TableResolutionDecision,
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


def _resolve(document: ParsedDocument):
    inventory = QualityInputAdapter.from_parsed_document(document)
    return TableRepresentationResolver().resolve(document.tables[0], inventory)


def _span_cells() -> list[TableCell]:
    return [
        TableCell(text="Group", start_row=0, start_col=0),
        TableCell(text="Value", start_row=0, start_col=1),
        TableCell(text="A", start_row=1, start_col=0, row_span=2),
        TableCell(text="one", start_row=1, start_col=1),
        TableCell(text="two", start_row=2, start_col=1),
    ]


def _span_html() -> str:
    return (
        "<table><tr><th>Group</th><th>Value</th></tr>"
        "<tr><td rowspan=\"2\">A</td><td>one</td></tr>"
        "<tr><td>two</td></tr></table>"
    )


def test_span_free_html_resolves_to_an_exact_auto_safe_target():
    base = _load("sdp-001-mineru")
    table = base.tables[0].model_copy(
        update={
            "table_id": "span-free-html",
            "html": "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>",
            "markdown": None,
            "cells": [],
            "num_rows": 2,
            "num_cols": 2,
        }
    )
    document = base.model_copy(update={"tables": [table]})

    result = _resolve(document)

    assert result.decision == TableResolutionDecision.AUTO_SAFE_HTML_TO_MARKDOWN
    assert result.auto_safe and not result.review_required
    assert result.conversion_target is not None
    assert result.conversion_target.object_id == "span-free-html"
    assert result.conversion_target.field_path == "html"
    assert result.generated_markdown == "| A | B |\n| --- | --- |\n| 1 | 2 |"


def _span_free_cells() -> list[TableCell]:
    return [
        TableCell(text="A", start_row=0, start_col=0, column_header=True),
        TableCell(text="B", start_row=0, start_col=1, column_header=True),
        TableCell(text="1", start_row=1, start_col=0),
        TableCell(text="2", start_row=1, start_col=1),
    ]


def _with_partial_table_cells(document: ParsedDocument) -> ParsedDocument:
    capability = document.capabilities["table_cells"].model_copy(
        update={
            "state": EvidenceAvailability.PARTIAL,
            "reason": "Cell locator coverage is incomplete.",
        }
    )
    return document.model_copy(
        update={
            "capabilities": {
                **document.capabilities,
                "table_cells": capability,
            }
        }
    )


def test_partial_cells_with_a_verified_complete_grid_allow_html_conversion():
    base = _load("sdp-001-mineru")
    table = base.tables[0].model_copy(
        update={
            "table_id": "partial-complete-grid",
            "html": "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>",
            "markdown": None,
            "cells": _span_free_cells(),
            "num_rows": 2,
            "num_cols": 2,
        }
    )

    result = _resolve(_with_partial_table_cells(base.model_copy(update={"tables": [table]})))

    assert result.decision == TableResolutionDecision.AUTO_SAFE_HTML_TO_MARKDOWN
    assert result.auto_safe
    assert all(comparison.compatible for comparison in result.comparisons)


def test_partial_cells_with_an_incomplete_grid_still_require_review():
    base = _load("sdp-001-mineru")
    table = base.tables[0].model_copy(
        update={
            "table_id": "partial-incomplete-grid",
            "html": "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>",
            "markdown": None,
            "cells": _span_free_cells()[:-1],
            "num_rows": 2,
            "num_cols": 2,
        }
    )

    result = _resolve(_with_partial_table_cells(base.model_copy(update={"tables": [table]})))

    assert result.decision == TableResolutionDecision.REVIEW_INCONSISTENT
    assert result.review_required
    assert any("table_cells is incomplete" in comparison.reasons for comparison in result.comparisons)


def test_span_html_requires_review_when_no_existing_markdown_exists():
    base = _load("sdp-001-mineru")
    table = base.tables[0].model_copy(
        update={
            "table_id": "spanned-html",
            "html": _span_html(),
            "markdown": None,
            "cells": _span_cells(),
            "num_rows": 3,
            "num_cols": 2,
        }
    )

    result = _resolve(base.model_copy(update={"tables": [table]}))

    assert result.decision == TableResolutionDecision.LOSSY_HTML_PROJECTION_REVIEW
    assert result.review_required and not result.auto_safe
    assert result.has_spans
    assert result.generated_markdown == (
        "| Group | Value |\n| --- | --- |\n| A | one |\n|  | two |"
    )
    assert result.conversion_target is not None


def test_existing_markdown_can_be_used_when_it_matches_spanned_structure():
    base = _load("sdp-001-mineru")
    table = base.tables[0].model_copy(
        update={
            "table_id": "spanned-consistent",
            "html": _span_html(),
            "markdown": "| Group | Value |\n| --- | --- |\n| A | one |\n|  | two |",
            "cells": _span_cells(),
            "num_rows": 3,
            "num_cols": 2,
        }
    )

    result = _resolve(base.model_copy(update={"tables": [table]}))

    assert result.decision == TableResolutionDecision.USE_TABLE_MARKDOWN
    assert result.selected_representation is not None
    assert result.has_spans
    assert not result.review_required
    assert all(comparison.compatible for comparison in result.comparisons)


def test_conflicting_html_markdown_and_cells_are_never_silently_selected():
    base = _load("sdp-001-mineru")
    table = base.tables[0].model_copy(
        update={
            "table_id": "conflicting-representations",
            "html": _span_html(),
            "markdown": "| Group | Value |\n| --- | --- |\n| A | wrong |\n|  | two |",
            "cells": _span_cells(),
            "num_rows": 3,
            "num_cols": 2,
        }
    )

    result = _resolve(base.model_copy(update={"tables": [table]}))

    assert result.decision == TableResolutionDecision.REVIEW_INCONSISTENT
    assert result.review_required
    assert result.selected_representation is None
    assert any(not comparison.compatible for comparison in result.comparisons)
    assert any(comparison.mismatched_cells for comparison in result.comparisons)


def test_global_legacy_repair_skips_span_bearing_html():
    html = _span_html()

    assert convert_html_tables(html) == (html, 0)
