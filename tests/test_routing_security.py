import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.core.contracts import (  # noqa: E402
    DocumentSignals,
    ParseRequest,
    ParserCapability,
)
from document_parser.routing import (  # noqa: E402
    CapabilityRegistry,
    CloudParserForbiddenError,
    InvalidRoutingOptionError,
    ModelRouter,
    RoutingSettings,
)


def _router(*, allow_cloud: bool) -> ModelRouter:
    registry = CapabilityRegistry(
        [
            ParserCapability(
                parser_id="mineru",
                provider="test",
                display_name="MinerU",
                formats={".pdf"},
                requires_network=True,
                available=True,
            ),
            ParserCapability(
                parser_id="docling",
                provider="test",
                display_name="Docling",
                formats={".pdf"},
                available=True,
            ),
            ParserCapability(
                parser_id="ocr",
                provider="test",
                display_name="OCR",
                formats={".pdf"},
                available=True,
            ),
            ParserCapability(
                parser_id="microsoft.markitdown",
                provider="test",
                display_name="MarkItDown",
                formats={".pdf"},
                available=True,
            ),
            ParserCapability(
                parser_id="anydoc",
                provider="test",
                display_name="AnyDoc",
                formats={".pdf"},
                available=True,
            ),
        ]
    )
    return ModelRouter(registry, RoutingSettings(allow_cloud=allow_cloud))


def _pdf_signals() -> DocumentSignals:
    return DocumentSignals(
        extension=".pdf",
        size_bytes=100,
        has_text_layer=True,
    )


def test_server_cloud_policy_cannot_be_reenabled_by_request_preference() -> None:
    router = _router(allow_cloud=False)

    decision = router.route(_pdf_signals(), allow_cloud=True)

    assert decision.selected_parser_id == "docling"
    assert decision.unavailable_reasons["mineru"] == "allow_cloud=false forbids cloud parsing."
    assert decision.parser_options["allow_cloud"] is False


def test_string_false_request_preference_disables_cloud_routing() -> None:
    router = _router(allow_cloud=True)
    request = ParseRequest(
        filename="paper.pdf",
        file_type="application/pdf",
        content=b"%PDF-1.7\nfixture",
        options={"allow_cloud": "false"},
    )

    decision = router.route_request(request)

    assert decision.selected_parser_id == "docling"
    assert decision.parser_options["allow_cloud"] is False


def test_manual_cloud_selection_obeys_server_cloud_policy() -> None:
    router = _router(allow_cloud=False)

    with pytest.raises(CloudParserForbiddenError, match="mineru"):
        router.route(
            _pdf_signals(),
            requested_parser_id="mineru",
            allow_cloud=True,
        )


def test_invalid_cloud_preference_is_rejected_explicitly() -> None:
    router = _router(allow_cloud=True)

    with pytest.raises(InvalidRoutingOptionError, match="allow_cloud"):
        router.route(_pdf_signals(), allow_cloud="sometimes")


def test_routing_settings_rejects_untrusted_mineru_base_url() -> None:
    with pytest.raises(ValueError, match="Invalid MinerU API base URL"):
        RoutingSettings(mineru_api_base_url="https://attacker.invalid/api/v4")


def test_routing_decision_does_not_expose_mineru_service_address() -> None:
    router = _router(allow_cloud=True)

    decision = router.route(_pdf_signals())

    assert decision.selected_parser_id == "mineru"
    assert "api_base_url" not in decision.parser_options
    assert "mineru_api_base_url" not in decision.parser_options

def test_routing_settings_disable_cloud_by_default(monkeypatch) -> None:
    monkeypatch.delenv("DOCUMENT_PARSER_ALLOW_CLOUD", raising=False)

    settings = RoutingSettings.from_environment()

    assert settings.allow_cloud is False

