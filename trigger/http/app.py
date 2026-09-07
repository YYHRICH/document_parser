"""HTTP 触发层应用装配：FastAPI 工厂 + 静态资源 + 路由注册。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ...app.bootstrap import ApplicationContainer, build_application, build_source_lifecycle
from ...infra.lifecycle import JsonSourceLifecycleRepository
from ...app.orchestration import DocumentParsePipeline
from .routes import build_router


def create_app(
    *,
    storage_root: Path | str = Path("outputs/api"),
    parser: DocumentParsePipeline | None = None,
    application: ApplicationContainer | None = None,
) -> FastAPI:
    app = FastAPI(title="Document Parser API", version="0.1.0")
    project_root = Path(__file__).resolve().parents[2]
    resolved_storage_root = Path(storage_root)
    if not resolved_storage_root.is_absolute():
        resolved_storage_root = project_root / resolved_storage_root
    container = application or build_application(storage_root=resolved_storage_root, parser=parser)
    workspace_root = resolved_storage_root.resolve() / "_lifecycle"
    raw_root = workspace_root / "raw"
    state_root = workspace_root / ".llmwiki" / ".document_parser"
    raw_root.mkdir(parents=True, exist_ok=True)
    lifecycle = build_source_lifecycle(
        raw_root=raw_root,
        state_root=state_root,
        storage_root=state_root / "packages",
        mobilework_root=resolved_storage_root / "_downstream-mobilework",
        mmwiki_root=resolved_storage_root / "_downstream-mmwiki",
        parser=container.parser,
    )
    lifecycle_repository = JsonSourceLifecycleRepository(state_root)
    frontend_root = project_root / "frontend"
    if frontend_root.exists():
        app.mount("/static", StaticFiles(directory=frontend_root), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        index_path = frontend_root / "index.html"
        if index_path.is_file():
            return HTMLResponse(index_path.read_text(encoding="utf-8"))
        return HTMLResponse("<!doctype html><html><body><p>Frontend not built.</p></body></html>")

    app.include_router(
        build_router(
            application=container,
            lifecycle=lifecycle,
            lifecycle_repository=lifecycle_repository,
            lifecycle_raw_root=raw_root,
            lifecycle_state_root=state_root,
        )
    )
    return app


app = create_app()
