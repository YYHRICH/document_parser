"""HTTP API routes for the document parser trigger layer."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ...api.dto import (
    ParseJobResponse,
    ParseRecordResponse,
    ParserListResponse,
    QualityPackageResponse,
    ReparseRequest,
    package_path_text,
)
from ...domain.model.contracts import ParseRequest, QualityPackage


def build_router(*, application: object) -> APIRouter:
    router = APIRouter()

    parse_document = getattr(application, "parse_document")
    reparse_document = getattr(application, "reparse_document")
    storage = getattr(application, "storage")

    @router.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/api/parsers", response_model=ParserListResponse)
    def list_parsers() -> ParserListResponse:
        return ParserListResponse(parsers=parse_document.list_parsers())

    @router.post("/api/parses", response_model=ParseJobResponse)
    async def create_parse(
        file: UploadFile = File(),
        parser_id: str | None = Form(default=None),
        options_json: str | None = Form(default=None),
        native_output_dir: str | None = Form(default=None),
    ) -> ParseJobResponse:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        options = _parse_options(options_json)
        if native_output_dir:
            options["native_output_dir"] = native_output_dir
        filename = file.filename or "upload.bin"
        request = ParseRequest(
            filename=filename,
            file_type=file.content_type
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream",
            content=content,
            parser_id=parser_id or None,
            options=options,
        )
        try:
            result = parse_document.execute(request)
        except Exception as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return ParseJobResponse(
            parse_id=result.parse_id,
            package_path=package_path_text(result.package_root),
            document=result.document,
            native_artifact_count=len(result.document.native_artifacts),
        )

    @router.get("/api/parses/{parse_id}", response_model=ParseRecordResponse)
    def get_parse(parse_id: str) -> ParseRecordResponse:
        try:
            package_root = storage.package_root(parse_id)
            document = storage.load_document(parse_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Parse job not found.") from error
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return ParseRecordResponse(
            parse_id=parse_id,
            package_path=package_path_text(package_root),
            document=document,
        )

    @router.get("/api/parses/{parse_id}/quality-package", response_model=QualityPackageResponse)
    def get_quality_package(parse_id: str) -> QualityPackageResponse:
        try:
            package_root = storage.package_root(parse_id)
            quality_package = storage.load_quality_package(parse_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Quality package not found.") from error
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return QualityPackageResponse(
            parse_id=parse_id,
            package_path=package_path_text(package_root),
            quality_package=quality_package,
        )

    @router.post("/api/parses/{parse_id}/quality-package", response_model=QualityPackageResponse)
    def set_quality_package(parse_id: str, body: QualityPackage) -> QualityPackageResponse:
        try:
            package_root = storage.package_root(parse_id)
            document = storage.load_document(parse_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Parse job not found.") from error
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if body.document_id != document.document_id:
            raise HTTPException(
                status_code=400,
                detail="Quality package document_id does not match the stored parse.",
            )
        storage.write_quality_package(parse_id, body)
        return QualityPackageResponse(
            parse_id=parse_id,
            package_path=package_path_text(package_root),
            quality_package=storage.load_quality_package(parse_id),
        )

    @router.get("/api/parses/{parse_id}/artifacts")
    def list_artifacts(parse_id: str) -> dict[str, object]:
        try:
            files = storage.list_package_files(parse_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Parse job not found.") from error
        return {"parse_id": parse_id, "files": files}

    @router.get("/api/parses/{parse_id}/download")
    def download_package(parse_id: str) -> FileResponse:
        package_root = storage.package_root(parse_id)
        if not package_root.is_dir():
            raise HTTPException(status_code=404, detail="Parse job not found.")
        archive_path = storage.create_package_archive(parse_id)
        return FileResponse(
            archive_path,
            media_type="application/zip",
            filename=f"document-package-{parse_id}.zip",
            background=BackgroundTask(_remove_temp_file, archive_path),
        )

    @router.get("/api/parses/{parse_id}/artifacts/{artifact_path:path}")
    def get_artifact(parse_id: str, artifact_path: str) -> FileResponse:
        try:
            path = storage.resolve_package_file(parse_id, artifact_path)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Artifact not found.") from error
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return FileResponse(path, media_type=storage.content_type_for(path))

    @router.post("/api/parses/{parse_id}/reparse", response_model=ParseJobResponse)
    def reparse(parse_id: str, body: ReparseRequest) -> ParseJobResponse:
        try:
            result = reparse_document.execute(parse_id, body.parser_id, body.options)
        except Exception as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return ParseJobResponse(
            parse_id=result.parse_id,
            package_path=package_path_text(result.package_root),
            document=result.document,
            native_artifact_count=len(result.document.native_artifacts),
        )

    return router


def _remove_temp_file(path: Path) -> None:
    path.unlink(missing_ok=True)


def _parse_options(options_json: str | None) -> dict[str, object]:
    if not options_json:
        return {}
    try:
        value = __import__("json").loads(options_json)
    except Exception as error:
        raise HTTPException(status_code=400, detail="options_json must be valid JSON.") from error
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="options_json must be a JSON object.")
    return value
