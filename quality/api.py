"""质量层公共入口。

- ``run_quality``：计算 QualityPackage（不落盘，规则测试无需文件系统）；
- ``write_quality_package``：四件套落盘（M5 实现原子化写入）。

计算与 I/O 分离（spec §3.1）。
"""

from __future__ import annotations

from pathlib import Path

from document_parser.core.contracts import ParsedDocument, QualityPackage

from quality.config import QualityConfig
from quality.pipeline import run_pipeline


class QualityPipelineNotImplemented(NotImplementedError):
    """质量流水线功能尚未实现。"""


def run_quality(
    parsed_document: ParsedDocument,
    *,
    config: QualityConfig | None = None,
    llm_advisor: object | None = None,
) -> QualityPackage:
    """对 ParsedDocument 执行质量流水线，返回 QualityPackage。"""
    if llm_advisor is not None:
        raise QualityPipelineNotImplemented("LLM 顾问层将在 MVP-B（M6）实现。")
    return run_pipeline(parsed_document, config=config)


def write_quality_package(
    package: QualityPackage,
    output_dir: Path,
) -> None:
    """将 QualityPackage 四件套落盘到 output_dir（M5 实现原子化写入）。"""
    raise QualityPipelineNotImplemented("四件套落盘将在 M5 实现。")
