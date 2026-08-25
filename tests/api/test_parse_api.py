import io
import json
import zipfile
import sys
from pathlib import Path

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.trigger.http.app import create_app  # noqa: E402


def test_backend_serves_frontend_shell_and_parser_list(tmp_path: Path) -> None:
    client = TestClient(create_app(storage_root=tmp_path))

    home = client.get("/")
    assert home.status_code == 200
    assert 'id="parseForm"' in home.text

    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert "submitParse" in script.text

    parsers = client.get("/api/parsers")
    assert parsers.status_code == 200
    parser_ids = {parser["parser_id"] for parser in parsers.json()["parsers"]}
    assert {"microsoft.markitdown", "anydoc", "docling", "mineru", "ocr"} <= parser_ids


def test_parse_api_creates_package_and_serves_artifact(tmp_path: Path) -> None:
    client = TestClient(create_app(storage_root=tmp_path))
    options = {
        "native_markdown": "# Native Title\n\nBody",
        "native_payload": {
            "blocks": [
                {
                    "id": "title-1",
                    "type": "title",
                    "text": "Native Title",
                    "page_number": 1,
                    "bbox": [1, 2, 30, 40],
                }
            ]
        },
        "native_files": {"debug.log": "ok"},
    }

    response = client.post(
        "/api/parses",
        data={"parser_id": "mineru", "options_json": json.dumps(options)},
        files={"file": ("paper.pdf", b"%PDF-1.7\nfixture", "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    parse_id = body["parse_id"]
    assert body["document"]["provenance"]["parser_id"] == "mineru"
    assert body["document"]["schema_version"] == "2.2"
    assert body["native_artifact_count"] >= 1
    assert (tmp_path / parse_id / "parsed_document.json").is_file()
    assert (tmp_path / parse_id / "quality_package.json").is_file()
    assert (tmp_path / parse_id / "native" / "mineru_result.json").is_file()

    read_response = client.get(f"/api/parses/{parse_id}")
    assert read_response.status_code == 200
    assert read_response.json()["document"]["filename"] == "paper.pdf"

    quality_response = client.get(f"/api/parses/{parse_id}/quality-package")
    assert quality_response.status_code == 200
    assert quality_response.json()["quality_package"]["document_id"] == body["document"]["document_id"]

    artifact_response = client.get(f"/api/parses/{parse_id}/artifacts/native/mineru_result.json")
    assert artifact_response.status_code == 200
    assert artifact_response.json()["blocks"][0]["source_block_id"] == "title-1"

    artifact_list = client.get(f"/api/parses/{parse_id}/artifacts")
    assert artifact_list.status_code == 200
    listed_paths = {item["path"] for item in artifact_list.json()["files"]}
    assert {"parsed_document.json", "quality_package.json", "native/mineru_result.json"} <= listed_paths

    download = client.get(f"/api/parses/{parse_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert {"parsed_document.json", "quality_package.json", "native/mineru_result.json"} <= set(archive.namelist())


def test_parse_api_reparse_uses_stored_source(tmp_path: Path) -> None:
    client = TestClient(create_app(storage_root=tmp_path))
    first = client.post(
        "/api/parses",
        data={"parser_id": "mineru"},
        files={"file": ("notes.md", b"# Title\n\nBody.", "text/markdown")},
    )
    assert first.status_code == 200

    reparse = client.post(
        f"/api/parses/{first.json()['parse_id']}/reparse",
        json={"parser_id": "mineru", "options": {"language": "en"}},
    )

    assert reparse.status_code == 200
    assert reparse.json()["parse_id"] != first.json()["parse_id"]
    assert reparse.json()["document"]["provenance"]["parser_id"] == "mineru"
    assert reparse.json()["document"]["provenance"]["parameters"]["language"] == "en"


def test_parse_api_accepts_and_serves_quality_package(tmp_path: Path) -> None:
    client = TestClient(create_app(storage_root=tmp_path))
    first = client.post(
        "/api/parses",
        data={"parser_id": "mineru"},
        files={"file": ("notes.md", b"# Title\n\nBody.", "text/markdown")},
    )
    assert first.status_code == 200

    parse_id = first.json()["parse_id"]
    document_id = first.json()["document"]["document_id"]
    quality_path = PROJECT_ROOT / "examples" / "contracts" / "quality_package.json"
    quality_payload = json.loads(quality_path.read_text(encoding="utf-8"))
    quality_payload["document_id"] = document_id
    quality_payload["canonical_document"]["document_id"] = document_id
    quality_payload["quality_report"]["document_id"] = document_id

    attach = client.post(f"/api/parses/{parse_id}/quality-package", json=quality_payload)
    assert attach.status_code == 200
    assert attach.json()["quality_package"]["document_id"] == document_id

    readback = client.get(f"/api/parses/{parse_id}/quality-package")
    assert readback.status_code == 200
    assert readback.json()["quality_package"]["quality_report"]["state"] == "pass_with_warnings"


def test_parse_api_rejects_unsafe_artifact_path(tmp_path: Path) -> None:
    client = TestClient(create_app(storage_root=tmp_path))
    response = client.get("/api/parses/not-real/artifacts/../secret.txt")

    assert response.status_code in {400, 404}
