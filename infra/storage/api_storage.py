"""Filesystem storage adapter for document packages."""

from __future__ import annotations

import json
import mimetypes
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import uuid4

from ..packaging.document_package import load_document_package, write_document_package
from ...domain.model.contracts import ParsedDocument, QualityPackage
from ...domain.quality.table_storage import TABLE_INDEX_NAME
from ..quality_packaging.artifacts import (
    ISSUES_NAME,
    OPTIMIZED_NAME,
    STRUCTURE_NAME,
    build_issues_payload,
    build_structure_payload,
)
from ..quality_packaging.table_index import verify_table_index, write_table_index


class ApiStorage:
    def __init__(self, root: Path | str = Path("outputs/api")) -> None:
        self.root = Path(root)

    def new_parse_id(self) -> str:
        return uuid4().hex

    def package_root(self, parse_id: str) -> Path:
        if not parse_id or any(character in parse_id for character in "/\\:"):
            raise ValueError("Invalid parse_id.")
        return self.root / parse_id

    def write_parse_package(
        self,
        *,
        parse_id: str,
        document: ParsedDocument,
        source_filename: str,
        source_content: bytes,
        native_files: dict[str, bytes],
    ) -> Path:
        package_root = self.package_root(parse_id)
        write_document_package(document, package_root, native_files=native_files)
        suffix = Path(source_filename).suffix or ".bin"
        source_path = package_root / "source" / f"original{suffix}"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(source_content)
        return package_root

    def list_package_files(self, parse_id: str) -> list[dict[str, object]]:
        package_root = self.package_root(parse_id)
        if not package_root.is_dir():
            raise FileNotFoundError(parse_id)
        return [
            {
                "path": path.relative_to(package_root).as_posix(),
                "size_bytes": path.stat().st_size,
                "file_type": self.content_type_for(path),
                "category": _package_file_category(path.relative_to(package_root).as_posix()),
            }
            for path in sorted(item for item in package_root.rglob("*") if item.is_file())
        ]

    def structure_path(self, parse_id: str) -> Path:
        return self.package_root(parse_id) / STRUCTURE_NAME

    def quality_issues_path(self, parse_id: str) -> Path:
        return self.package_root(parse_id) / ISSUES_NAME

    def optimized_markdown_path(self, parse_id: str) -> Path:
        return self.package_root(parse_id) / OPTIMIZED_NAME

    def write_quality_package(self, parse_id: str, quality_package: QualityPackage) -> Path:
        structure_path = self.structure_path(parse_id)
        issues_path = self.quality_issues_path(parse_id)
        markdown_path = self.optimized_markdown_path(parse_id)
        structure_path.parent.mkdir(parents=True, exist_ok=True)
        table_index = write_table_index(
            quality_package,
            structure_path.parent / TABLE_INDEX_NAME,
        )
        structure_payload = build_structure_payload(
            quality_package,
            table_index=table_index,
        )
        issues_payload = build_issues_payload(quality_package)
        structure_path.write_text(
            json.dumps(structure_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        issues_path.write_text(
            json.dumps(issues_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        markdown_path.write_text(quality_package.optimized_markdown, encoding="utf-8")
        return structure_path

    def load_quality_package(self, parse_id: str) -> QualityPackage:
        structure = json.loads(self.structure_path(parse_id).read_text(encoding="utf-8"))
        issues = json.loads(self.quality_issues_path(parse_id).read_text(encoding="utf-8"))
        if structure.get("table_index"):
            verify_table_index(
                self.package_root(parse_id) / TABLE_INDEX_NAME,
                str(structure["document_id"]),
            )
        payload = {
            "schema_name": "QualityPackage",
            "document_id": structure["document_id"],
            "canonical_document": structure["canonical_document"],
            "quality_report": issues["quality_report"],
        }
        payload["optimized_markdown"] = self.optimized_markdown_path(
            parse_id
        ).read_text(encoding="utf-8")
        return QualityPackage.model_validate(payload)

    def has_quality_package(self, parse_id: str) -> bool:
        base_files_exist = all(
            path.is_file()
            for path in (
                self.structure_path(parse_id),
                self.quality_issues_path(parse_id),
                self.optimized_markdown_path(parse_id),
            )
        )
        if not base_files_exist:
            return False
        try:
            structure = json.loads(
                self.structure_path(parse_id).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return False
        return not structure.get("table_index") or (
            self.package_root(parse_id) / TABLE_INDEX_NAME
        ).is_file()

    def load_document(self, parse_id: str) -> ParsedDocument:
        return load_document_package(self.package_root(parse_id))

    def create_package_archive(self, parse_id: str) -> Path:
        package_root = self.package_root(parse_id)
        archive_fd, archive_name = tempfile.mkstemp(
            prefix=f"document-package-{parse_id}-", suffix=".zip"
        )
        os.close(archive_fd)
        archive_path = Path(archive_name)
        try:
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for file_path in package_root.rglob("*"):
                    if file_path.is_file():
                        archive.write(file_path, file_path.relative_to(package_root).as_posix())
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise
        return archive_path

    def resolve_package_file(self, parse_id: str, relative_path: str) -> Path:
        safe_path = _validate_relative_path(relative_path)
        package_root = self.package_root(parse_id).resolve()
        target = (package_root / safe_path).resolve()
        if package_root != target and package_root not in target.parents:
            raise ValueError("Artifact path escapes the parse package.")
        if not target.is_file():
            raise FileNotFoundError(relative_path)
        return target

    def content_type_for(self, path: Path) -> str:
        return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _package_file_category(relative_path: str) -> str:
    if relative_path.startswith("native/"):
        return "parser_output"
    if relative_path.startswith("source/"):
        return "source"
    if relative_path.startswith("assets/"):
        return "asset"
    if relative_path == "parsed_document.json":
        return "parsed_document"
    if relative_path == "structure.json":
        return "document_structure"
    if relative_path == "quality_issues.json":
        return "quality_issues"
    if relative_path == "optimized.md":
        return "quality_markdown"
    if relative_path == TABLE_INDEX_NAME:
        return "table_index"
    return "other"


def _validate_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or bool(windows_path.drive)
        or ".." in path.parts
        or normalized.endswith("/")
    ):
        raise ValueError("Artifact path must be a safe relative path.")
    return str(path)
