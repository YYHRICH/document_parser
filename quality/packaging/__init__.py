"""质量产物 packaging primitives."""

from quality.packaging.writer import verify_package_directory, write_package_directory
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

__all__ = [
    "CANONICAL_NAME", "MANIFEST_NAME", "OPTIMIZED_NAME", "REPORT_NAME",
    "PackageArtifacts", "build_package_artifacts", "read_package_files",
    "verify_package_files", "write_package_directory", "verify_package_directory",
]
