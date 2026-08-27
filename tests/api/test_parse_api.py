import hashlib
import io
import json
import zipfile
import sys

import pytest
import time
from pathlib import Path

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.backend import create_app  # noqa: E402
from document_parser.core.contracts import QualityState  # noqa: E402
from quality.packaging.artifacts import verify_package_files  # noqa: E402
from quality.packaging.hashing import markdown_bytes, sha256_bytes, stable_json_bytes  # noqa: E402


QUALITY_PACKAGE_ARTIFACTS = frozenset(
    {
        "optimized.md",
        "canonical_document.json",
        "quality_report.json",
        "package_manifest.json",
    }
)
QUALITY_PACKAGE_CORE_ARTIFACTS = QUALITY_PACKAGE_ARTIFACTS - {"package_manifest.json"}


def _assert_response_contains_no_package_path(payload: object) -> None:
    """Keep filesystem implementation paths out of every public response level."""

    if isinstance(payload, dict):
        assert "package_path" not in payload
        for value in payload.values():
            _assert_response_contains_no_package_path(value)
    elif isinstance(payload, list):
        for value in payload:
            _assert_response_contains_no_package_path(value)


def _wait_for_terminal_job(client: TestClient, parse_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 30.0
    latest: dict[str, object] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{parse_id}")
        assert response.status_code == 200, response.text
        latest = response.json()
        if latest["status"] in {"succeeded", "failed", "cancelled", "needs_review"}:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"job did not become terminal within 30 seconds: {latest}")


def _quality_package_with_state(package, quality_state: QualityState):
    """Create a manifest-consistent quality package for delivery policy tests."""

    report_payload = package.quality_report.model_dump(mode="python")
    report_payload["state"] = quality_state
    report_payload["reparse_recommendation"] = (
        {"parser_id": "docling", "reason": "fixture requires a reparse"}
        if quality_state == QualityState.REPARSE_REQUIRED
        else None
    )
    report = type(package.quality_report).model_validate(report_payload)
    candidate = package.model_copy(update={"quality_report": report})
    manifest = type(package.package_manifest)(
        artifacts={
            "optimized.md": sha256_bytes(markdown_bytes(candidate.optimized_markdown)),
            "canonical_document.json": sha256_bytes(stable_json_bytes(candidate.canonical_document)),
            "quality_report.json": sha256_bytes(stable_json_bytes(candidate.quality_report)),
        }
    )
    return candidate.model_copy(update={"package_manifest": manifest})


def _replace_stored_quality_state(
    client: TestClient,
    parse_id: str,
    quality_state: QualityState,
) -> None:
    storage = client.app.state.storage
    package = storage.load_quality_package(parse_id)
    storage.write_quality_package(
        parse_id,
        _quality_package_with_state(package, quality_state),
    )


def _create_completed_parse(client: TestClient) -> str:
    response = client.post(
        "/api/parses",
        data={"parser_id": "docling"},
        files={"file": ("delivery.md", b"# Delivery\n\nBody.", "text/markdown")},
    )
    assert response.status_code == 200, response.text
    return response.json()["parse_id"]


