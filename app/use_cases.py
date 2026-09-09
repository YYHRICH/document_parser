"""Application use cases shared by HTTP, CLI, and future message triggers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain.model.contracts import ParsedDocument, ParseRequest, QualityPackage
from ..domain.ports import StoragePort
from ..domain.quality.config import QualityConfig
from ..domain.quality.pipeline import run_pipeline
from .orchestration import DocumentParsePipeline


@dataclass(frozen=True)
class ParseApplicationResult:
    parse_id: str
    package_root: Path
    document: ParsedDocument
    quality_package: QualityPackage
    native_files: dict[str, bytes]


class ParseDocumentUseCase:
    def __init__(
        self,
        parser: DocumentParsePipeline,
        storage: StoragePort,
        quality: "RunQualityUseCase | None" = None,
    ) -> None:
        self._parser = parser
        self._storage = storage
        self._quality = quality or RunQualityUseCase()

    def execute(self, request: ParseRequest) -> ParseApplicationResult:
        result = self._parser.parse_for_package(request)
        return self._materialize(
            result=result,
            source_filename=request.filename,
            source_content=request.content,
        )

    def list_parsers(self):
        return self._parser.list_parsers()

    def _materialize(
        self,
        *,
        result: Any,
        source_filename: str,
        source_content: bytes,
    ) -> ParseApplicationResult:
        parse_id = self._storage.new_parse_id()
        package_root = self._storage.write_parse_package(
            parse_id=parse_id,
            document=result.document,
            source_filename=source_filename,
            source_content=source_content,
            native_files=result.native_files,
        )
        quality_package = self._quality.execute(result.document)
        self._storage.write_quality_package(parse_id, quality_package)
        return ParseApplicationResult(
            parse_id=parse_id,
            package_root=package_root,
            document=result.document,
            quality_package=quality_package,
            native_files=result.native_files,
        )


class ReparseDocumentUseCase:
    def __init__(self, parser: DocumentParsePipeline, storage: StoragePort) -> None:
        self._parser = parser
        self._storage = storage

    def execute(self, parse_id: str, parser_id: str | None, options: dict[str, Any]) -> ParseApplicationResult:
        current_package = self._storage.package_root(parse_id)
        source_path = next((current_package / "source").glob("original.*"))
        content = source_path.read_bytes()
        filename = source_path.name.replace("original", "reparse", 1)
        return ParseDocumentUseCase(self._parser, self._storage).execute(
            ParseRequest(
                filename=filename,
                file_type="application/octet-stream",
                content=content,
                parser_id=parser_id,
                options=dict(options),
            )
        )


def run_quality(
    parsed_document: ParsedDocument,
    *,
    config: QualityConfig | None = None,
) -> QualityPackage:
    """应用层质量入口：对 ParsedDocument 执行质量流水线，返回 QualityPackage。"""

    return run_pipeline(parsed_document, config=config)


class RunQualityUseCase:
    def execute(self, document: ParsedDocument) -> QualityPackage:
        return run_quality(document)
