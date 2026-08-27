import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser import DocumentSignals, ParserCapability  # noqa: E402
from document_parser.routing import ModelRouter  # noqa: E402


def _capabilities() -> list[ParserCapability]:
    return [
        ParserCapability(
            parser_id="mineru",
            provider="fixture",
            display_name="MinerU",
            formats={".pdf", ".png"},
            requires_network=True,
        ),
        ParserCapability(
            parser_id="docling",
            provider="fixture",
            display_name="Docling",
            formats={".pdf", ".md"},
        ),
        ParserCapability(
            parser_id="ocr",
            provider="fixture",
            display_name="OCR",
            formats={".pdf", ".png"},
        ),
        ParserCapability(
            parser_id="microsoft.markitdown",
            provider="fixture",
            display_name="MarkItDown",
            formats={".pdf", ".md", ".txt"},
        ),
        ParserCapability(
            parser_id="anydoc",
            provider="fixture",
            display_name="AnyDoc",
            formats={".docx"},
        ),
    ]


def test_router_prefers_mineru_for_pdf() -> None:
    router = ModelRouter.from_environment(_capabilities(), mineru_api_token="token", allow_cloud=True)
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
    router = ModelRouter.from_environment(_capabilities())
    decision = router.route(
        DocumentSignals(
            extension=".md",
            size_bytes=128,
            has_text_layer=True,
        )
    )

    assert decision.selected_parser_id == "microsoft.markitdown"
    assert decision.parser_options["preserve_original"] is True
