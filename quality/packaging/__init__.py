"""Packaging primitives with lazy filesystem adapters.

Pure serialization and hash helpers may be imported by the quality pipeline.
Directory reads and writes stay behind explicit functions so an in-memory run
does not load a filesystem adapter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from quality.packaging.artifacts import (
    CANONICAL_NAME,
    MANIFEST_NAME,
    OPTIMIZED_NAME,
    REPORT_NAME,
    PackageArtifacts,
    build_package_artifacts,
    read_package_files,
    verify_package_files,
)

if TYPE_CHECKING:
    from pathlib import Path

    from quality.contracts import QualityPackage


def write_package_directory(
    package: "QualityPackage",
    output_dir: "Path | str",
    *,
    replace_existing: bool = False,
) -> "Path":
    """Lazily load the filesystem writer for an explicit artifact write."""

    from pathlib import Path

    from quality.packaging.writer import write_package_directory as _write

    return _write(package, Path(output_dir), replace_existing=replace_existing)


def verify_package_directory(directory: "Path | str") -> None:
    """Lazily load the filesystem verifier for an explicit artifact read."""

    from pathlib import Path

    from quality.packaging.writer import verify_package_directory as _verify

    _verify(Path(directory))


__all__ = [
    "CANONICAL_NAME",
    "MANIFEST_NAME",
    "OPTIMIZED_NAME",
    "REPORT_NAME",
    "PackageArtifacts",
    "build_package_artifacts",
    "read_package_files",
    "verify_package_files",
    "write_package_directory",
    "verify_package_directory",
]
