import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser import DocumentParserGateway, ParseRequest  # noqa: E402
from document_parser.core.contracts import DocumentSignals, RoutingDecision, RoutingMode  # noqa: E402

from document_parser.parsers.registry import build_parser_registry, get_parser  # noqa: E402


def test_gateway_lists_registered_parsers() -> None:
    gateway = DocumentParserGateway.from_environment()

    parser_ids = {capability.parser_id for capability in gateway.list_parsers()}

    assert {"microsoft.markitdown", "docling", "mineru", "ocr"}.issubset(parser_ids)


def test_gateway_can_dispatch_to_docling_adapter() -> None:
    gateway = DocumentParserGateway.from_environment()
    request = ParseRequest(
        filename="sample.md",
        file_type="text/markdown",
        content=b"# Title\n\nBody.",
        parser_id="docling",
        options={},
    )

    parsed = gateway.parse(request)

    assert parsed.provenance.parser_id == "docling"
    assert parsed.routing_decision is not None
    assert parsed.routing_decision.selected_parser_id == "docling"
    assert parsed.markdown == "# Title\n\nBody."
    assert parsed.blocks[0].kind.value == "heading"


def test_parser_registry_resolves_known_adapters() -> None:
    registry = build_parser_registry()

    assert set(registry) == {"microsoft.markitdown", "anydoc", "docling", "mineru", "ocr"}
    assert get_parser("docling", registry).PARSER_ID == "docling"


def test_gateway_consumes_external_routing_decision() -> None:
    class FakeRouter:
        def route_request(self, request: ParseRequest) -> RoutingDecision:
            signals = DocumentSignals(
                extension=".md",
                size_bytes=len(request.content),
                has_text_layer=True,
            )
            return RoutingDecision(
                mode=RoutingMode.AUTO,
                selected_parser_id="docling",
                reason="test route",
                signals=signals,
                parser_options={"route_profile": "quality_first", "allow_cloud": True},
            )

    gateway = DocumentParserGateway(router=FakeRouter())
    request = ParseRequest(
        filename="sample.md",
        file_type="text/markdown",
        content=b"# Title\n\nBody.",
        parser_id=None,
        options={},
    )

    parsed = gateway.parse(request)

    assert parsed.provenance.parser_id == "docling"
    assert parsed.provenance.routing_mode == RoutingMode.AUTO
    assert parsed.provenance.requested_parser_id is None
    assert parsed.provenance.parameters["route_profile"] == "quality_first"