def test_backend_exposes_api_without_frontend_assets(tmp_path: Path) -> None:
    client = TestClient(create_app(storage_root=tmp_path))

    home = client.get("/")
    assert home.status_code == 404

    script = client.get("/static/workbench.js")
    assert script.status_code == 404

    parsers = client.get("/api/parsers")
    assert parsers.status_code == 200
    parser_payload = parsers.json()
    parser_ids = {parser["parser_id"] for parser in parser_payload["parsers"]}
    assert {"microsoft.markitdown", "anydoc", "docling", "mineru", "ocr"} <= parser_ids
    assert isinstance(parser_payload["selection_policy"]["cloud_parsers_enabled"], bool)


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
        data={"parser_id": "docling", "options_json": json.dumps(options)},
        files={"file": ("paper.md", b"# Native Title\n\nBody", "text/markdown")},
    )

    assert response.status_code == 200
    body = response.json()
    parse_id = body["parse_id"]
    assert body["document"]["provenance"]["parser_id"] == "docling"
    assert body["document"]["schema_version"] == "2.2"
    assert body["native_artifact_count"] >= 1
    _assert_response_contains_no_package_path(body)
    package_root = tmp_path / parse_id
    assert (package_root / "parsed_document.json").is_file()
    assert (package_root / "quality_package.json").is_file()
    assert (package_root / "native" / "result.json").is_file()
    assert all((package_root / name).is_file() for name in QUALITY_PACKAGE_ARTIFACTS)

    read_response = client.get(f"/api/parses/{parse_id}")
    assert read_response.status_code == 200
    read_payload = read_response.json()
    _assert_response_contains_no_package_path(read_payload)
    assert read_payload["document"]["filename"] == "paper.md"

    status_response = client.get(f"/api/jobs/{parse_id}")
    assert status_response.status_code == 200
    _assert_response_contains_no_package_path(status_response.json())

    quality_response = client.get(f"/api/parses/{parse_id}/quality-package")
    assert quality_response.status_code == 200
    quality_payload = quality_response.json()
    _assert_response_contains_no_package_path(quality_payload)
    assert quality_payload["quality_package"]["document_id"] == body["document"]["document_id"]
    expected_hashes = quality_payload["quality_package"]["package_manifest"]["artifacts"]
    assert set(expected_hashes) == QUALITY_PACKAGE_CORE_ARTIFACTS
    for artifact_path in QUALITY_PACKAGE_CORE_ARTIFACTS:
        assert hashlib.sha256((package_root / artifact_path).read_bytes()).hexdigest() == expected_hashes[artifact_path]
    assert json.loads((package_root / "package_manifest.json").read_text(encoding="utf-8"))["artifacts"] == expected_hashes

    artifact_response = client.get(f"/api/parses/{parse_id}/artifacts/native/result.json")
    assert artifact_response.status_code == 200
    assert artifact_response.json()["blocks"][0]["id"] == "title-1"

    artifact_list = client.get(f"/api/parses/{parse_id}/artifacts")
    assert artifact_list.status_code == 200
    listed_paths = {item["path"] for item in artifact_list.json()["files"]}
    assert {"parsed_document.json", "quality_package.json", "native/result.json"} <= listed_paths
    assert QUALITY_PACKAGE_ARTIFACTS <= listed_paths
    for artifact_path in QUALITY_PACKAGE_ARTIFACTS:
        quality_artifact = client.get(f"/api/parses/{parse_id}/artifacts/{artifact_path}")
        assert quality_artifact.status_code == 200
        assert quality_artifact.content == (package_root / artifact_path).read_bytes()

    download = client.get(f"/api/parses/{parse_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        archived_paths = set(archive.namelist())
        assert {"parsed_document.json", "quality_package.json", "native/result.json"} <= archived_paths
        assert QUALITY_PACKAGE_ARTIFACTS <= archived_paths


def test_parse_api_reparse_uses_stored_source(tmp_path: Path) -> None:
    client = TestClient(create_app(storage_root=tmp_path))
    first = client.post(
        "/api/parses",
        data={"parser_id": "docling"},
        files={"file": ("notes.md", b"# Title\n\nBody.", "text/markdown")},
    )
    assert first.status_code == 200

    reparse = client.post(
        f"/api/parses/{first.json()['parse_id']}/reparse",
        json={"parser_id": "docling", "options": {"language": "en"}},
    )

    assert reparse.status_code == 202
    child_parse_id = reparse.json()["parse_id"]
    assert child_parse_id != first.json()["parse_id"]
    completed = _wait_for_terminal_job(client, child_parse_id)
    assert completed["status"] == "succeeded", completed
    child_document = client.get(f"/api/parses/{child_parse_id}")
    assert child_document.status_code == 200
    assert child_document.json()["document"]["provenance"]["parser_id"] == "docling"
    assert child_document.json()["document"]["provenance"]["parameters"]["language"] == "en"


def test_parse_api_accepts_and_serves_quality_package(tmp_path: Path) -> None:
    client = TestClient(create_app(storage_root=tmp_path, allow_quality_package_override=True))
    first = client.post(
        "/api/parses",
        data={"parser_id": "docling"},
        files={"file": ("notes.md", b"# Title\n\nBody.", "text/markdown")},
    )
    assert first.status_code == 200

    parse_id = first.json()["parse_id"]
    document_id = first.json()["document"]["document_id"]
    quality_before_override = client.get(f"/api/parses/{parse_id}/quality-package")
    assert quality_before_override.status_code == 200
    quality_payload = quality_before_override.json()["quality_package"]

    attach = client.post(f"/api/parses/{parse_id}/quality-package", json=quality_payload)
    assert attach.status_code == 200
    _assert_response_contains_no_package_path(attach.json())
    assert attach.json()["quality_package"]["document_id"] == document_id

    readback = client.get(f"/api/parses/{parse_id}/quality-package")
    assert readback.status_code == 200
    _assert_response_contains_no_package_path(readback.json())
    assert readback.json()["quality_package"]["quality_report"]["state"] == quality_payload["quality_report"]["state"]


@pytest.mark.parametrize("quality_state", list(QualityState))
def test_delivery_returns_only_manifest_verified_business_artifacts(
    tmp_path: Path,
    quality_state: QualityState,
) -> None:
    client = TestClient(create_app(storage_root=tmp_path))
    parse_id = _create_completed_parse(client)
    _replace_stored_quality_state(client, parse_id, quality_state)

    response = client.get(f"/api/parses/{parse_id}/delivery")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        paths = set(archive.namelist())
        assert paths == QUALITY_PACKAGE_ARTIFACTS
        assert "parsed_document.json" not in paths
        assert not any(path.startswith(("source/", "native/")) for path in paths)
        delivery_files = {path: archive.read(path) for path in paths}
    manifest = verify_package_files(delivery_files)
    assert manifest.artifacts == json.loads(delivery_files["package_manifest.json"])["artifacts"]
    assert json.loads(delivery_files["quality_report.json"])["state"] == quality_state.value


@pytest.mark.parametrize(
    "quality_state",
    [
        QualityState.MANUAL_REVIEW_REQUIRED,
        QualityState.REPARSE_REQUIRED,
        QualityState.REJECTED,
    ],
)
def test_delivery_direct_url_includes_non_pass_quality_guidance(
    tmp_path: Path,
    quality_state: QualityState,
) -> None:
    client = TestClient(create_app(storage_root=tmp_path))
    parse_id = _create_completed_parse(client)
    _replace_stored_quality_state(client, parse_id, quality_state)

    response = client.get(f"/api/parses/{parse_id}/delivery")

    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        report = json.loads(archive.read("quality_report.json"))
    assert report["state"] == quality_state.value


def test_delivery_requires_the_outer_manifest_and_hides_integrity_details(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(storage_root=tmp_path))
    parse_id = _create_completed_parse(client)
    source_files = tuple((tmp_path / parse_id / "source").iterdir())
    assert len(source_files) == 1
    source_files[0].write_bytes(b"tampered source")

    response = client.get(f"/api/parses/{parse_id}/delivery")

    assert response.status_code == 409
    assert response.json()["detail"] == "Business delivery cannot be verified."
    assert "source" not in response.json()["detail"].lower()


def test_parse_api_rejects_unsafe_artifact_path(tmp_path: Path) -> None:
    client = TestClient(create_app(storage_root=tmp_path))
    response = client.get("/api/parses/not-real/artifacts/../secret.txt")

    assert response.status_code in {400, 404}
