import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser import DocumentSignals  # noqa: E402
from document_parser.app.bootstrap import build_router  # noqa: E402
from document_parser.domain.routing.config import RouteProfile  # noqa: E402
from document_parser.domain.routing.policy import build_route_plan  # noqa: E402


def test_router_prefers_mineru_for_pdf() -> None:
    router = build_router(mineru_api_token="token")
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


def test_router_skips_mineru_for_pdf_without_cloud_token(monkeypatch) -> None:
    monkeypatch.delenv("MINERU_API_TOKEN", raising=False)
    monkeypatch.setattr(
        "document_parser.infra.parsers.mineru.mineru.find_spec", lambda _name: None
    )
    monkeypatch.setattr(
        "document_parser.infra.parsers.mineru.mineru.shutil.which", lambda _name: None
    )
    router = build_router(mineru_api_token=None)
    decision = router.route(
        DocumentSignals(
            extension=".pdf",
            size_bytes=1024,
            has_text_layer=True,
            language_hint="zh",
        )
    )

    assert decision.selected_parser_id == "docling"
    assert "mineru" in decision.unavailable_reasons


def test_router_uses_installed_local_mineru_without_cloud_token(monkeypatch) -> None:
    monkeypatch.delenv("MINERU_API_TOKEN", raising=False)
    monkeypatch.setattr(
        "document_parser.infra.parsers.mineru.mineru.find_spec",
        lambda name: object() if name == "mineru" else None,
    )
    router = build_router(mineru_api_token=None)

    decision = router.route(
        DocumentSignals(
            extension=".pdf",
            size_bytes=1024,
            has_text_layer=True,
            language_hint="zh",
        )
    )

    assert decision.selected_parser_id == "mineru"
    assert decision.parser_options["api_mode"] == "local"
    assert decision.parser_options["mineru_force_local"] is True


def test_router_uses_markitdown_for_plain_text() -> None:
    router = build_router()
    decision = router.route(
        DocumentSignals(
            extension=".md",
            size_bytes=128,
            has_text_layer=True,
        )
    )

    assert decision.selected_parser_id == "microsoft.markitdown"
    assert decision.parser_options["preserve_original"] is True


def test_route_plan_prefers_anydoc_for_excel_regardless_of_libreoffice() -> None:
    for extension in (".xls", ".xlsx"):
        for libreoffice_available in (False, True):
            plan = build_route_plan(
                DocumentSignals(extension=extension, size_bytes=128),
                profile=RouteProfile.LOCAL_FIRST,
                libreoffice_available=libreoffice_available,
            )

            assert plan.candidate_parser_ids == ["anydoc", "microsoft.markitdown"]
