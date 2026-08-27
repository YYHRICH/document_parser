import json
import time
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.backend import create_app  # noqa: E402
from document_parser.backend.storage import ApiStorage  # noqa: E402
from document_parser.orchestration import ParseFailureKind, ParseJobStatus  # noqa: E402


def _create_terminal_parent(
    storage: ApiStorage,
    *,
    status: ParseJobStatus = ParseJobStatus.FAILED,
    failure_kind: ParseFailureKind | None = ParseFailureKind.TRANSIENT,
    retryable: bool = True,
):
    source = b"# Retry fixture\n\nBody."
    job = storage.create_job(
        parse_id=storage.new_parse_id(),
        source_filename="retry.md",
        source_file_type="text/markdown",
        source_content=source,
        requested_parser_id="docling",
        options={"language": "en"},
    )
    if status == ParseJobStatus.FAILED:
        assert failure_kind is not None
        return storage.save_job(
            job.transition(
                ParseJobStatus.FAILED,
                error=f"Synthetic {failure_kind.value} failure.",
                failure_kind=failure_kind,
                retryable=retryable,
            )
        )
    if status == ParseJobStatus.CANCELLED:
        return storage.save_job(
            job.transition(
                ParseJobStatus.CANCELLED,
                error="Cancelled before execution.",
                failure_kind=ParseFailureKind.CANCELLED,
                retryable=False,
            )
        )
    if status == ParseJobStatus.SUCCEEDED:
        for stage in (
            ParseJobStatus.PREFLIGHT,
            ParseJobStatus.PARSING,
            ParseJobStatus.NORMALIZING,
            ParseJobStatus.QUALITY_CHECKING,
        ):
            job = storage.save_job(job.transition(stage))
        return storage.save_job(
            job.transition(
                ParseJobStatus.SUCCEEDED,
                document_id=uuid4(),
                package_path="/synthetic/completed-package",
                retryable=False,
            )
        )
    raise AssertionError(f"Unsupported synthetic terminal state: {status}")


def _record_submissions(client: TestClient) -> list[str]:
    submitted: list[str] = []

    def record(parse_id: str) -> None:
        submitted.append(parse_id)

    client.app.state.task_queue.submit = record
    return submitted


def _submit_job(client: TestClient, *, key: str | None = None, content: bytes = b"# Title\n\nBody.") -> dict[str, object]:
    headers = {"Idempotency-Key": key} if key else {}
    response = client.post(
        "/api/jobs",
        headers=headers,
        data={"parser_id": "docling"},
        files={"file": ("notes.md", content, "text/markdown")},
    )
    assert response.status_code == 202, response.text
    return response.json()


def _wait_for_terminal_job(client: TestClient, parse_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 90.0
    latest: dict[str, object] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{parse_id}")
        assert response.status_code == 200, response.text
        latest = response.json()
        if latest["status"] in {"succeeded", "failed", "cancelled", "needs_review"}:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"job did not become terminal within 90 seconds: {latest}")


class _FailingGateway:
    """Minimal gateway which exercises the persisted parse-failure path."""

    def list_parsers(self) -> list[object]:
        return []

    def parse_for_package(self, _request: object) -> object:
        raise RuntimeError(
            r"password=review-password token=review-token path=C:\private\review.pdf"
        )


def _assert_public_job_payload_is_secret_free(
    payload: object,
    *,
    private_values: set[str],
) -> None:
    serialized = json.dumps(payload, sort_keys=True)
    for value in private_values:
        assert value not in serialized

    forbidden_keys = {
        "attempt_id",
        "data",
        "event_id",
        "idempotency_key",
        "message",
        "metrics",
        "package_path",
        "parameters_fingerprint",
        "parser_id",
        "parser_version",
        "quality_run_id",
        "reason",
        "revision",
        "source_filename",
        "source_sha256",
        "source_size_bytes",
    }

    def visit(value: object) -> None:
        if isinstance(value, dict):
            assert not (forbidden_keys & set(value))
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(payload)


