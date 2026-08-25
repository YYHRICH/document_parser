"""HTTP 触发层应用装配：FastAPI 工厂 + 静态资源 + 路由注册。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ...app.bootstrap import ApplicationContainer, build_application
from ...app.orchestration import DocumentParsePipeline
from .routes import build_router


def create_app(
    *,
    storage_root: Path | str = Path("outputs/api"),
    parser: DocumentParsePipeline | None = None,
    application: ApplicationContainer | None = None,
) -> FastAPI:
    app = FastAPI(title="Document Parser API", version="0.1.0")
    container = application or build_application(storage_root=storage_root, parser=parser)
    frontend_root = Path(__file__).resolve().parents[2] / "frontend"
    if frontend_root.exists():
        app.mount("/static", StaticFiles(directory=frontend_root), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        index_path = frontend_root / "index.html"
        if index_path.is_file():
            return HTMLResponse(index_path.read_text(encoding="utf-8"))
        return HTMLResponse("<!doctype html><html><body><p>Frontend not built.</p></body></html>")

    app.include_router(build_router(application=container))
    return app


app = create_app()
