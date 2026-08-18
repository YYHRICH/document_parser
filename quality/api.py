"""质量层公共入口。

- ``run_quality_repair``：Agno 单文档 Agent 正式入口；
- ``run_quality``：显式确定性维护/测试入口；
- ``write_quality_package``：质量产物四件套落盘。

计算与 I/O 分离（spec §3.1）。
"""

from __future__ import annotations

from pathlib import Path

from document_parser.core.contracts import ParsedDocument, QualityPackage

from quality.agent.runtime import (
    RepairAgent,
    RepairAgentConfig,
    RepairAgentFactory,
    run_repair,
)
from quality.config import QualityConfig
from quality.packaging.writer import write_package_directory
from quality.pipeline import run_pipeline


def run_quality(
    parsed_document: ParsedDocument,
    *,
    config: QualityConfig | None = None,
) -> QualityPackage:
    """显式运行确定性维护/测试路径，不代表生产 Agent 修复成功。"""

    return run_pipeline(parsed_document, config=config)


def run_quality_repair(
    parsed_document: ParsedDocument,
    *,
    agent: RepairAgent | None = None,
    agent_factory: RepairAgentFactory | None = None,
    config: QualityConfig | None = None,
    agent_config: RepairAgentConfig | None = None,
) -> QualityPackage:
    """执行正式单文档 Agent 修复。

    生产调用应传 agent_factory，由入口把本次文档的唯一 toolbox
    注入 Agent；直接传 agent 主要用于测试或已完成绑定的适配器。
    两者都未提供时拒绝静默降级到确定性路径。
    """

    return run_repair(
        parsed_document,
        agent=agent,
        agent_factory=agent_factory,
        config=config,
        agent_config=agent_config,
    ).package


def write_quality_package(
    package: QualityPackage,
    output_dir: Path,
    *,
    replace_existing: bool = False,
) -> Path:
    """将 QualityPackage 四件套原子落盘并返回最终目录。"""
    return write_package_directory(
        package,
        Path(output_dir),
        replace_existing=replace_existing,
    )