def test_public_job_views_allowlist_private_control_plane_data(tmp_path: Path) -> None:
    source = b"# Confidential document\n\nPrivate body."
    private_options = {
        "route_profile": "quality_first",
        "allow_cloud": False,
        "password": "review-password",
        "nested": {"apiToken": "review-token"},
    }
    private_idempotency_key = "review-private-key"

    with TestClient(
        create_app(storage_root=tmp_path, gateway=_FailingGateway(), job_workers=1)
    ) as client:
        response = client.post(
            "/api/jobs",
            headers={"Idempotency-Key": private_idempotency_key},
            data={
                "parser_id": "failing-parser",
                "options_json": json.dumps(private_options),
            },
            files={"file": ("confidential.md", source, "text/markdown")},
        )
        assert response.status_code == 202, response.text
        created = response.json()
        parse_id = created["parse_id"]
        assert created["job"]["source_extension"] == ".md"
        assert created["job"]["requested_parser_id"] == "failing-parser"
        assert created["job"]["options"] == {
            "route_profile": "quality_first",
            "allow_cloud": False,
        }

        final = _wait_for_terminal_job(client, parse_id)
        assert final["status"] == "failed", final
        assert final["job"]["error"] == "The parser could not process this document."
        assert final["job"]["error_reference"] == "failure-parser"

        persisted = client.app.state.storage.load_job(parse_id)
        assert persisted.source_filename == "confidential.md"
        assert persisted.options == private_options
        assert persisted.idempotency_key == private_idempotency_key

        private_values = {
            "confidential.md",
            private_idempotency_key,
            "review-password",
            "review-token",
            r"C:\private\review.pdf",
            persisted.source_sha256,
        }
        _assert_public_job_payload_is_secret_free(created, private_values=private_values)
        _assert_public_job_payload_is_secret_free(final, private_values=private_values)

        events_response = client.get(f"/api/jobs/{parse_id}/events")
        assert events_response.status_code == 200, events_response.text
        events = events_response.json()
        _assert_public_job_payload_is_secret_free(events, private_values=private_values)
        assert events["error"] == "The parser could not process this document."
        assert events["error_reference"] == "failure-parser"
        assert events["attempts"]
        assert set(events["attempts"][-1]) == {
            "status",
            "duration_ms",
            "failure_kind",
            "retryable",
            "occurred_at",
        }
        assert events["attempts"][-1]["status"] == "failed"
        assert events["attempts"][-1]["failure_kind"] == "parser"
        assert all(
            set(event) == {"previous_status", "status", "occurred_at"}
            for event in events["events"]
        )


def test_async_job_persists_attempts_and_result(tmp_path: Path) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        created = _submit_job(client)
        assert created["status"] in {"queued", "preflight", "parsing", "normalizing", "quality_checking", "succeeded"}
        parse_id = created["parse_id"]
        final = _wait_for_terminal_job(client, parse_id)
        assert final["status"] == "succeeded", final
        assert final["job"]["attempts"]
        assert client.get(f"/api/parses/{parse_id}").status_code == 200
        events = client.get(f"/api/jobs/{parse_id}/events")
        assert events.status_code == 200
        assert events.json()["attempts"]
        metrics = client.get("/api/metrics")
        assert metrics.status_code == 200
        assert metrics.json()["status_counts"]["succeeded"] == 1


def test_job_idempotency_reuses_exact_request_and_rejects_mismatch(tmp_path: Path) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        first = _submit_job(client, key="same-request")
        second = _submit_job(client, key="same-request")
        assert first["parse_id"] == second["parse_id"]
        mismatch = client.post(
            "/api/jobs",
            headers={"Idempotency-Key": "same-request"},
            data={"parser_id": "docling"},
            files={"file": ("notes.md", b"different", "text/markdown")},
        )
        assert mismatch.status_code == 409


def test_public_execution_options_cannot_override_server_or_filesystem(tmp_path: Path) -> None:
    with TestClient(create_app(storage_root=tmp_path)) as client:
        response = client.post(
            "/api/jobs",
            data={"options_json": '{"native_output_dir":"C:/private"}'},
            files={"file": ("notes.md", b"# Title", "text/markdown")},
        )
        assert response.status_code == 400
        assert "server-controlled" in response.json()["detail"]


