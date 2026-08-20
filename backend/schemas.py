"""Backend API request and response models."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..core.contracts import ParsedDocument, ParserCapability, QualityPackage


class ParseJobResponse(BaseModel):
    parse_id: str
    package_path: str
    document: ParsedDocument
    native_artifact_count: int = Field(ge=0)


class ParseRecordResponse(BaseModel):
    parse_id: str
    package_path: str
    document: ParsedDocument


class QualityPackageResponse(BaseModel):
    parse_id: str
    package_path: str
    quality_package: QualityPackage


class ReparseRequest(BaseModel):
    parser_id: str | None = None
    options: dict[str, object] = Field(default_factory=dict)


class ParserListResponse(BaseModel):
    parsers: list[ParserCapability]


def package_path_text(path: Path) -> str:
    return str(path.resolve())
