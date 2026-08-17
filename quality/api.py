"""质量层公共入口。

- ``run_quality``：计算 QualityPackage（不落盘，规则测试无需文件系统）；
- ``write_quality_package``：四件套落盘（计算与 I/O 分离，spec §3.1）。

M0 阶段：入口签名冻结；完整流水线在 M1+ 实现。
"""

from __future__ import annotations

from pathlib import Path

from document_parser.core.contracts import ParsedDocument, QualityPackage

from quality.config import QualityConfig


class QualityPipelineNotImplemented(NotImplementedError):
    """质量流水线尚未实现（M0 骨架阶段）。"""


def run_quality(
    parsed_document: ParsedDocument,
    *,
    config: QualityConfig | None = None,
    llm_advisor: object | None = None,
) -> QualityPackage:
    """对 ParsedDocument 执行质量流水线，返回 QualityPackage。"""
    raise QualityPipelineNotImplemented(
        "质量流水线将在 M1 实现：EvidenceContext -> 规则 -> 修复 -> Gate -> 打包。"
    )


def write_quality_package(
    package: QualityPackage,
    output_dir: Path,
) -> None:
    """将 QualityPackage 四件套落盘到 output_dir（M5 实现原子化写入）。"""
    raise QualityPipelineNotImplemented("四件套落盘将在 M5 实现。")