def test_result_manifest_detects_tampering_and_external_quality_write_is_disabled(tmp_path: Path) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        created = _submit_job(client)
        parse_id = created["parse_id"]
        final = _wait_for_terminal_job(client, parse_id)
        assert final["status"] == "succeeded"
        quality = client.get(f"/api/parses/{parse_id}/quality-package")
        assert quality.status_code == 200
        overwrite = client.post(
            f"/api/parses/{parse_id}/quality-package",
            json=quality.json()["quality_package"],
        )
        assert overwrite.status_code == 405

        private_artifact = tmp_path / parse_id / "native" / "tenant-private-secret.txt"
        private_artifact.write_text("private artifact body", encoding="utf-8")
        private_values = {
            "tenant-private-secret.txt",
            "native/tenant-private-secret.txt",
            str(private_artifact.resolve()),
        }
        expected_errors = {
            f"/api/parses/{parse_id}": "Parse result cannot be verified.",
            f"/api/parses/{parse_id}/quality-package": "Quality package cannot be verified.",
            f"/api/parses/{parse_id}/artifacts": "Published parse package cannot be verified.",
            f"/api/parses/{parse_id}/download": "Published parse package cannot be verified.",
            f"/api/parses/{parse_id}/artifacts/parsed_document.json": (
                "Published parse package cannot be verified."
            ),
        }
        for url, expected_detail in expected_errors.items():
            response = client.get(url)
            assert response.status_code == 409, response.text
            assert response.json()["detail"] == expected_detail
            for value in private_values:
                assert value not in response.json()["detail"]


