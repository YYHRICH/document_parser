"""Routing plans."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..model.contracts import DocumentSignals
from .config import RouteProfile
from .ids import ANYDOC_ID, DOCLING_ID, MARKITDOWN_ID, MINERU_ID, OCR_ID


IMAGE_FORMATS = {".bmp", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
OFFICE_FORMATS = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
EXCEL_FORMATS = {".xls", ".xlsx"}
TEXT_FORMATS = {".md", ".markdown", ".txt"}
CSV_FORMATS = {".csv"}
WEB_FORMATS = {".html", ".htm", ".adoc", ".asciidoc", ".eml", ".epub"}
LEGACY_OFFICE_FORMATS = {".doc", ".ppt", ".xls"}


@dataclass(frozen=True)
class RoutePlan:
    candidate_parser_ids: list[str]
    reason: str
    option_hints: dict[str, object] = field(default_factory=dict)


def build_route_plan(
    signals: DocumentSignals,
    *,
    profile: RouteProfile,
    libreoffice_available: bool,
) -> RoutePlan:
    ext = signals.extension.lower()
    if ext in TEXT_FORMATS:
        return RoutePlan([MARKITDOWN_ID], "Markdown / TXT 直接走原文直通。")
    if ext in CSV_FORMATS:
        return RoutePlan(
            [MARKITDOWN_ID, DOCLING_ID, ANYDOC_ID],
            "CSV 保留原文并优先生成检索文本。",
        )
    if ext in EXCEL_FORMATS:
        return RoutePlan(
            [ANYDOC_ID, MARKITDOWN_ID],
            "Excel 表格优先走 AnyDoc 结构通道，MarkItDown 作为正文回退。",
        )
    if ext in LEGACY_OFFICE_FORMATS:
        if libreoffice_available:
            return RoutePlan(
                [MARKITDOWN_ID, ANYDOC_ID, DOCLING_ID],
                "旧 Office 先转新版并优先走 MarkItDown，AnyDoc 作为回退。",
            )
        return RoutePlan([ANYDOC_ID, MARKITDOWN_ID], "未启用 LibreOffice，旧 Office 先走 AnyDoc。")
    if ext in OFFICE_FORMATS:
        return RoutePlan(
            [DOCLING_ID, ANYDOC_ID, MARKITDOWN_ID],
            "现代 Office 优先 Docling，AnyDoc 作为回退。",
        )
    if ext in WEB_FORMATS:
        return RoutePlan([DOCLING_ID, MARKITDOWN_ID], "网页与出版格式优先 Docling。")
    if ext == ".pdf":
        return RoutePlan(
            [MINERU_ID, DOCLING_ID, OCR_ID, MARKITDOWN_ID],
            "PDF 固定 MinerU 优先，再回退 Docling。",
        )
    if ext in IMAGE_FORMATS:
        if profile == RouteProfile.QUALITY_FIRST:
            return RoutePlan(
                [MINERU_ID, DOCLING_ID, OCR_ID],
                "质量优先图片先 MinerU，再回退 Docling。",
            )
        return RoutePlan(
            [DOCLING_ID, OCR_ID, MINERU_ID],
            "本地优先图片先 Docling，再回退 OCR。",
        )
    return RoutePlan([MARKITDOWN_ID], f"未识别格式 {ext}，先回退 MarkItDown。")
