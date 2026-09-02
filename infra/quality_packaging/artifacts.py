"""质量层双文件交付的确定性序列化与校验。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from document_parser.domain.model.contracts import QualityPackage

OPTIMIZED_NAME = "optimized.md"
QUALITY_NAME = "quality_package.json"


@dataclass(frozen=True)
class PackageArtifacts:
    """待写入的两个质量产物。"""

    files: Mapping[str, bytes]


def _quality_payload(package: QualityPackage) -> dict:
    """生成不重复正文的 JSON 载荷。"""

    return package.model_dump(mode="json", exclude={"optimized_markdown"})


def build_package_artifacts(package: QualityPackage) -> PackageArtifacts:
    """生成 optimized.md 和 quality_package.json。"""

    optimized = package.optimized_markdown.encode("utf-8")
    quality = json.dumps(
        _quality_payload(package),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    return PackageArtifacts(
        files={OPTIMIZED_NAME: optimized, QUALITY_NAME: quality}
    )


def verify_package_files(files: Mapping[str, bytes]) -> None:
    """校验双文件存在且 JSON 结构合法；不计算或保存哈希。"""

    required = {OPTIMIZED_NAME, QUALITY_NAME}
    missing = required - set(files)
    if missing:
        raise ValueError(f"quality package 缺少文件: {sorted(missing)}")
    try:
        payload = json.loads(files[QUALITY_NAME].decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON 根节点必须是对象")
        if "optimized_markdown" in payload or "package_manifest" in payload:
            raise ValueError("quality_package.json 不应重复正文或包含 manifest")
        QualityPackage.model_validate({**payload, "optimized_markdown": ""})
    except Exception as exc:
        raise ValueError("quality_package.json 无法校验") from exc


def read_package_files(directory: Path) -> dict[str, bytes]:
    """读取双文件并校验 JSON。"""

    try:
        files = {
            name: (directory / name).read_bytes()
            for name in (OPTIMIZED_NAME, QUALITY_NAME)
        }
    except FileNotFoundError as exc:
        raise ValueError(f"quality package 缺少文件: {exc.filename}") from exc
    verify_package_files(files)
    return files
