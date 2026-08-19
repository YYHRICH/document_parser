import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser import (  # noqa: E402
    ParseConfidence,
    ParsedDocument,
    ParserProvenance,
    QualityPackage,
    QualityReport,
    RoutingDecision,
)


EXAMPLE_DIR = PROJECT_ROOT / "examples" / "contracts"


def load_example(filename: str) -> dict:
    with (EXAMPLE_DIR / filename).open("r", encoding="utf-8") as stream:
        return json.load(stream)


def test_routing_decision_fixed_example() -> None:
    decision = RoutingDecision.model_validate(load_example("routing_decision.json"))

    assert decision.selected_parser_id == "mineru"
    assert decision.mode.value == "auto"
    assert decision.fallback_parser_ids == ["docling", "ocr"]
    assert decision.signals.scanned_page_ratio == 0.15
    assert decision.parser_options["table"] is True


def test_parsed_document_fixed_example() -> None:
    document = ParsedDocument.model_validate(load_example("parsed_document.json"))

    assert document.schema_version == "2.2"
    assert document.provenance.parser_id == "mineru"
    assert document.routing_decision is not None
    assert document.routing_decision.selected_parser_id == document.provenance.parser_id
    assert document.tables[0].cells[3].text == "259"
    assert document.native_artifacts[0].required_for_quality is True
    assert document.capabilities["table_cells"].state.value == "available"


def test_quality_package_fixed_example() -> None:
    package = QualityPackage.model_validate(load_example("quality_package.json"))

    assert package.quality_report.state.value == "pass_with_warnings"
    assert package.canonical_document.table_bindings[0].column_path == ["Train 10%"]
    relation_types = {relation.relation_type for relation in package.canonical_document.relations}
    assert {"parent_child", "reference_of"}.issubset(relation_types)
    assert package.document_id == package.canonical_document.document_id
    assert package.document_id == package.quality_report.document_id


def test_fixed_examples_form_one_handoff_chain() -> None:
    parsed = ParsedDocument.model_validate(load_example("parsed_document.json"))
    package = QualityPackage.model_validate(load_example("quality_package.json"))

    parsed_source_ids = {block.source_block_id for block in parsed.blocks}
    canonical_source_ids = {
        block.source_locator.source_block_id
        for block in package.canonical_document.blocks
    }
    assert package.document_id == parsed.document_id
    assert canonical_source_ids.issubset(parsed_source_ids)
    assert package.canonical_document.table_bindings[0].table_id == parsed.tables[0].table_id
    assert package.optimized_markdown == parsed.markdown


def test_existing_parsed_document_callers_remain_compatible() -> None:
    document = ParsedDocument(
        filename="legacy.txt",
        file_type="text/plain",
        markdown="legacy content",
        blocks=[],
        confidence=ParseConfidence(),
        provenance=ParserProvenance(parser_id="markitdown"),
    )

    assert document.schema_version == "2.2"
    assert document.tables == []
    assert document.native_artifacts == []
    assert document.capabilities == {}


def test_manual_routing_must_select_the_requested_parser() -> None:
    payload = load_example("routing_decision.json")
    payload.update(
        {
            "mode": "manual",
            "requested_parser_id": "docling",
            "selected_parser_id": "mineru",
            "allow_automatic_fallback": False,
        }
    )

    with pytest.raises(ValidationError):
        RoutingDecision.model_validate(payload)


def test_reparse_quality_state_requires_a_recommendation() -> None:
    report = load_example("quality_package.json")["quality_report"]
    report["state"] = "reparse_required"
    report["reparse_recommendation"] = None

    with pytest.raises(ValidationError):
        QualityReport.model_validate(report)
