from __future__ import annotations

from pathlib import Path

import pytest

from document_parser import (
    DocumentSignals,
    ParseRequest,
    ParserCapability,
    ReparseRecommendation,
)
from document_parser.routing import (
    ANYDOC_ID,
    DOCLING_ID,
    MINERU_ID,
    PASSTHROUGH_ID,
    CapabilityRegistry,
    CloudParserForbiddenError,
    ModelRouter,
    ParserUnavailableError,
    ReparseRejectedError,
    RouteProfile,
    RoutingSettings,
    UnknownParserError,
    UnsupportedFormatError,
)
from document_parser.routing.registry import (
    ANYDOC_FORMATS,
    DOCLING_FORMATS,
    MINERU_FORMATS,
    PASSTHROUGH_FORMATS,
)


def capability_registry(**availability: bool) -> CapabilityRegistry:
    definitions = [
        (DOCLING_ID, DOCLING_FORMATS, False),
        (ANYDOC_ID, ANYDOC_FORMATS, False),
        (MINERU_ID, MINERU_FORMATS, True),
        (PASSTHROUGH_ID, PASSTHROUGH_FORMATS, False),
    ]
    return CapabilityRegistry(
        ParserCapability(
            parser_id=parser_id,
            provider="test",
            display_name=parser_id,
            formats=formats,
            requires_network=requires_network,
            available=availability.get(parser_id, True),
            unavailable_reason=(
                None if availability.get(parser_id, True) else f"{parser_id} unavailable"
            ),
        )
        for parser_id, formats, requires_network in definitions
    )


def router(**availability: bool) -> ModelRouter:
    return ModelRouter(capability_registry(**availability), RoutingSettings())


def signals(extension: str, **updates: object) -> DocumentSignals:
    values: dict[str, object] = {"extension": extension, "size_bytes": 1024}
    values.update(updates)
    return DocumentSignals.model_validate(values)


def test_pdf_always_prefers_mineru_in_default_profile() -> None:
    decision = router().route(signals(".PDF", has_text_layer=True))

    assert decision.selected_parser_id == MINERU_ID
    assert decision.fallback_parser_ids == [DOCLING_ID]
    assert decision.signals.extension == ".pdf"
    assert decision.parser_options["api_mode"] == "precise"
    assert decision.parser_options["download_full_zip"] is True
    assert "MINERU_API_TOKEN" not in decision.model_dump_json()


def test_pdf_falls_back_to_docling_when_cloud_is_forbidden() -> None:
    decision = router().route(signals(".pdf"), allow_cloud=False)

    assert decision.selected_parser_id == DOCLING_ID
    assert decision.fallback_parser_ids == []
    assert "allow_cloud=false" in decision.unavailable_reasons[MINERU_ID]
    assert decision.parser_options["allow_cloud"] is False


@pytest.mark.parametrize("extension", [".bmp", ".jpg", ".jpeg", ".png", ".tiff", ".webp"])
def test_local_first_images_use_docling_rapidocr(extension: str) -> None:
    decision = router().route(signals(extension, language_hint="zh"))

    assert decision.selected_parser_id == DOCLING_ID
    assert decision.parser_options["ocr"] is True
    assert decision.parser_options["ocr_engine"] == "rapidocr"
    assert decision.parser_options["image_export_mode"] == "referenced"
    assert decision.parser_options["output_formats"] == ["md", "json"]


@pytest.mark.parametrize("extension", [".bmp", ".jpg", ".jpeg", ".png", ".webp"])
def test_quality_first_images_use_mineru(extension: str) -> None:
    decision = router().route(signals(extension), profile=RouteProfile.QUALITY_FIRST)

    assert decision.selected_parser_id == MINERU_ID
    assert decision.fallback_parser_ids == [DOCLING_ID]
    assert decision.parser_options["model_version"] == "vlm"


def test_quality_first_tiff_declares_lossless_preprocessing() -> None:
    decision = router().route(signals(".tif"), profile="quality_first")

    assert decision.selected_parser_id == MINERU_ID
    assert decision.parser_options["preprocessors"] == ["lossless_tiff_to_png"]


@pytest.mark.parametrize("extension", [".docx", ".pptx", ".xlsx"])
def test_modern_office_uses_docling_then_anydoc(extension: str) -> None:
    decision = router().route(signals(extension))

    assert decision.selected_parser_id == DOCLING_ID
    assert decision.fallback_parser_ids == [ANYDOC_ID]


def test_quality_first_office_requests_comparison_without_changing_primary() -> None:
    decision = router().route(signals(".docx"), profile="quality_first")

    assert decision.selected_parser_id == DOCLING_ID
    assert decision.parser_options["comparison_parser_ids"] == [ANYDOC_ID]


