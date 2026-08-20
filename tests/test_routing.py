import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser import DocumentSignals  # noqa: E402
from document_parser.routing import ModelRouter  # noqa: E402


def test_router_prefers_mineru_for_pdf() -> None:
    router = ModelRouter.from_environment(mineru_api_token="token")
    decision = router.route(
        DocumentSignals(
            extension=".pdf",
            size_bytes=1024,
            has_text_layer=True,
            language_hint="zh",
        )
    )

    assert decision.selected_parser_id == "mineru"
    assert decision.parser_options["api_mode"] == "precise"
    assert decision.parser_options["language"] == "ch"


def test_router_uses_markitdown_for_plain_text() -> None:
    router = ModelRouter.from_environment()
    decision = router.route(
        DocumentSignals(
            extension=".md",
            size_bytes=128,
            has_text_layer=True,
        )
    )

    assert decision.selected_parser_id == "microsoft.markitdown"
    assert decision.parser_options["preserve_original"] is True
