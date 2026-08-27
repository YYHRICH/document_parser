"""Architecture checks for the standalone routing module."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser import DocumentSignals, ParserCapability  # noqa: E402
from document_parser.routing import CapabilityRegistry, ModelRouter, RoutingSettings  # noqa: E402


def _docling_capability() -> ParserCapability:
    return ParserCapability(
        parser_id="docling",
        provider="fixture",
        display_name="Standalone Docling capability",
        formats={".pdf"},
        available=True,
    )


def test_router_runs_with_a_small_injected_capability_snapshot() -> None:
    router = ModelRouter(
        CapabilityRegistry.from_snapshot([_docling_capability()]),
        RoutingSettings(allow_cloud=True),
    )

    decision = router.route(
        DocumentSignals(extension="pdf", size_bytes=42, has_text_layer=True)
    )

    assert decision.selected_parser_id == "docling"
    assert decision.fallback_parser_ids == []
    assert decision.unavailable_reasons["mineru"].startswith("Parser is not present")


def test_capability_registry_isolated_from_caller_mutation() -> None:
    capability = _docling_capability()
    registry = CapabilityRegistry.from_snapshot([capability])

    capability.formats.add(".docx")

    assert registry.get("docling").formats == {".pdf"}


def test_routing_source_has_no_parser_or_gateway_imports() -> None:
    routing_dir = PROJECT_ROOT / "routing"
    forbidden = {"parsers", "gateway"}
    for source_path in routing_dir.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module_parts = set((node.module or "").split("."))
                assert not (module_parts & forbidden), (
                    f"{source_path.name} imports forbidden module {node.module!r}"
                )
                for imported in node.names:
                    imported_parts = set(imported.name.split("."))
                    assert not (imported_parts & forbidden), (
                        f"{source_path.name} imports forbidden symbol {imported.name!r}"
                    )
            elif isinstance(node, ast.Import):
                for imported in node.names:
                    module_parts = set(imported.name.split("."))
                    assert not (module_parts & forbidden), (
                        f"{source_path.name} imports forbidden module {imported.name!r}"
                    )


def test_importing_routing_does_not_load_parser_implementations() -> None:
    command = (
        "import sys; import document_parser.routing; "
        "assert not any(name == 'document_parser.parsers' or "
        "name.startswith('document_parser.parsers.') or "
        "name == 'document_parser.composition.gateway' for name in sys.modules)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=PROJECT_ROOT.parent,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
