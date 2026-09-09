"""Validate the fixed handoff examples without requiring pytest.

This is a lightweight smoke check for the parse-integration baseline. The
formal regression entry remains ``python -m pytest tests/test_contract_examples.py -q``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import ValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser import (  # noqa: E402
    ParsedDocument,
    QualityPackage,
    QualityReport,
    RoutingDecision,
)


EXAMPLE_DIR = PROJECT_ROOT / "examples" / "contracts"


def load_example(filename: str) -> dict:
    return json.loads((EXAMPLE_DIR / filename).read_text(encoding="utf-8"))


def record(checks: list[str], message: str) -> None:
    checks.append(message)
    print(f"[ok] {message}")


def main() -> None:
    checks: list[str] = []

    decision = RoutingDecision.model_validate(load_example("routing_decision.json"))
    assert decision.selected_parser_id == "mineru"
    assert decision.mode.value == "auto"
    assert decision.fallback_parser_ids == ["docling", "ocr"]
    assert decision.signals.scanned_page_ratio == 0.15
    assert decision.parser_options["table"] is True
    record(checks, "routing_decision.json validates as RoutingDecision")

    document = ParsedDocument.model_validate(load_example("parsed_document.json"))
    assert document.schema_name == "ParsedDocument"
    assert document.provenance.parser_id == "mineru"
    assert document.routing_decision is not None
    assert document.routing_decision.selected_parser_id == document.provenance.parser_id
    assert document.tables[0].cells[3].text == "259"
    assert document.native_artifacts[0].required_for_quality is True
    assert document.capabilities["table_cells"].state.value == "available"
    record(checks, "parsed_document.json validates as ParsedDocument")

    package = QualityPackage.model_validate(load_example("quality_package.json"))
    assert package.quality_report.state.value == "pass_with_warnings"
    assert package.canonical_document.table_bindings[0].column_path == ["Train 10%"]
    relation_types = {
        relation.relation_type for relation in package.canonical_document.relations
    }
    assert {"parent_child", "reference_of"}.issubset(relation_types)
    assert package.document_id == package.canonical_document.document_id
    assert package.document_id == package.quality_report.document_id
    record(checks, "quality_package.json validates as QualityPackage")

    parsed_source_ids = {block.source_block_id for block in document.blocks}
    canonical_source_ids = {
        block.source_locator.source_block_id
        for block in package.canonical_document.blocks
    }
    assert package.document_id == document.document_id
    assert canonical_source_ids.issubset(parsed_source_ids)
    assert package.canonical_document.table_bindings[0].table_id == (
        document.tables[0].table_id
    )
    assert package.optimized_markdown == document.markdown
    record(checks, "fixed examples form one handoff chain")

    manual_payload = load_example("routing_decision.json")
    manual_payload.update(
        {
            "mode": "manual",
            "requested_parser_id": "docling",
            "selected_parser_id": "mineru",
            "allow_automatic_fallback": False,
        }
    )
    try:
        RoutingDecision.model_validate(manual_payload)
    except ValidationError:
        record(checks, "manual routing mismatch is rejected")
    else:
        raise AssertionError("manual routing mismatch should fail")

    report = load_example("quality_package.json")["quality_report"]
    report["state"] = "reparse_required"
    report["reparse_recommendation"] = None
    try:
        QualityReport.model_validate(report)
    except ValidationError:
        record(checks, "reparse_required without recommendation is rejected")
    else:
        raise AssertionError("reparse_required without recommendation should fail")

    print(f"[done] {len(checks)} contract baseline checks passed")


if __name__ == "__main__":
    main()
