from __future__ import annotations

from io import BytesIO

import openpyxl

from document_parser.infra.parsers.anydoc.structured import anydoc_document_to_payload
from document_parser.infra.parsers.anydoc.workbook import enrich_tables_with_workbook


def _paragraph(text: str) -> dict:
    return {"kind": "paragraph", "content": [{"kind": "text", "text": text}]}


def test_anydoc_document_preserves_origin_covered_and_nested_tables() -> None:
    child = {
        "kind": "table",
        "table": {
            "headerRows": 1,
            "kind": "data",
            "grid": [[{"kind": "origin", "cell": {"blocks": [_paragraph("子表值")], "rowSpan": 1, "colSpan": 1}}]],
        },
    }
    payload = {
        "schema_name": "AnyDocDocumentSidecar",
        "document": {
            "blocks": [
                {"kind": "heading", "level": 1, "content": [{"kind": "text", "text": "Sheet1"}]},
                {
                    "kind": "table",
                    "table": {
                        "headerRows": 1,
                        "kind": "data",
                        "grid": [
                            [
                                {
                                    "kind": "origin",
                                    "cell": {
                                        "blocks": [_paragraph("父表头"), child],
                                        "rowSpan": 1,
                                        "colSpan": 2,
                                    },
                                },
                                {"kind": "covered", "originRow": 0, "originCol": 0},
                            ]
                        ],
                    },
                },
            ]
        },
        "assets": [],
        "structured_error": None,
    }

    normalized = anydoc_document_to_payload(payload)

    assert len(normalized["tables"]) == 2
    parent, nested = normalized["tables"]
    assert parent["cells"][0]["text"] == "父表头"
    assert parent["grid"][0][1]["kind"] == "covered"
    assert nested["parent_table_id"] == parent["table_id"]
    assert nested["parent_cell_id"] == parent["cells"][0]["cell_id"]
    assert nested["nesting_depth"] == 1


def test_workbook_preprocessing_declares_visible_view_and_merge_count() -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(["地区", "值"])
    sheet.append(["华北", "=1+1"])
    sheet.append(["华南", 2])
    sheet.merge_cells("A1:B1")
    sheet.auto_filter.ref = "A1:B3"
    sheet.row_dimensions[3].hidden = True
    output = BytesIO()
    workbook.save(output)

    payload = {
        "tables": [
            {
                "table_id": "t1",
                "source_container_name": "Sheet1",
                "num_rows": 2,
                "num_cols": 2,
                "cells": [
                    {"cell_id": "t1:r0c0", "text": "地区", "start_row": 0, "start_col": 0},
                    {"cell_id": "t1:r1c0", "text": "华北", "start_row": 1, "start_col": 0},
                    {"cell_id": "t1:r1c1", "text": "2", "start_row": 1, "start_col": 1},
                ],
                "metadata": {},
            }
        ]
    }
    enriched, warnings = enrich_tables_with_workbook(
        payload,
        content=output.getvalue(),
        extension=".xlsx",
    )

    assert warnings == []
    table = enriched["tables"][0]
    assert table["view_scope"] == "visible_rows"
    assert table["source_has_filter"] is True
    assert table["source_row_count"] == 3
    assert table["emitted_row_count"] == 2
    assert table["hidden_row_count"] == 1
    assert table["metadata"]["merged_range_count"] == 1
    value_cell = table["cells"][2]
    assert value_cell["source_anchor"]["cell_ref"] == "B2"
    assert value_cell["raw_value"] == "=1+1"
    assert value_cell["formula"] == "=1+1"
    assert value_cell["value_type"] == "formula"
