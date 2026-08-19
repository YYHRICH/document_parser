"""FastAPI backend for parser integration."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..core.gateway import DocumentParserGateway
from ..core.contracts import ParseRequest
from ..core.contracts import QualityPackage
from .schemas import (
    ParseJobResponse,
    ParseRecordResponse,
    ParserListResponse,
    QualityPackageResponse,
    ReparseRequest,
    package_path_text,
)
from .storage import ApiStorage


def create_app(
    *,
    storage_root: Path | str = Path("outputs/api"),
    gateway: DocumentParserGateway | None = None,
) -> FastAPI:
    app = FastAPI(title="Document Parser API", version="0.1.0")
    parser_gateway = gateway or DocumentParserGateway.from_environment()
    storage = ApiStorage(storage_root)
    frontend_root = Path(__file__).resolve().parents[1] / "frontend"
    if frontend_root.exists():
        app.mount("/static", StaticFiles(directory=frontend_root), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        index_path = frontend_root / "index.html"
        if index_path.is_file():
            return HTMLResponse(index_path.read_text(encoding="utf-8"))
        return HTMLResponse("<!doctype html><html><body><p>Frontend not built.</p></body></html>")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/parsers", response_model=ParserListResponse)
    def list_parsers() -> ParserListResponse:
        return ParserListResponse(parsers=parser_gateway.list_parsers())

    @app.post("/api/parses", response_model=ParseJobResponse)
    async def create_parse(
        file: Annotated[UploadFile, File()],
        parser_id: Annotated[str | None, Form()] = None,
        options_json: Annotated[str | None, Form()] = None,
        native_output_dir: Annotated[str | None, Form()] = None,
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
            result = parser_gateway.parse_for_package(request)
            parse_id = storage.new_parse_id()
            package_root = storage.write_parse_package(
                parse_id=parse_id,
                document=result.document,
                source_filename=filename,
                source_content=content,
                native_files=result.native_files,
            )
        except Exception as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return ParseJobResponse(
            parse_id=parse_id,
            package_path=package_path_text(package_root),
            document=result.document,
            native_artifact_count=len(result.document.native_artifacts),
        )

    @app.get("/api/parses/{parse_id}", response_model=ParseRecordResponse)
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

    @app.get("/api/parses/{parse_id}/quality-package", response_model=QualityPackageResponse)
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

    @app.post("/api/parses/{parse_id}/quality-package", response_model=QualityPackageResponse)
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

    @app.get("/api/parses/{parse_id}/artifacts/{artifact_path:path}")
    def get_artifact(parse_id: str, artifact_path: str) -> FileResponse:
        try:
            path = storage.resolve_package_file(parse_id, artifact_path)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Artifact not found.") from error
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return FileResponse(path, media_type=storage.content_type_for(path))

    @app.post("/api/parses/{parse_id}/reparse", response_model=ParseJobResponse)
    def reparse(parse_id: str, body: ReparseRequest) -> ParseJobResponse:
        try:
            current_package = storage.package_root(parse_id)
            source_path = next((current_package / "source").glob("original.*"))
        except StopIteration as error:
            raise HTTPException(status_code=404, detail="Original source file not found.") from error
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        content = source_path.read_bytes()
        filename = source_path.name.replace("original", "reparse", 1)
        request = ParseRequest(
            filename=filename,
            file_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
            content=content,
            parser_id=body.parser_id,
            options=dict(body.options),
        )
        try:
            result = parser_gateway.parse_for_package(request)
            new_parse_id = storage.new_parse_id()
            package_root = storage.write_parse_package(
                parse_id=new_parse_id,
                document=result.document,
                source_filename=filename,
                source_content=content,
                native_files=result.native_files,
            )
        except Exception as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return ParseJobResponse(
            parse_id=new_parse_id,
            package_path=package_path_text(package_root),
            document=result.document,
            native_artifact_count=len(result.document.native_artifacts),
        )

    return app


def _parse_options(options_json: str | None) -> dict[str, object]:
    if not options_json:
        return {}
    try:
        value = json.loads(options_json)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="options_json must be valid JSON.") from error
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="options_json must be a JSON object.")
    return value


app = create_app()
