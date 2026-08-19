"""解析器能力注册表与本机可用性检查。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable

from ..core.contracts import ParserCapability
from .config import RoutingSettings
from .errors import UnknownParserError


DOCLING_ID = "docling"
ANYDOC_ID = "anydoc"
MINERU_ID = "mineru"
PASSTHROUGH_ID = "passthrough"

DOCLING_FORMATS = {
    ".pdf",
    ".bmp",
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".htm",
    ".md",
    ".markdown",
    ".txt",
    ".csv",
    ".adoc",
    ".asciidoc",
    ".eml",
    ".epub",
    # 旧 Office 由统一转换层先转换为新版格式。
    ".doc",
    ".ppt",
    ".xls",
}

ANYDOC_FORMATS = {
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".csv",
}

# TIFF 由 Adapter 无损转 PNG 后提交 MinerU，因此注册表声明的是 Adapter 可接收格式。
MINERU_FORMATS = {
    ".pdf",
    ".bmp",
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}

PASSTHROUGH_FORMATS = {".md", ".markdown", ".txt"}


class CapabilityRegistry:
    """稳定 parser ID 到 ``ParserCapability`` 的映射。"""

    def __init__(self, capabilities: Iterable[ParserCapability]) -> None:
        self._capabilities: dict[str, ParserCapability] = {}
        for capability in capabilities:
            if capability.parser_id in self._capabilities:
                raise ValueError(f"解析器 ID 重复：{capability.parser_id}")
            self._capabilities[capability.parser_id] = capability

    @classmethod
    def from_settings(cls, settings: RoutingSettings) -> "CapabilityRegistry":
        """检查本机命令与 MinerU Token，建立运行时能力表。"""

        docling_path = _find_executable(settings.docling_executable, "docling")
        anydoc_path = _find_executable(settings.anydoc_executable, "anydoc")
        token = settings.mineru_api_token
        mineru_available = bool(token and token.get_secret_value().strip())

        return cls(
            [
                ParserCapability(
                    parser_id=DOCLING_ID,
                    provider="docling-project",
                    display_name="Docling + RapidOCR",
                    formats=DOCLING_FORMATS,
                    model_versions=["standard", "vlm"],
                    default_model_version="standard",
                    requires_network=False,
                    requires_gpu=False,
                    available=docling_path is not None,
                    unavailable_reason=(
                        None
                        if docling_path is not None
                        else "未找到 Docling 命令；请安装依赖或设置 DOCLING_EXECUTABLE。"
                    ),
                ),
                ParserCapability(
                    parser_id=ANYDOC_ID,
                    provider="firecrawl",
                    display_name="AnyDoc",
                    formats=ANYDOC_FORMATS,
                    model_versions=["0.1.6"],
                    default_model_version="0.1.6",
                    requires_network=False,
                    requires_gpu=False,
                    available=anydoc_path is not None,
                    unavailable_reason=(
                        None
                        if anydoc_path is not None
                        else "未找到 AnyDoc 命令；请安装 @firecrawl/anydoc 或设置 ANYDOC_EXECUTABLE。"
                    ),
                ),
                ParserCapability(
                    parser_id=MINERU_ID,
                    provider="mineru",
                    display_name="MinerU 精准解析 API",
                    formats=MINERU_FORMATS,
                    model_versions=["pipeline", "vlm"],
                    default_model_version="vlm",
                    requires_network=True,
                    requires_gpu=False,
                    available=mineru_available,
                    unavailable_reason=(
                        None
                        if mineru_available
                        else "未配置 MINERU_API_TOKEN，MinerU 精准解析 API 不可用。"
                    ),
                ),
                ParserCapability(
                    parser_id=PASSTHROUGH_ID,
                    provider="document_parser",
                    display_name="UTF-8 原文直通",
                    formats=PASSTHROUGH_FORMATS,
                    model_versions=["1.0"],
                    default_model_version="1.0",
                    requires_network=False,
                    requires_gpu=False,
                    available=True,
                ),
            ]
        )

    def get(self, parser_id: str) -> ParserCapability:
        try:
            return self._capabilities[parser_id]
        except KeyError as exc:
            raise UnknownParserError(f"未注册解析器：{parser_id}") from exc

    def list(self) -> list[ParserCapability]:
        return list(self._capabilities.values())

    def contains(self, parser_id: str) -> bool:
        return parser_id in self._capabilities


def _find_executable(configured: str | None, command: str) -> str | None:
    if configured:
        path = Path(configured).expanduser()
        return str(path.resolve()) if path.is_file() else None
    return shutil.which(command) or shutil.which(f"{command}.cmd")
