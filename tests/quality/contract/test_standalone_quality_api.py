"""Standalone quality API and architecture boundary tests."""

from __future__ import annotations

import ast
import builtins
from pathlib import Path
import subprocess
import sys
from uuid import UUID

import pytest

from quality import (
    QualityEvidenceNegotiator,
    get_quality_evidence_requirements,
    inspect_quality_capabilities,
    run_quality,
)
from quality.contracts import (
    BlockKind,
    DocumentBlock,
    EvidenceAvailability,
    EvidenceCapability,
    ParseConfidence,
    ParsedDocument,
    ParserProvenance,
    SourceAnchor,
)
from quality.evidence import EvidenceRequirement
from quality.pipeline import QUALITY_RULES


DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000001")
HEADING_ID = UUID("00000000-0000-0000-0000-000000000002")
PARAGRAPH_ID = UUID("00000000-0000-0000-0000-000000000003")


def _memory_document(*, parser_id: str = "memory-fixture") -> ParsedDocument:
    """Construct a valid input without fixtures, routing, parsers, or paths."""

    return ParsedDocument(
        document_id=DOCUMENT_ID,
        filename="memory.md",
        file_type="text/markdown",
        markdown="# Heading\n\nBody.",
        blocks=[
            DocumentBlock(
                id=HEADING_ID,
                source_block_id="memory-heading",
                order_index=0,
                kind=BlockKind.HEADING,
                text="Heading",
                heading_level=1,
                markdown="# Heading",
                anchor=SourceAnchor(page_number=1),
            ),
            DocumentBlock(
                id=PARAGRAPH_ID,
                source_block_id="memory-paragraph",
                order_index=1,
                kind=BlockKind.PARAGRAPH,
                text="Body.",
                markdown="Body.",
                anchor=SourceAnchor(page_number=1),
            ),
        ],
        confidence=ParseConfidence(),
        provenance=ParserProvenance(parser_id=parser_id),
        capabilities={
            "page_bbox": EvidenceCapability(
                state=EvidenceAvailability.AVAILABLE,
                granularity="block",
            )
        },
    )


def test_run_quality_accepts_only_an_in_memory_parsed_document(monkeypatch):
    """The compute entry must not open, read, write, or require any directory."""

    document = _memory_document()
    before = document.model_dump_json()

    def no_filesystem(*_args, **_kwargs):
        raise AssertionError("run_quality must not access the filesystem")

    monkeypatch.setattr(builtins, "open", no_filesystem)
    monkeypatch.setattr(Path, "open", no_filesystem)
    monkeypatch.setattr(Path, "read_bytes", no_filesystem)
    monkeypatch.setattr(Path, "read_text", no_filesystem)
    monkeypatch.setattr(Path, "write_bytes", no_filesystem)
    monkeypatch.setattr(Path, "write_text", no_filesystem)

    package = run_quality(document)

    assert document.routing_decision is None
    assert document.model_dump_json() == before
    assert package.document_id == DOCUMENT_ID
    assert package.quality_report.metrics["source_block_count"] == 2
    assert len(package.quality_report.metrics["evidence_negotiation"]) == len(
        QUALITY_RULES
    )


def test_quality_evidence_contract_is_immutable_and_auditable():
    document = _memory_document()
    requirements = get_quality_evidence_requirements()
    declaration = inspect_quality_capabilities(document)

    assert requirements.rule_ids == tuple(sorted(rule.rule_id for rule in QUALITY_RULES))
    assert "QL-CONT-001" in requirements.by_rule_id
    assert declaration.table_count == 0
    assert declaration.document_schema_name == "ParsedDocument"
    assert not hasattr(declaration, "parser_id")

    with pytest.raises(TypeError):
        requirements.by_rule_id["QL-TEST-001"] = ()

    negotiator = QualityEvidenceNegotiator(declaration)
    table_result = negotiator.negotiate(
        "QL-TBL-004",
        requirements.for_rule("QL-TBL-004"),
    )
    assert table_result.mode == "not_applicable"

    missing_ocr = negotiator.negotiate(
        "QL-TEST-OCR",
        (EvidenceRequirement(kind="ocr_spans", required_state="available"),),
    )
    assert missing_ocr.mode == "blocked"
    assert missing_ocr.checks[0].reason


def test_quality_behavior_does_not_branch_on_parser_identity():
    first = run_quality(_memory_document(parser_id="parser-a"))
    second = run_quality(_memory_document(parser_id="parser-b"))

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_fresh_quality_import_does_not_load_feature_modules_or_writer():
    """The standalone import path must not initialize application composition."""

    project_root = Path(__file__).resolve().parents[3]
    script = """
import sys
import quality
forbidden = (
    'routing',
    'parsers',
    'backend',
    'normalizers',
    'document_parser.routing',
    'document_parser.parsers',
    'document_parser.backend',
)
unexpected = [name for name in forbidden if name in sys.modules]
assert not unexpected, unexpected
assert 'quality.packaging.writer' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


_FORBIDDEN_QUALITY_IMPORT_PREFIXES = (
    "routing",
    "parsers",
    "backend",
    "normalizers",
    "document_parser.routing",
    "document_parser.parsers",
    "document_parser.backend",
    "document_parser.normalizers",
)


def _forbidden_module(module: str) -> bool:
    return any(
        module == prefix or module.startswith(f"{prefix}.")
        for prefix in _FORBIDDEN_QUALITY_IMPORT_PREFIXES
    )


def test_quality_source_has_no_feature_module_imports():
    """Guard the declared architecture boundary even for future lazy code paths."""

    project_root = Path(__file__).resolve().parents[3]
    violations: list[str] = []
    for source_path in sorted((project_root / "quality").rglob("*.py")):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [name.name for name in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                if _forbidden_module(module):
                    violations.append(f"{source_path.relative_to(project_root)}:{module}")

    assert not violations, "quality must not import feature modules: " + ", ".join(violations)
