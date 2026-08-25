"""M5 打包落盘（infra 层）：将 QualityPackage 四件套安全写入目录并校验。"""

from __future__ import annotations

from pathlib import Path

from document_parser.domain.model.contracts import QualityPackage

from .writer import verify_package_directory, write_package_directory
from .artifacts import (
    CANONICAL_NAME,
    MANIFEST_NAME,
    OPTIMIZED_NAME,
    REPORT_NAME,
    PackageArtifacts,
    build_package_artifacts,
    read_package_files,
    verify_package_files,
)


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


__all__ = [
    "CANONICAL_NAME", "MANIFEST_NAME", "OPTIMIZED_NAME", "REPORT_NAME",
    "PackageArtifacts", "build_package_artifacts", "read_package_files",
    "verify_package_files", "write_package_directory", "verify_package_directory",
    "write_quality_package",
]
