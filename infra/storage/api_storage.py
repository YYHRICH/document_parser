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

    def quality_package_path(self, parse_id: str) -> Path:
        return self.package_root(parse_id) / "quality_package.json"

    def optimized_markdown_path(self, parse_id: str) -> Path:
        return self.package_root(parse_id) / "optimized.md"

    def write_quality_package(self, parse_id: str, quality_package: QualityPackage) -> Path:
        package_path = self.quality_package_path(parse_id)
        markdown_path = self.optimized_markdown_path(parse_id)
        package_path.parent.mkdir(parents=True, exist_ok=True)
        # 正文是独立 Markdown 文件；JSON 只保存结构化文档和质量结果，避免重复。
        payload = quality_package.model_dump(
            mode="json", exclude={"optimized_markdown"}
        )
        package_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        markdown_path.write_text(quality_package.optimized_markdown, encoding="utf-8")
        return package_path

    def load_quality_package(self, parse_id: str) -> QualityPackage:
        payload = json.loads(
            self.quality_package_path(parse_id).read_text(encoding="utf-8")
        )
        payload["optimized_markdown"] = self.optimized_markdown_path(
            parse_id
        ).read_text(encoding="utf-8")
        return QualityPackage.model_validate(payload)

    def has_quality_package(self, parse_id: str) -> bool:
        return self.quality_package_path(parse_id).is_file() and self.optimized_markdown_path(
            parse_id
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
    if relative_path == "quality_package.json":
        return "quality_package"
    if relative_path == "optimized.md":
        return "quality_markdown"
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
