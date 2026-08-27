"""Static shell coverage for the document-processing workbench."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.backend import create_app  # noqa: E402


def test_frontend_shell_exposes_task_upload_and_processing_center(tmp_path: Path) -> None:
    del tmp_path
    frontend = PROJECT_ROOT / "frontend"
    upload = (frontend / "index.html").read_text(encoding="utf-8")
    assert 'data-page="upload"' in upload
    assert 'id="taskUploadForm"' in upload
    assert 'id="fileInput"' in upload
    assert "multiple" in upload
    assert 'id="fileDropzone"' in upload
    assert 'id="fileQueue"' in upload
    assert 'id="parserSelect"' in upload
    assert 'id="parserHint"' in upload
    assert 'id="allowCloud"' in upload
    assert 'id="cloudHint"' in upload
    assert "解析模型" in upload
    assert 'id="startTask"' in upload
    assert "已选文件" in upload
    assert "待处理文件" not in upload
    assert "./api-config.js" in upload
    assert "./workbench.css" in upload
    assert "./workbench.js" in upload

    center = (frontend / "task-center.html").read_text(encoding="utf-8")
    assert 'data-page="task-center"' in center
    assert 'id="downloadButton"' in center
    assert 'id="downloadMenu"' in center
    assert 'data-download="original"' in center
    assert 'data-download="optimized"' in center
    assert 'id="statusSummary"' in center
    assert 'id="taskFileList"' in center
    assert 'id="rejectedNotice"' in center
    assert "原始解析压缩包" in center
    assert "优化后文档压缩包" in center

    body = (frontend / "workbench.js").read_text(encoding="utf-8")
    assert 'var UPLOAD_ENDPOINT = apiUrl("/api/tasks")' in body
    assert 'var PARSER_LIST_ENDPOINT = apiUrl("/api/parsers")' in body
    assert 'fetch(PARSER_LIST_ENDPOINT' in body
    assert 'formData.append("files", item.file, item.file.name)' in body
    assert 'formData.set("parser_id", selectedParserId)' in body
    assert 'formData.set("options_json"' in body
    assert 'var allowCloud = byId("allowCloud")' in body
    assert "selection_policy" in body
    assert "cloud_parsers_enabled" in body
    assert "function selectedExtensions()" in body
    assert 'fetch(apiUrl("/api/tasks/" + encodeURIComponent(taskId))' in body
    assert 'apiUrl("/api/tasks/" + encodeURIComponent(taskId) + "/downloads/"' in body
    assert "task_file_id" in body
    assert "function fileBuckets(task)" in body
    assert "button.disabled = count <= 0;" in body
    assert 'if (state.filter !== "all" && counts[state.filter] <= 0) state.filter = "all";' in body
    assert 'row.appendChild(create("span", "file-pending", "待提交"));' in body
    assert "taskCenterUrl(taskId, arrayOf(payload && payload.rejected_files).length)" in body
    assert "rejectedCountFromLocation" in body
    assert "history.replaceState" in body
    assert "documentDetailUrl(taskId, id)" in body
    assert "POLL_INTERVAL_MS" in body
    assert "正在处理文档。" in body
    assert "sessionStorage" not in body
    assert "百分比" not in body

    icons = (frontend / "assets" / "lucide-icons.js").read_text(encoding="utf-8")
    assert "Lucide Icons" in icons

    detail = (frontend / "document-detail.html").read_text(encoding="utf-8")
    assert 'id="detailSummary"' in detail
    detail_body = (frontend / "document-detail.js").read_text(encoding="utf-8")
    assert "function renderGuidancePanel" in detail_body
    assert "ui.summary.hidden = terminalPanel;" in detail_body
    assert "qualitySummary: qualitySummary" in detail_body
    assert "待确认项" in detail_body
    assert "相关说明已随优化后文档一并交付" in detail_body
    assert "定位到正文" in detail_body
    assert "anchor_ids" in detail_body
    assert "当前版本未找到该记录对应的正文位置" in detail_body
    assert "正文正在加载，加载完成后将自动定位" in detail_body
    assert "已自动修复" in detail_body
    assert "当前结果不能作为交付版本" not in detail_body
    detail_style = (frontend / "document-detail.css").read_text(encoding="utf-8")
    assert ".status-panel__issue-list" in detail_style
    assert ".revision-locate" in detail_style


def test_api_allows_only_configured_frontend_origin(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DOCUMENT_PARSER_FRONTEND_ORIGINS", "http://localhost:5173")
    with TestClient(create_app(storage_root=tmp_path)) as client:
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
