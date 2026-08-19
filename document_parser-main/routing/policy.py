"""基于已完成实测的后缀路由策略。"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.contracts import DocumentSignals
from .config import RouteProfile
from .errors import UnsupportedFormatError
from .registry import ANYDOC_ID, DOCLING_ID, MINERU_ID, PASSTHROUGH_ID


IMAGE_FORMATS = {".bmp", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
MODERN_OFFICE_FORMATS = {".docx", ".pptx", ".xlsx"}
LEGACY_OFFICE_FORMATS = {".doc", ".ppt", ".xls"}
DOCLING_TEXT_FORMATS = {".html", ".htm", ".adoc", ".asciidoc", ".eml", ".epub"}
PASSTHROUGH_FORMATS = {".md", ".markdown", ".txt"}


@dataclass(frozen=True)
class RoutePlan:
    """策略产生的有序候选和 Adapter 参数提示。"""

    candidate_parser_ids: tuple[str, ...]
    reason: str
    option_hints: dict[str, object] = field(default_factory=dict)


def build_route_plan(
    signals: DocumentSignals,
    *,
    profile: RouteProfile,
    libreoffice_available: bool,
) -> RoutePlan:
    """按后缀生成策略计划；解析器可用性由 Router 再过滤。"""

    extension = signals.extension
    if extension == ".pdf":
        return RoutePlan(
            (MINERU_ID, DOCLING_ID),
            "PDF 按当前 MVP 决策固定优先 MinerU，云端不可用或被禁用时回退 Docling。",
        )

    if extension in IMAGE_FORMATS:
        if profile == RouteProfile.QUALITY_FIRST:
            hints: dict[str, object] = {}
            if extension in {".tif", ".tiff"}:
                hints["preprocessors"] = ["lossless_tiff_to_png"]
            return RoutePlan(
                (MINERU_ID, DOCLING_ID),
                "质量优先模式下图片优先 MinerU，失败或禁止云端时回退 Docling。",
                hints,
            )
        return RoutePlan(
            (DOCLING_ID,),
            "本地优先模式下图片使用本地 Docling + RapidOCR。",
        )

    if extension in MODERN_OFFICE_FORMATS:
        hints = (
            {"comparison_parser_ids": [ANYDOC_ID]}
            if profile == RouteProfile.QUALITY_FIRST
            else {}
        )
        return RoutePlan(
            (DOCLING_ID, ANYDOC_ID),
            "现代 Office 使用 Docling 主解析，AnyDoc 作为回退。",
            hints,
        )

    if extension in LEGACY_OFFICE_FORMATS:
        if libreoffice_available:
            return RoutePlan(
                (DOCLING_ID, ANYDOC_ID),
                "检测到 LibreOffice，旧 Office 先转新版交给 Docling，失败后回退 AnyDoc。",
                {"preprocessors": ["libreoffice_to_modern_office"]},
            )
        return RoutePlan(
            (ANYDOC_ID,),
            "未启用 LibreOffice，旧 Office 使用已实测可直读的 AnyDoc。",
        )

    if extension in DOCLING_TEXT_FORMATS:
        return RoutePlan(
            (DOCLING_ID,),
            "该格式按本地实测结果使用 Docling。",
        )

    if extension in PASSTHROUGH_FORMATS:
        return RoutePlan(
            (PASSTHROUGH_ID, DOCLING_ID),
            "原生文本优先做 UTF-8 直通，避免无意义重解析。",
        )

    if extension == ".csv":
        hints = {"preserve_original": True}
        if profile == RouteProfile.QUALITY_FIRST:
            hints["comparison_parser_ids"] = [ANYDOC_ID]
        return RoutePlan(
            (DOCLING_ID, ANYDOC_ID),
            "CSV 保留原文件并由 Docling 生成检索文本，AnyDoc 作为回退。",
            hints,
        )

    raise UnsupportedFormatError(
        f"格式 {extension} 不在已验证路由表中，不自动尝试未知解析器。"
    )