def test_retry_creates_an_immutable_source_child_and_replay_does_not_resubmit(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        storage = client.app.state.storage
        parent = _create_terminal_parent(storage)
        parent_snapshot = parent.model_dump(mode="json")
        submitted = _record_submissions(client)

        first = client.post(
            f"/api/jobs/{parent.parse_id}/retry",
            headers={"Idempotency-Key": "retry-child-key"},
        )
        second = client.post(
            f"/api/jobs/{parent.parse_id}/retry",
            headers={"Idempotency-Key": "retry-child-key"},
        )

        assert first.status_code == 202, first.text
        assert second.status_code == 202, second.text
        child_parse_id = first.json()["parse_id"]
        assert second.json()["parse_id"] == child_parse_id
        assert child_parse_id != parent.parse_id
        assert submitted == [child_parse_id]

        child = storage.load_job(child_parse_id)
        assert child.parent_parse_id == parent.parse_id
        assert child.idempotency_key == "retry-child-key"
        assert child.source_sha256 == parent.source_sha256
        assert child.source_size_bytes == parent.source_size_bytes
        assert child.source_filename == parent.source_filename
        assert child.source_file_type == parent.source_file_type
        assert storage.job_source_path(child.parse_id).read_bytes() == storage.job_source_path(
            parent.parse_id
        ).read_bytes()
        assert storage.load_job(parent.parse_id).model_dump(mode="json") == parent_snapshot
        assert len(tuple(storage.iter_jobs())) == 2


@pytest.mark.parametrize(
    ("status", "failure_kind", "retryable", "expected_detail"),
    [
        (ParseJobStatus.SUCCEEDED, None, False, "Only failed jobs"),
        (ParseJobStatus.CANCELLED, ParseFailureKind.CANCELLED, False, "Only failed jobs"),
        (ParseJobStatus.FAILED, ParseFailureKind.POLICY, True, "policy"),
        (ParseJobStatus.FAILED, ParseFailureKind.UNSUPPORTED, True, "unsupported"),
        (ParseJobStatus.FAILED, ParseFailureKind.INTEGRITY, True, "integrity"),
        (ParseJobStatus.FAILED, ParseFailureKind.TRANSIENT, False, "not retryable"),
    ],
)
def test_retry_rejects_non_eligible_parent_jobs(
    tmp_path: Path,
    status: ParseJobStatus,
    failure_kind: ParseFailureKind | None,
    retryable: bool,
    expected_detail: str,
) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        storage = client.app.state.storage
        parent = _create_terminal_parent(
            storage,
            status=status,
            failure_kind=failure_kind,
            retryable=retryable,
        )

        response = client.post(f"/api/jobs/{parent.parse_id}/retry")

        assert response.status_code == 409, response.text
        assert expected_detail.lower() in response.json()["detail"].lower()
        assert len(tuple(storage.iter_jobs())) == 1


def test_retry_and_reparse_hide_tampered_source_details(tmp_path: Path) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        storage = client.app.state.storage
        source = b"# Confidential source\n\nBody."
        parent = storage.create_job(
            parse_id=storage.new_parse_id(),
            source_filename="confidential-source.md",
            source_file_type="text/markdown",
            source_content=source,
            requested_parser_id="docling",
            options={"password": "source-option-secret"},
        )
        parent = storage.save_job(
            parent.transition(
                ParseJobStatus.FAILED,
                error="Transient fixture failure.",
                failure_kind=ParseFailureKind.TRANSIENT,
                retryable=True,
            )
        )
        source_path = storage.job_source_path(parent.parse_id)
        source_path.write_bytes(b"tampered source")
        private_values = {
            parent.source_sha256,
            str(parent.source_size_bytes),
            parent.source_filename,
            "source-option-secret",
            str(source_path.resolve()),
        }

        retry = client.post(f"/api/jobs/{parent.parse_id}/retry")
        reparse = client.post(
            f"/api/parses/{parent.parse_id}/reparse",
            json={"parser_id": "docling", "options": {}},
        )

        assert retry.status_code == 409, retry.text
        assert retry.json()["detail"] == "The stored source cannot be verified for retry."
        assert reparse.status_code == 409, reparse.text
        assert reparse.json()["detail"] == "The stored source cannot be verified for reparse."
        for response in (retry, reparse):
            detail = response.json()["detail"]
            for value in private_values:
                assert value not in detail


def test_invalid_job_metadata_uses_safe_public_error_detail(tmp_path: Path) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        storage = client.app.state.storage
        job = storage.create_job(
            parse_id=storage.new_parse_id(),
            source_filename="confidential-metadata.md",
            source_file_type="text/markdown",
            source_content=b"source",
            requested_parser_id="docling",
            options={},
        )
        private_values = {"metadata-password", r"C:\private\job.json"}
        storage.job_path(job.parse_id).write_text(
            json.dumps(
                {
                    "parse_id": job.parse_id,
                    "password": "metadata-password",
                    "path": r"C:\private\job.json",
                }
            ),
            encoding="utf-8",
        )

        responses = [
            client.get(f"/api/jobs/{job.parse_id}"),
            client.get(f"/api/jobs/{job.parse_id}/events"),
            client.get(f"/api/jobs/{job.parse_id}/lineage"),
            client.get(
                "/api/jobs/compare",
                params={"left": job.parse_id, "right": job.parse_id},
            ),
        ]
        for response in responses:
            assert response.status_code == 400, response.text
            assert response.json()["detail"] == "Parse job metadata is invalid."
            for value in private_values:
                assert value not in response.json()["detail"]


def test_retry_missing_parent_returns_not_found(tmp_path: Path) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        response = client.post("/api/jobs/missing-parent/retry")

    assert response.status_code == 404


def test_reparse_idempotency_returns_one_child_per_key_without_duplicate_submit(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        storage = client.app.state.storage
        parent = _create_terminal_parent(storage)
        submitted = _record_submissions(client)
        request = {"parser_id": "docling", "options": {"language": "zh"}}

        first = client.post(
            f"/api/parses/{parent.parse_id}/reparse",
            headers={"Idempotency-Key": "reparse-child-key"},
            json=request,
        )
        replay = client.post(
            f"/api/parses/{parent.parse_id}/reparse",
            headers={"Idempotency-Key": "reparse-child-key"},
            json=request,
        )
        independent = client.post(
            f"/api/parses/{parent.parse_id}/reparse",
            headers={"Idempotency-Key": "reparse-child-key-2"},
            json=request,
        )
        mismatch = client.post(
            f"/api/parses/{parent.parse_id}/reparse",
            headers={"Idempotency-Key": "reparse-child-key"},
            json={"parser_id": "docling", "options": {"language": "en"}},
        )

        assert first.status_code == 202, first.text
        assert replay.status_code == 202, replay.text
        assert independent.status_code == 202, independent.text
        assert mismatch.status_code == 409, mismatch.text
        first_child_id = first.json()["parse_id"]
        assert replay.json()["parse_id"] == first_child_id
        assert independent.json()["parse_id"] != first_child_id
        assert submitted == [first_child_id, independent.json()["parse_id"]]
        for child_parse_id in submitted:
            child = storage.load_job(child_parse_id)
            assert child.parent_parse_id == parent.parse_id
            assert child.source_sha256 == parent.source_sha256
            assert child.source_size_bytes == parent.source_size_bytes
        assert len(tuple(storage.iter_jobs())) == 3

