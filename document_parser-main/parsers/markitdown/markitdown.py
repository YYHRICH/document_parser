"""Microsoft MarkItDown 解析器实现。

职责边界：本文件只把 MarkItDown 原生支持的文件转换为 Markdown，再生成统一
文档块。`.doc/.ppt` 等旧格式由 ``core.converter`` 在进入解析器前统一标准化，
这里不判断操作系统，也不调用 LibreOffice、Word 或 PowerPoint。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from pathlib import Path

from ...core.contracts import (
    DocumentSignals,
    ParseConfidence,
    ParsedDocument,
    ParseRequest,
    ParserCapability,
    ParserProvenance,
)
from .block_builder import blocks_from_markdown


class MarkItDownParser:
    """将 MarkItDown 原生格式转换为统一 ``ParsedDocument``。"""

    # 解析器 ID 会写入持久化结果，对外应保持稳定。
    PARSER_ID = "microsoft.markitdown"

    # 这里只声明 MarkItDown 直接消费的格式；旧格式由 Gateway 合并到最终能力列表。
    NATIVE_FORMATS = {
        ".pdf",
        ".docx",
        ".pptx",
        ".xlsx",
        ".xls",
        ".html",
        ".htm",
        ".md",
        ".txt",
        ".csv",
        ".json",
        ".xml",
        ".zip",
        ".epub",
    }

    @property
    def capability(self) -> ParserCapability:
        """返回原生能力；查询能力不会初始化重量级转换依赖。"""

        # find_spec 只检查包是否存在，不导入 MarkItDown，降低 API 启动耗时。
        dependency_available = find_spec("markitdown") is not None
        return ParserCapability(
            parser_id=self.PARSER_ID,
            provider="microsoft",
            display_name="Microsoft MarkItDown 解析器",
            formats=self.NATIVE_FORMATS,
            model_versions=["markitdown"],
            default_model_version="markitdown",
            requires_network=False,
            requires_gpu=False,
            available=dependency_available,
            unavailable_reason=(
                None
                if dependency_available
                else "未安装 markitdown[all]；请执行项目安装脚本。"
            ),
        )

    def parse(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParsedDocument:
        """执行转换、切块并补齐统一来源信息。"""

        # 第一层校验：依赖和格式问题应在创建子进程前快速失败。
        if not self.capability.available:
            raise RuntimeError(self.capability.unavailable_reason)
        if signals.extension not in self.NATIVE_FORMATS:
            raise ValueError(f"MarkItDown 不支持原生格式：{signals.extension}")

        # 第二层转换：单独计时，便于与 core 层的旧格式转换耗时区分。
        started = time.perf_counter()
        markdown = _convert_with_markitdown(request.content, signals.extension)
        markitdown_duration_ms = int((time.perf_counter() - started) * 1000)

        # 第三层标准化：无论源格式是什么，下游都获得同一种块结构。
        blocks = blocks_from_markdown(markdown)
        return ParsedDocument(
            filename=request.filename,
            file_type=request.file_type,
            # 完整正文供 Wiki 构建直接使用，blocks 供结构化检索与溯源。
            markdown=markdown,
            blocks=blocks,
            # MarkItDown convert_stream 当前不返回可独立保存的图片二进制。
            assets=[],
            # 该分数只标记是否产出有效内容，不表达调用方的解析质量偏好。
            confidence=ParseConfidence(overall=0.9 if blocks else 0.0),
            provenance=ParserProvenance(
                parser_id=self.PARSER_ID,
                model="markitdown",
                version=_markitdown_version(),
                parameters={
                    "plugins_enabled": False,
                    "source_extension": signals.extension,
                },
                format_conversion_duration_ms=0,
                markitdown_duration_ms=markitdown_duration_ms,
                # 没有前置转换时，总解析耗时就是 MarkItDown 耗时。
                parse_duration_ms=markitdown_duration_ms,
            ),
        )


def _convert_with_markitdown(content: bytes, extension: str) -> str:
    """在受控子进程执行第三方转换器，并返回 UTF-8 Markdown。"""

    # 当前 MarkItDown 依赖在普通后台线程中存在阻塞风险。隔离到子进程后，单个
    # 文件超时或第三方库崩溃只会使当前任务失败，不会锁死 API worker。
    script = r"""
import sys
from pathlib import Path
from markitdown import MarkItDown

source, output, extension = sys.argv[1:4]
with Path(source).open("rb") as stream:
    result = MarkItDown(enable_plugins=False).convert_stream(
        stream,
        file_extension=extension,
    )
Path(output).write_text(result.text_content, encoding="utf-8")
"""

    # 输入、输出和错误日志均放入一次性目录，退出后自动清理。
    with tempfile.TemporaryDirectory(prefix="markitdown-run-") as temporary:
        directory = Path(temporary)
        source = directory / f"source{extension}"
        output = directory / "output.md"
        error_log = directory / "error.log"
        source.write_bytes(content)

        # Windows 隐藏子进程窗口；其他系统 creationflags 必须为 0。
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with error_log.open("w", encoding="utf-8") as errors:
            completed = subprocess.run(
                [sys.executable, "-c", script, str(source), str(output), extension],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=errors,
                timeout=300,
                creationflags=creation_flags,
                check=False,
            )

        # 错误只回传子进程日志，不泄露输入正文或临时文件内容。
        if completed.returncode != 0 or not output.is_file():
            message = error_log.read_text(encoding="utf-8").strip()
            raise RuntimeError(
                f"MarkItDown 转换失败（退出码 {completed.returncode}）：{message}"
            )
        return output.read_text(encoding="utf-8")


def _markitdown_version() -> str:
    """读取安装版本并写入 provenance，方便复现不同版本的解析差异。"""

    try:
        return version("markitdown")
    except PackageNotFoundError:
        return "unknown"
