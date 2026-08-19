"""自动、手动和重新解析路由实现。"""

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
from .policy import IMAGE_FORMATS, RoutePlan, build_route_plan
from .registry import (
    ANYDOC_ID,
    DOCLING_ID,
    MINERU_ID,
    PASSTHROUGH_ID,
    CapabilityRegistry,
)


class ModelRouter:
    """只负责选择模型并输出稳定 ``RoutingDecision``，不执行解析。"""

    def __init__(
        self,
        registry: CapabilityRegistry,
        settings: RoutingSettings | None = None,
    ) -> None:
        self.registry = registry
        self.settings = settings or RoutingSettings()
        self._inspector = SimpleSourceInspector()

    @classmethod
    def from_environment(cls, **overrides: Any) -> "ModelRouter":
        settings = RoutingSettings.from_environment(**overrides)
        return cls(CapabilityRegistry.from_settings(settings), settings)

    def route(
        self,
        signals: DocumentSignals,
        *,
        requested_parser_id: str | None = None,
        profile: RouteProfile | str | None = None,
        allow_cloud: bool | None = None,
        libreoffice_available: bool | None = None,
    ) -> RoutingDecision:
        """为固定信号生成自动或手动路由。"""

        normalized_signals = signals.model_copy(
            update={"extension": _normalize_extension(signals.extension)}
        )
        selected_profile = RouteProfile(profile or self.settings.profile)
        cloud_allowed = self.settings.allow_cloud if allow_cloud is None else allow_cloud
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
        """读取 ``ParseRequest.options`` 中的公开开关并生成决策。"""

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
        """校验质量层建议，避免无效重解析和模型循环。"""

        attempted = set(attempted_parser_ids)
        if recommendation.parser_id in attempted:
            raise ReparseRejectedError(
                f"解析器 {recommendation.parser_id} 已尝试过，拒绝形成重解析循环。"
            )

        base = self.route(
            signals,
            requested_parser_id=recommendation.parser_id,
            profile=profile,
            allow_cloud=allow_cloud,
            libreoffice_available=libreoffice_available,
        )
        options = {
            **base.parser_options,
            **recommendation.parser_options,
            "reparse": True,
        }
        return base.model_copy(
            update={
                "mode": RoutingMode.AUTO,
                "requested_parser_id": None,
                "reason": f"质量层建议重新解析：{recommendation.reason}",
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
            capability = self.registry.get(parser_id)
            reason = self._unavailable_reason(
                capability, signals.extension, allow_cloud=allow_cloud
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
                f"格式 {signals.extension} 没有可执行解析器。{detail}"
            )

        selected = available[0]
        fallbacks = [item.parser_id for item in available[1:]]
        reason = plan.reason
        if selected.parser_id != plan.candidate_parser_ids[0]:
            reason += f" 首选不可用，本次实际选择 {selected.parser_id}。"

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
        if capability.requires_network and not allow_cloud:
            raise CloudParserForbiddenError(
                f"任务 allow_cloud=false，禁止使用云端解析器 {requested_parser_id}。"
            )
        if signals.extension not in capability.formats:
            raise UnsupportedFormatError(
                f"解析器 {requested_parser_id} 不支持格式 {signals.extension}。"
            )
        if not capability.available:
            raise ParserUnavailableError(
                capability.unavailable_reason
                or f"解析器 {requested_parser_id} 在当前环境不可用。"
            )

        return RoutingDecision(
            mode=RoutingMode.MANUAL,
            requested_parser_id=requested_parser_id,
            selected_parser_id=requested_parser_id,
            reason=f"用户明确指定解析器 {requested_parser_id}。",
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

    @staticmethod
    def _unavailable_reason(
        capability: ParserCapability,
        extension: str,
        *,
        allow_cloud: bool,
    ) -> str | None:
        if capability.requires_network and not allow_cloud:
            return "任务配置 allow_cloud=false，禁止上传到云端。"
        if extension not in capability.formats:
            return f"解析器不支持格式 {extension}。"
        if not capability.available:
            return capability.unavailable_reason or "解析器在当前环境不可用。"
        return None

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
        parser_hints = dict(option_hints)
        if parser_id != MINERU_ID and parser_hints.get("preprocessors") == [
            "lossless_tiff_to_png"
        ]:
            parser_hints.pop("preprocessors")

        common: dict[str, Any] = {
            "route_profile": profile.value,
            "allow_cloud": allow_cloud,
            "result_layout": {
                "markdown": "document.md",
                "images": "images/",
                "parsed_document": "parsed_document.json",
                "native": f"native/{parser_id}/",
            },
            **parser_hints,
        }
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
                "api_base_url": self.settings.mineru_api_base_url,
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
            return {
                **common,
                "output_format": "md",
                "preserve_original": True,
            }
        if parser_id == PASSTHROUGH_ID:
            return {
                **common,
                "encoding_candidates": ["utf-8-sig", "utf-8", "gb18030", "gbk"],
                "normalize_to": "utf-8",
                "preserve_original": True,
            }
        raise AssertionError(f"没有为解析器 {parser_id} 定义参数模板。")


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
