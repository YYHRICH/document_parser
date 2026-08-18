"""质量产物四件套的确定性序列化、哈希和 manifest 校验。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from document_parser.core.contracts import PackageManifest, QualityPackage

from quality.packaging.hashing import markdown_bytes, sha256_bytes, stable_json_bytes

OPTIMIZED_NAME = "optimized.md"
CANONICAL_NAME = "canonical_document.json"
REPORT_NAME = "quality_report.json"
MANIFEST_NAME = "package_manifest.json"


@dataclass(frozen=True)
class PackageArtifacts:
    """待写入四件套的最终字节和 manifest。"""

    files: Mapping[str, bytes]
    manifest: PackageManifest


def build_package_artifacts(package: QualityPackage) -> PackageArtifacts:
    """按 spec §10.3 顺序生成三个核心文件和 manifest。"""
    optimized = markdown_bytes(package.optimized_markdown)
    canonical = stable_json_bytes(package.canonical_document)
    report = stable_json_bytes(package.quality_report)
    hashes = {
        OPTIMIZED_NAME: sha256_bytes(optimized),
        CANONICAL_NAME: sha256_bytes(canonical),
        REPORT_NAME: sha256_bytes(report),
    }
    if package.package_manifest.artifacts != hashes:
        raise ValueError("QualityPackage manifest 与实际产物哈希不一致")
    manifest = PackageManifest(artifacts=hashes)
    files = {
        OPTIMIZED_NAME: optimized,
        CANONICAL_NAME: canonical,
        REPORT_NAME: report,
        MANIFEST_NAME: stable_json_bytes(manifest),
    }
    return PackageArtifacts(files=files, manifest=manifest)


def verify_package_files(files: Mapping[str, bytes]) -> PackageManifest:
    """校验四件套存在、核心哈希和 manifest 内容；失败时抛出 ValueError。"""
    required = {OPTIMIZED_NAME, CANONICAL_NAME, REPORT_NAME, MANIFEST_NAME}
    missing = required - set(files)
    if missing:
        raise ValueError(f"package 缺少文件: {sorted(missing)}")
    import json
    try:
        payload = json.loads(files[MANIFEST_NAME].decode("utf-8"))
        manifest = PackageManifest.model_validate(payload)
    except Exception as exc:
        raise ValueError("package_manifest.json 无法校验") from exc
    expected = {
        OPTIMIZED_NAME: sha256_bytes(files[OPTIMIZED_NAME]),
        CANONICAL_NAME: sha256_bytes(files[CANONICAL_NAME]),
        REPORT_NAME: sha256_bytes(files[REPORT_NAME]),
    }
    if manifest.artifacts != expected:
        raise ValueError("manifest 哈希与四件套内容不一致")
    return manifest


def read_package_files(directory: Path) -> dict[str, bytes]:
    """读取目录中的四件套并执行完整校验。"""
    try:
        files = {name: (directory / name).read_bytes() for name in (OPTIMIZED_NAME, CANONICAL_NAME, REPORT_NAME, MANIFEST_NAME)}
    except FileNotFoundError as exc:
        raise ValueError(f"package 缺少文件: {exc.filename}") from exc
    verify_package_files(files)
    return files