@pytest.mark.parametrize("extension", [".doc", ".ppt", ".xls"])
def test_legacy_office_without_libreoffice_uses_anydoc(extension: str) -> None:
    decision = router().route(signals(extension), libreoffice_available=False)

    assert decision.selected_parser_id == ANYDOC_ID
    assert decision.fallback_parser_ids == []


def test_legacy_office_with_libreoffice_uses_conversion_then_docling() -> None:
    decision = router().route(signals(".doc"), libreoffice_available=True)

    assert decision.selected_parser_id == DOCLING_ID
    assert decision.fallback_parser_ids == [ANYDOC_ID]
    assert decision.parser_options["preprocessors"] == [
        "libreoffice_to_modern_office"
    ]


@pytest.mark.parametrize("extension", [".md", ".markdown", ".txt"])
def test_native_text_uses_passthrough(extension: str) -> None:
    decision = router().route(signals(extension))

    assert decision.selected_parser_id == PASSTHROUGH_ID
    assert decision.fallback_parser_ids == [DOCLING_ID]
    assert decision.parser_options["normalize_to"] == "utf-8"


def test_csv_preserves_original_and_uses_docling() -> None:
    decision = router().route(signals("csv"))

    assert decision.selected_parser_id == DOCLING_ID
    assert decision.parser_options["preserve_original"] is True


def test_manual_selection_has_no_silent_fallback() -> None:
    decision = router().route(signals(".pdf"), requested_parser_id=DOCLING_ID)

    assert decision.mode.value == "manual"
    assert decision.requested_parser_id == DOCLING_ID
    assert decision.selected_parser_id == DOCLING_ID
    assert decision.allow_automatic_fallback is False
    assert decision.fallback_parser_ids == []


def test_manual_cloud_parser_is_rejected_when_cloud_is_forbidden() -> None:
    with pytest.raises(CloudParserForbiddenError, match="allow_cloud=false"):
        router().route(
            signals(".pdf"), requested_parser_id=MINERU_ID, allow_cloud=False
        )


def test_unknown_manual_parser_is_rejected() -> None:
    with pytest.raises(UnknownParserError, match="未注册解析器"):
        router().route(signals(".pdf"), requested_parser_id="missing")


def test_unsupported_format_does_not_guess() -> None:
    with pytest.raises(UnsupportedFormatError, match="不在已验证路由表"):
        router().route(signals(".unknown"))


def test_all_candidates_unavailable_returns_all_reasons() -> None:
    with pytest.raises(ParserUnavailableError) as raised:
        router(mineru=False, docling=False).route(signals(".pdf"))

    message = str(raised.value)
    assert "mineru unavailable" in message
    assert "docling unavailable" in message


def test_route_request_reads_public_switches_from_options() -> None:
    request = ParseRequest(
        filename="scan.pdf",
        file_type="application/pdf",
        content=b"pdf",
        options={"allow_cloud": False, "route_profile": "quality_first"},
    )

    decision = router().route_request(request)

    assert decision.selected_parser_id == DOCLING_ID
    assert decision.parser_options["route_profile"] == "quality_first"


def test_reparse_recommendation_is_validated_and_merged() -> None:
    recommendation = ReparseRecommendation(
        parser_id=DOCLING_ID,
        reason="云端结果缺少正文",
        parser_options={"ocr": True, "ocr_mode": "full_page"},
    )

    decision = router().route_reparse(signals(".pdf"), recommendation)

    assert decision.selected_parser_id == DOCLING_ID
    assert decision.mode.value == "auto"
    assert decision.parser_options["reparse"] is True
    assert decision.parser_options["ocr_mode"] == "full_page"


def test_reparse_rejects_a_parser_already_attempted() -> None:
    recommendation = ReparseRecommendation(
        parser_id=MINERU_ID,
        reason="再次尝试",
    )

    with pytest.raises(ReparseRejectedError, match="重解析循环"):
        router().route_reparse(
            signals(".pdf"), recommendation, attempted_parser_ids=[MINERU_ID]
        )


def test_registry_reads_explicit_commands_and_token_without_exposing_secret(
    tmp_path: Path,
) -> None:
    docling = tmp_path / "docling.exe"
    anydoc = tmp_path / "anydoc.cmd"
    docling.touch()
    anydoc.touch()
    settings = RoutingSettings(
        docling_executable=str(docling),
        anydoc_executable=str(anydoc),
        mineru_api_token="secret-token",
    )

    registry = CapabilityRegistry.from_settings(settings)

    assert all(item.available for item in registry.list())
    assert "secret-token" not in settings.model_dump_json()
