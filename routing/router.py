"""Routing decision engine."""

from __future__ import annotations

from typing import Any, Iterable

from ..core.contracts import (
    DocumentSignals,
    ParseRequest,
    ParserCapability,
    ReparseRecommendation,
    RoutingDecision,
    RoutingMode,
)
from ..core.inspector import SimpleSourceInspector
from .config import RouteProfile, RoutingSettings
from .errors import (
    CloudParserForbiddenError,
    ParserUnavailableError,
    ReparseRejectedError,
    UnsupportedFormatError,
)
from .policy import (
    CSV_FORMATS,
    IMAGE_FORMATS,
    LEGACY_OFFICE_FORMATS,
    TEXT_FORMATS,
    RoutePlan,
    WEB_FORMATS,
    build_route_plan,
    cloud_parser_forbidden_reason,
    resolve_cloud_permission,
)
from .identifiers import ANYDOC_ID, DOCLING_ID, MARKITDOWN_ID, MINERU_ID, OCR_ID
from .registry import CapabilityRegistry


class ModelRouter:
    """Selects a parser and emits a stable ``RoutingDecision``."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        settings: RoutingSettings | None = None,
    ) -> None:
        self.registry = registry
        self.settings = settings or RoutingSettings()
        self._inspector = SimpleSourceInspector()

    @classmethod
    def from_environment(
        cls,
        capabilities: Iterable[ParserCapability] | CapabilityRegistry,
        **overrides: Any,
    ) -> "ModelRouter":
        """Create a router from server settings and an injected capability snapshot.

        The caller that knows concrete parser implementations is responsible for
        collecting their public capabilities.  Routing itself never constructs or
        imports adapters.
        """

        settings = RoutingSettings.from_environment(**overrides)
        registry = (
            capabilities
            if isinstance(capabilities, CapabilityRegistry)
            else CapabilityRegistry.from_snapshot(capabilities)
        )
        return cls(registry, settings)

    def route(
        self,
        signals: DocumentSignals,
        *,
        requested_parser_id: str | None = None,
        profile: RouteProfile | str | None = None,
        allow_cloud: bool | None = None,
        libreoffice_available: bool | None = None,
    ) -> RoutingDecision:
        normalized_signals = signals.model_copy(
            update={"extension": _normalize_extension(signals.extension)}
        )
        selected_profile = RouteProfile(profile or self.settings.profile)
        cloud_allowed = resolve_cloud_permission(
            server_allow_cloud=self.settings.allow_cloud,
            requested_allow_cloud=allow_cloud,
        )
        libreoffice = (
            self.settings.libreoffice_available
            if libreoffice_available is None
            else libreoffice_available
        )

        if requested_parser_id is not None:
            return self._manual_decision(
                normalized_signals,
                requested_parser_id=requested_parser_id,
                profile=selected_profile,
                allow_cloud=cloud_allowed,
                libreoffice_available=libreoffice,
            )

        plan = build_route_plan(
            normalized_signals,
            profile=selected_profile,
            libreoffice_available=libreoffice,
        )
        return self._automatic_decision(
            normalized_signals,
            plan=plan,
            profile=selected_profile,
            allow_cloud=cloud_allowed,
            libreoffice_available=libreoffice,
        )

    def route_request(self, request: ParseRequest) -> RoutingDecision:
        options = request.options
        return self.route(
            self._inspector.inspect(request),
            requested_parser_id=request.parser_id,
            profile=options.get("route_profile"),
            allow_cloud=options.get("allow_cloud"),
            libreoffice_available=options.get("libreoffice_available"),
        )

    def route_reparse(
        self,
        signals: DocumentSignals,
        recommendation: ReparseRecommendation,
        *,
        attempted_parser_ids: Iterable[str] = (),
        profile: RouteProfile | str | None = None,
        allow_cloud: bool | None = None,
        libreoffice_available: bool | None = None,
    ) -> RoutingDecision:
        attempted = set(attempted_parser_ids)
        if recommendation.parser_id in attempted:
            raise ReparseRejectedError(
                f"Parser {recommendation.parser_id} has already been attempted."
            )

        decision = self.route(
            signals,
            requested_parser_id=recommendation.parser_id,
            profile=profile,
            allow_cloud=allow_cloud,
            libreoffice_available=libreoffice_available,
        )
        options = {
            **decision.parser_options,
            **recommendation.parser_options,
            "reparse": True,
        }
        return decision.model_copy(
            update={
                "mode": RoutingMode.AUTO,
                "requested_parser_id": None,
                "reason": f"Reparse recommendation: {recommendation.reason}",
                "parser_options": options,
                "allow_automatic_fallback": False,
            }
        )

    def _automatic_decision(
        self,
        signals: DocumentSignals,
        *,
        plan: RoutePlan,
        profile: RouteProfile,
        allow_cloud: bool,
        libreoffice_available: bool,
    ) -> RoutingDecision:
        available: list[ParserCapability] = []
        unavailable_reasons: dict[str, str] = {}
        for parser_id in plan.candidate_parser_ids:
            if not self.registry.contains(parser_id):
                unavailable_reasons[parser_id] = (
                    "Parser is not present in the injected capability snapshot."
                )
                continue
            capability = self.registry.get(parser_id)
            reason = self._unavailable_reason(
                capability,
                signals.extension,
                allow_cloud=allow_cloud,
            )
            if reason is None:
                available.append(capability)
            else:
                unavailable_reasons[parser_id] = reason

        if not available:
            detail = "; ".join(
                f"{parser_id}: {reason}"
                for parser_id, reason in unavailable_reasons.items()
            )
            raise ParserUnavailableError(
                f"Format {signals.extension} has no executable parser. {detail}"
            )

        selected = available[0]
        fallbacks = [item.parser_id for item in available[1:]]
        reason = plan.reason
        if selected.parser_id != plan.candidate_parser_ids[0]:
            reason += f" First choice unavailable; selected {selected.parser_id}."

        return RoutingDecision(
            mode=RoutingMode.AUTO,
            selected_parser_id=selected.parser_id,
            reason=reason,
            signals=signals,
            parser_options=self._parser_options(
                selected.parser_id,
                signals,
                profile=profile,
                allow_cloud=allow_cloud,
                libreoffice_available=libreoffice_available,
                option_hints=plan.option_hints,
            ),
            fallback_parser_ids=fallbacks,
            allow_automatic_fallback=bool(fallbacks),
            unavailable_reasons=unavailable_reasons,
        )

    def _manual_decision(
        self,
        signals: DocumentSignals,
        *,
        requested_parser_id: str,
        profile: RouteProfile,
        allow_cloud: bool,
        libreoffice_available: bool,
    ) -> RoutingDecision:
        capability = self.registry.get(requested_parser_id)
        cloud_reason = cloud_parser_forbidden_reason(
            capability,
            allow_cloud=allow_cloud,
        )
        if cloud_reason is not None:
            raise CloudParserForbiddenError(f"{cloud_reason} Parser: {requested_parser_id}.")
        if not self._supports_extension(capability, signals.extension, requested_parser_id):
            raise UnsupportedFormatError(
                f"Parser {requested_parser_id} does not support {signals.extension}."
            )
        if not capability.available:
            raise ParserUnavailableError(
                capability.unavailable_reason
                or f"Parser {requested_parser_id} is unavailable in the current environment."
            )

        return RoutingDecision(
            mode=RoutingMode.MANUAL,
            requested_parser_id=requested_parser_id,
            selected_parser_id=requested_parser_id,
            reason=f"User explicitly selected parser {requested_parser_id}.",
            signals=signals,
            parser_options=self._parser_options(
                requested_parser_id,
                signals,
                profile=profile,
                allow_cloud=allow_cloud,
                libreoffice_available=libreoffice_available,
                option_hints={},
            ),
            fallback_parser_ids=[],
            allow_automatic_fallback=False,
        )

    def _unavailable_reason(
        self,
        capability: ParserCapability,
        extension: str,
        *,
        allow_cloud: bool,
    ) -> str | None:
        cloud_reason = cloud_parser_forbidden_reason(capability, allow_cloud=allow_cloud)
        if cloud_reason is not None:
            return cloud_reason
        if not self._supports_extension(capability, extension, capability.parser_id):
            return f"Parser does not support {extension}."
        if not capability.available:
            return capability.unavailable_reason or "Parser is unavailable."
        return None

    def _supports_extension(
        self,
        capability: ParserCapability,
        extension: str,
        parser_id: str,
    ) -> bool:
        if extension in capability.formats:
            return True
        return parser_id == MARKITDOWN_ID and extension in LEGACY_OFFICE_FORMATS

    def _parser_options(
        self,
        parser_id: str,
        signals: DocumentSignals,
        *,
        profile: RouteProfile,
        allow_cloud: bool,
        libreoffice_available: bool,
        option_hints: dict[str, object],
    ) -> dict[str, Any]:
        needs_ocr = _needs_ocr(signals)
        common: dict[str, Any] = {
            "route_profile": profile.value,
            "allow_cloud": allow_cloud,
            "result_layout": {
                "markdown": "document.md",
                "images": "images/",
                "parsed_document": "parsed_document.json",
                "native": f"native/{parser_id}/",
            },
            **option_hints,
        }
        if parser_id == MARKITDOWN_ID:
            return {**common, "preserve_original": True}
        if parser_id == DOCLING_ID:
            return {
                **common,
                "output_formats": ["md", "json"],
                "image_export_mode": "referenced",
                "tables": True,
                "table_mode": "accurate",
                "ocr": needs_ocr,
                "ocr_engine": "rapidocr",
                "ocr_mode": "full_page" if needs_ocr else "default",
                "ocr_languages": _docling_languages(signals.language_hint),
                "libreoffice_available": libreoffice_available,
            }
        if parser_id == MINERU_ID:
            return {
                **common,
                "api_mode": "precise",
                "model_version": "vlm",
                "is_ocr": needs_ocr,
                "enable_table": True,
                "enable_formula": True,
                "language": _mineru_language(signals.language_hint),
                "extra_formats": [],
                "download_full_zip": True,
                "required_native_artifacts": [
                    "full.md",
                    "content_list.json",
                    "middle.json",
                    "model.json",
                    "images/",
                ],
            }
        if parser_id == ANYDOC_ID:
            return {**common, "preserve_original": True}
        if parser_id == OCR_ID:
            return {
                **common,
                "ocr_engine": "rapidocr",
                "ocr_mode": "full_page" if needs_ocr else "default",
            }
        # A plugin may declare a parser ID that this policy does not need to
        # special-case.  It still receives the safe, parser-neutral routing
        # options and can validate its own public options at execution time.
        return common


def _normalize_extension(extension: str) -> str:
    value = extension.strip().lower()
    if not value:
        return ".bin"
    return value if value.startswith(".") else f".{value}"


def _needs_ocr(signals: DocumentSignals) -> bool:
    return (
        signals.extension in IMAGE_FORMATS
        or signals.has_text_layer is False
        or (signals.scanned_page_ratio or 0) > 0
    )


def _docling_languages(language_hint: str | None) -> list[str]:
    if not language_hint:
        return ["chinese", "english"]
    normalized = language_hint.lower()
    if normalized.startswith(("zh", "ch")):
        return ["chinese", "english"]
    return ["english"]


def _mineru_language(language_hint: str | None) -> str:
    if not language_hint:
        return "ch"
    normalized = language_hint.lower()
    if normalized.startswith(("zh", "ch")):
        return "ch"
    if normalized.startswith("en"):
        return "en"
    return "latin"
