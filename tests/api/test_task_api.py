from __future__ import annotations

import hashlib
import io
import json
import sys
from types import SimpleNamespace
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.backend import create_app  # noqa: E402
from document_parser.backend.task_endpoints import (  # noqa: E402
    _document_anchors,
    _repair_changes,
)
from document_parser.backend.storage import ApiStorage  # noqa: E402
from document_parser.backend.tasks import ProcessingTask, TaskFile  # noqa: E402
from document_parser.core.contracts import (  # noqa: E402
    AssetKind,
    BlockKind,
    DocumentAsset,
    DocumentBlock,
    EvidenceAvailability,
    EvidenceCapability,
    ParseConfidence,
    ParsedDocument,
    ParserProvenance,
    QualityState,
    SourceAnchor,
)
from document_parser.orchestration import ParseFailureKind, ParseJob, ParseJobStatus  # noqa: E402
from quality import run_quality  # noqa: E402
from quality.packaging.hashing import markdown_bytes, sha256_bytes, stable_json_bytes  # noqa: E402


def _record_submissions(client: TestClient) -> list[str]:
    submitted: list[str] = []
    client.app.state.task_queue.submit = submitted.append
    return submitted


def _fixture_document(
    source: bytes,
    *,
    filename: str,
    include_asset: bool = False,
) -> ParsedDocument:
    markdown = "# Fixture title\\n\\nFixture body."
    assets: list[DocumentAsset] = []
    if include_asset:
        markdown += "\\n\\n![Fixture image](assets/images/fixture.png)"
        assets.append(
            DocumentAsset(
                path="images/fixture.png",
                kind=AssetKind.IMAGE,
                file_type="image/png",
                content=b"fixture-png",
            )
        )
    return ParsedDocument(
        filename=filename,
        file_type="text/markdown",
        source_size_bytes=len(source),
        source_sha256=hashlib.sha256(source).hexdigest(),
        markdown=markdown,
        blocks=[
            DocumentBlock(
                source_block_id="heading",
                order_index=0,
                kind=BlockKind.HEADING,
                text="Fixture title",
                heading_level=1,
                markdown="# Fixture title",
                anchor=SourceAnchor(page_number=1),
            ),
            DocumentBlock(
                source_block_id="body",
                order_index=1,
                kind=BlockKind.PARAGRAPH,
                text="Fixture body.",
                markdown="Fixture body.",
                anchor=SourceAnchor(page_number=1),
            ),
        ],
        assets=assets,
        confidence=ParseConfidence(),
        provenance=ParserProvenance(parser_id="task-api-fixture"),
        capabilities={
            "page_bbox": EvidenceCapability(
                state=EvidenceAvailability.AVAILABLE,
                granularity="block",
            )
        },
    )


def _quality_with_state(package: object, state: QualityState):
    """Rebuild the inner manifest after setting an explicit test gate state."""

    report_payload = package.quality_report.model_dump(mode="python")
    report_payload["state"] = state
    report_payload["reparse_recommendation"] = (
        {"parser_id": "docling", "reason": "fixture requires reparse"}
        if state == QualityState.REPARSE_REQUIRED
        else None
    )
    report = type(package.quality_report).model_validate(report_payload)
    candidate = package.model_copy(update={"quality_report": report})
    manifest = type(package.package_manifest)(
        artifacts={
            "optimized.md": sha256_bytes(markdown_bytes(candidate.optimized_markdown)),
            "canonical_document.json": sha256_bytes(
                stable_json_bytes(candidate.canonical_document)
            ),
            "quality_report.json": sha256_bytes(stable_json_bytes(candidate.quality_report)),
        }
    )
    return candidate.model_copy(update={"package_manifest": manifest})


def _quality_run_id(package: object) -> str:
    encoded = json.dumps(
        package.package_manifest.model_dump(mode="json"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:32]


def _publish_completed_job(
    storage: ApiStorage,
    *,
    marker: str,
    quality_state: QualityState = QualityState.PASS,
    include_asset: bool = False,
) -> tuple[ParseJob, ParsedDocument]:
    source = f"# Source {marker}\\n\\nBody.".encode("utf-8")
    filename = f"{marker}.md"
    job = storage.create_job(
        parse_id=storage.new_parse_id(),
        source_filename=filename,
        source_file_type="text/markdown",
        source_content=source,
        requested_parser_id="docling",
        options={"fixture_option": marker},
    )
    for stage in (
        ParseJobStatus.PREFLIGHT,
        ParseJobStatus.PARSING,
        ParseJobStatus.NORMALIZING,
        ParseJobStatus.QUALITY_CHECKING,
    ):
        job = storage.save_job(job.transition(stage))
    document = _fixture_document(source, filename=filename, include_asset=include_asset)
    quality = _quality_with_state(run_quality(document), quality_state)
    package_path = storage.commit_completed_job(
        job=job,
        document=document,
        quality_package=quality,
        native_files={"native/fixture.json": b'{"private": true}'},
    )
    terminal = ParseJobStatus.SUCCEEDED
    job = storage.save_job(
        job.transition(
            terminal,
            document_id=document.document_id,
            quality_run_id=_quality_run_id(quality),
            quality_state=quality_state.value,
            package_path=package_path,
            retryable=False,
        )
    )
    return job, document


def _create_failed_job(storage: ApiStorage, *, marker: str) -> ParseJob:
    source = f"# Failed {marker}\\n\\nBody.".encode("utf-8")
    job = storage.create_job(
        parse_id=storage.new_parse_id(),
        source_filename=f"{marker}.md",
        source_file_type="text/markdown",
        source_content=source,
        requested_parser_id="docling",
        options={"fixture_option": marker},
    )
    return storage.save_job(
        job.transition(
            ParseJobStatus.FAILED,
            error="Synthetic retryable fixture failure.",
            failure_kind=ParseFailureKind.TRANSIENT,
            retryable=True,
        )
    )


def _create_processing_job(storage: ApiStorage, *, marker: str) -> ParseJob:
    source = f"# Processing {marker}\\n\\nBody.".encode("utf-8")
    return storage.create_job(
        parse_id=storage.new_parse_id(),
        source_filename=f"{marker}.md",
        source_file_type="text/markdown",
        source_content=source,
        requested_parser_id="docling",
        options={"fixture_option": marker},
    )


def _task_for_jobs(storage: ApiStorage, *jobs: ParseJob) -> ProcessingTask:
    task = ProcessingTask(
        task_id=storage.new_task_id(),
        files=[
            TaskFile(
                display_name=job.source_filename,
                source_file_type=job.source_file_type,
                source_size_bytes=job.source_size_bytes,
            ).attach_initial_parse(job.parse_id)
            for job in jobs
        ],
    )
    return storage.create_task(task)


def _assert_task_payload_is_safe(payload: object, *, private_values: set[str]) -> None:
    serialized = json.dumps(payload, sort_keys=True)
    for value in private_values:
        assert value not in serialized
    forbidden_keys = {
        "package_path",
        "source_sha256",
        "source_filename",
        "idempotency_key",
        "options",
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


def test_create_single_file_task_is_readable_and_uses_only_safe_projection(tmp_path: Path) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        submitted = _record_submissions(client)
        response = client.post(
            "/api/tasks",
            data={"parser_id": "docling", "options_json": '{"language":"zh"}'},
            files=[("files", ("single.md", b"# One\\n\\nBody.", "text/markdown"))],
        )

        assert response.status_code == 202, response.text
        body = response.json()
        task = body["task"]
        assert body["task_id"] == task["task_id"]
        assert body["status_url"] == f"/api/tasks/{body['task_id']}"
        assert body["rejected_files"] == []
        assert task["aggregate"]["total_files"] == 1
        assert task["counts"] == {
            "processing": 1,
            "needs_review": 0,
            "available": 0,
            "failed": 0,
        }
        task_file = task["files"][0]
        assert task_file["display_name"] == "single.md"
        assert task_file["state"] == "processing"
        assert task_file["stage"] == "queued"
        assert submitted == [task_file["active_parse_id"]]

        readback = client.get(f"/api/tasks/{body['task_id']}")
        events = client.get(f"/api/tasks/{body['task_id']}/events")
        assert readback.status_code == 200, readback.text
        assert events.status_code == 200, events.text
        assert readback.json()["task"] == task
        assert events.json()["task_id"] == body["task_id"]
        assert events.json()["events"] == []
        _assert_task_payload_is_safe(
            {"create": body, "read": readback.json(), "events": events.json()},
            private_values={
                hashlib.sha256(b"# One\\n\\nBody.").hexdigest(),
                str(tmp_path.resolve()),
                "language",
            },
        )


def test_create_many_file_task_supports_partial_acceptance_and_idempotent_replay(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        submitted = _record_submissions(client)
        upload = [
            ("files", ("first.md", b"# First\\n\\nBody.", "text/markdown")),
            ("files", ("second.md", b"# Second\\n\\nBody.", "text/markdown")),
        ]
        first = client.post(
            "/api/tasks",
            headers={"Idempotency-Key": "task-many-replay"},
            data={"parser_id": "docling"},
            files=upload,
        )
        replay = client.post(
            "/api/tasks",
            headers={"Idempotency-Key": "task-many-replay"},
            data={"parser_id": "docling"},
            files=upload,
        )

        assert first.status_code == 202, first.text
        assert replay.status_code == 202, replay.text
        assert replay.json()["task_id"] == first.json()["task_id"]
        task_files = first.json()["task"]["files"]
        assert len(task_files) == 2
        assert {
            client.app.state.storage.load_job(item["active_parse_id"]).requested_parser_id
            for item in task_files
        } == {"docling"}
        assert len(submitted) == 2
        assert len(set(submitted)) == 2

        partial = client.post(
            "/api/tasks",
            data={"parser_id": "docling"},
            files=[
                ("files", ("accepted.md", b"# Accepted\\n\\nBody.", "text/markdown")),
                ("files", ("empty.md", b"fixture", "application/pdf")),
            ],
        )
        assert partial.status_code == 202, partial.text
        partial_body = partial.json()
        assert [item["display_name"] for item in partial_body["task"]["files"]] == [
            "accepted.md"
        ]
        assert partial_body["task"]["aggregate"]["total_files"] == 1
        assert partial_body["rejected_files"] == [
            {"display_name": "empty.md", "reason": "文件格式或内容无法处理。"}
        ]


def test_task_read_aggregates_processing_available_review_and_failed_files(tmp_path: Path) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        storage = client.app.state.storage
        processing = _create_processing_job(storage, marker="processing")
        available, _ = _publish_completed_job(storage, marker="available")
        review, _ = _publish_completed_job(
            storage,
            marker="review",
            quality_state=QualityState.MANUAL_REVIEW_REQUIRED,
        )
        failed = _create_failed_job(storage, marker="failed")
        task = _task_for_jobs(storage, processing, available, review, failed)

        response = client.get(f"/api/tasks/{task.task_id}")

        assert response.status_code == 200, response.text
        rendered = response.json()["task"]
        assert rendered["aggregate"] == {
            "task_id": task.task_id,
            "total_files": 4,
            "processing_count": 1,
            "needs_review_count": 0,
            "available_count": 2,
            "failed_count": 1,
            "completed_count": 3,
            "downloadable_count": 2,
            "updated_at": rendered["aggregate"]["updated_at"],
        }
        assert rendered["counts"] == {
            "processing": 1,
            "needs_review": 0,
            "available": 2,
            "failed": 1,
        }
        assert rendered["downloads"] == {
            "original": {"available": True, "count": 2},
            "optimized": {"available": True, "count": 2},
        }
        state_by_name = {item["display_name"]: item["state"] for item in rendered["files"]}
        assert state_by_name == {
            "processing.md": "processing",
            "available.md": "available",
            "review.md": "available",
            "failed.md": "failed",
        }


def test_task_file_detail_and_both_previews_are_bound_to_verified_package(tmp_path: Path) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        storage = client.app.state.storage
        job, document = _publish_completed_job(storage, marker="preview", include_asset=True)
        task = _task_for_jobs(storage, job)
        task_file = task.files[0]

        detail = client.get(f"/api/tasks/{task.task_id}/files/{task_file.task_file_id}")
        original = client.get(
            f"/api/tasks/{task.task_id}/files/{task_file.task_file_id}/preview",
            params={"view": "original"},
        )
        optimized = client.get(
            f"/api/tasks/{task.task_id}/files/{task_file.task_file_id}/preview",
            params={"view": "optimized"},
        )

        assert detail.status_code == 200, detail.text
        detail_body = detail.json()
        assert detail_body["task_id"] == task.task_id
        assert detail_body["task_file_id"] == task_file.task_file_id
        assert detail_body["active_parse_id"] == job.parse_id
        assert detail_body["current_parse_id"] == job.parse_id
        assert detail_body["parse_history"] == [job.parse_id]
        assert detail_body["state"] == "available"
        assert detail_body["allowed_actions"] == ["view", "reparse"]
        assert detail_body["quality_summary"]["state"] == "pass"
        assert detail_body["preview_urls"] == {
            "optimized": f"/api/tasks/{task.task_id}/files/{task_file.task_file_id}/preview?view=optimized",
            "original": f"/api/tasks/{task.task_id}/files/{task_file.task_file_id}/preview?view=original",
        }

        assert original.status_code == 200, original.text
        assert original.json()["view"] == "original"
        assert original.json()["markdown"] == document.markdown
        assert original.json()["anchors"][0]["page_number"] == 1
        assert optimized.status_code == 200, optimized.text
        assert optimized.json()["view"] == "optimized"
        assert "Fixture title" in optimized.json()["markdown"]

        unknown_view = client.get(
            f"/api/tasks/{task.task_id}/files/{task_file.task_file_id}/preview",
            params={"view": "unsupported"},
        )
        assert unknown_view.status_code == 400
        _assert_task_payload_is_safe(
            detail_body,
            private_values={job.source_sha256, str(storage.package_root(job.parse_id).resolve())},
        )


def test_task_retry_replays_same_child_and_switches_only_once(tmp_path: Path) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        storage = client.app.state.storage
        parent = _create_failed_job(storage, marker="retry")
        task = _task_for_jobs(storage, parent)
        task_file = task.files[0]
        submitted = _record_submissions(client)
        endpoint = f"/api/tasks/{task.task_id}/files/{task_file.task_file_id}/retry"

        first = client.post(endpoint, headers={"Idempotency-Key": "task-file-retry"})
        replay = client.post(endpoint, headers={"Idempotency-Key": "task-file-retry"})

        assert first.status_code == 202, first.text
        assert replay.status_code == 202, replay.text
        child_parse_id = first.json()["parse_id"]
        assert replay.json()["parse_id"] == child_parse_id
        assert child_parse_id != parent.parse_id
        assert submitted == [child_parse_id]
        child = storage.load_job(child_parse_id)
        assert child.parent_parse_id == parent.parse_id
        current = client.get(f"/api/tasks/{task.task_id}/files/{task_file.task_file_id}")
        assert current.status_code == 200, current.text
        assert current.json()["active_parse_id"] == child_parse_id
        assert current.json()["parse_history"] == [parent.parse_id, child_parse_id]


def test_task_reparse_replays_same_child_and_preserves_logical_file_history(tmp_path: Path) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        storage = client.app.state.storage
        parent, _ = _publish_completed_job(storage, marker="reparse")
        task = _task_for_jobs(storage, parent)
        task_file = task.files[0]
        submitted = _record_submissions(client)
        endpoint = f"/api/tasks/{task.task_id}/files/{task_file.task_file_id}/reparse"
        request = {"parser_id": "mineru", "options": {"language": "zh"}}

        first = client.post(
            endpoint,
            headers={"Idempotency-Key": "task-file-reparse"},
            json=request,
        )
        replay = client.post(
            endpoint,
            headers={"Idempotency-Key": "task-file-reparse"},
            json=request,
        )

        assert first.status_code == 202, first.text
        assert replay.status_code == 202, replay.text
        child_parse_id = first.json()["parse_id"]
        assert replay.json()["parse_id"] == child_parse_id
        assert child_parse_id != parent.parse_id
        assert submitted == [child_parse_id]
        child = storage.load_job(child_parse_id)
        assert child.parent_parse_id == parent.parse_id
        assert child.requested_parser_id == "mineru"
        assert child.options == {"language": "zh"}
        current = client.get(f"/api/tasks/{task.task_id}/files/{task_file.task_file_id}")
        assert current.status_code == 200, current.text
        assert current.json()["active_parse_id"] == child_parse_id
        assert current.json()["parse_history"] == [parent.parse_id, child_parse_id]


def test_task_archives_contain_only_exact_public_original_and_optimized_sets(tmp_path: Path) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        storage = client.app.state.storage
        first, _ = _publish_completed_job(storage, marker="archive-one", include_asset=True)
        second, _ = _publish_completed_job(storage, marker="archive-two")
        task = _task_for_jobs(storage, first, second)

        original = client.get(f"/api/tasks/{task.task_id}/downloads/original")
        optimized = client.get(f"/api/tasks/{task.task_id}/downloads/optimized")

        assert original.status_code == 200, original.text
        assert optimized.status_code == 200, optimized.text
        assert original.headers["content-type"].startswith("application/zip")
        assert optimized.headers["content-type"].startswith("application/zip")
        first_id, second_id = (item.task_file_id for item in task.files)
        original_expected = {
            "archive_manifest.json",
            f"{first_id}/document.md",
            f"{first_id}/parsed_document.json",
            f"{first_id}/assets/images/fixture.png",
            f"{first_id}/parse_manifest.json",
            f"{second_id}/document.md",
            f"{second_id}/parsed_document.json",
            f"{second_id}/parse_manifest.json",
        }
        optimized_expected = {
            "archive_manifest.json",
            f"{first_id}/optimized.md",
            f"{first_id}/canonical_document.json",
            f"{first_id}/quality_report.json",
            f"{first_id}/package_manifest.json",
            f"{first_id}/assets/images/fixture.png",
            f"{first_id}/delivery_manifest.json",
            f"{second_id}/optimized.md",
            f"{second_id}/canonical_document.json",
            f"{second_id}/quality_report.json",
            f"{second_id}/package_manifest.json",
            f"{second_id}/delivery_manifest.json",
        }
        with zipfile.ZipFile(io.BytesIO(original.content)) as archive:
            assert set(archive.namelist()) == original_expected
            manifest = json.loads(archive.read("archive_manifest.json"))
            assert manifest["archive_kind"] == "original"
            assert {item["parse_id"] for item in manifest["included"]} == {
                first.parse_id,
                second.parse_id,
            }
        with zipfile.ZipFile(io.BytesIO(optimized.content)) as archive:
            assert set(archive.namelist()) == optimized_expected
            manifest = json.loads(archive.read("archive_manifest.json"))
            assert manifest["archive_kind"] == "optimized"
            assert not any(
                path.startswith(("source/", "native/"))
                for path in archive.namelist()
            )
            for task_file_id in (first_id, second_id):
                report = json.loads(archive.read(f"{task_file_id}/quality_report.json"))
                assert report["state"] == "pass"


def test_task_download_delivers_quality_guidance_and_refuses_tampered_manifest(tmp_path: Path) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        storage = client.app.state.storage
        review, _ = _publish_completed_job(
            storage,
            marker="quality-gated",
            quality_state=QualityState.MANUAL_REVIEW_REQUIRED,
        )
        gated_task = _task_for_jobs(storage, review)
        readback = client.get(f"/api/tasks/{gated_task.task_id}")
        delivered = client.get(f"/api/tasks/{gated_task.task_id}/downloads/optimized")

        assert readback.status_code == 200, readback.text
        assert readback.json()["task"]["downloads"]["optimized"] == {
            "available": True,
            "count": 1,
        }
        assert delivered.status_code == 200, delivered.text
        with zipfile.ZipFile(io.BytesIO(delivered.content)) as archive:
            report = json.loads(
                archive.read(f"{gated_task.files[0].task_file_id}/quality_report.json")
            )
        assert report["state"] == QualityState.MANUAL_REVIEW_REQUIRED.value

        available, _ = _publish_completed_job(storage, marker="tampered")
        tampered_task = _task_for_jobs(storage, available)
        package_path = storage.package_root(available.parse_id) / "document.md"
        package_path.write_text("tampered package content", encoding="utf-8")
        tampered = client.get(f"/api/tasks/{tampered_task.task_id}/downloads/original")

        assert tampered.status_code == 409, tampered.text
        assert tampered.json()["detail"] == "The requested download cannot be verified."
        assert str(package_path) not in tampered.json()["detail"]

def test_task_repair_records_are_localized_deduplicated_and_preview_anchored() -> None:
    block = SimpleNamespace(
        id="block-1",
        source_block_id="source-1",
        markdown="# 标题",
        text="标题",
        order_index=0,
        anchor=SimpleNamespace(page_number=2),
        kind=SimpleNamespace(value="heading"),
    )
    repair = SimpleNamespace(
        repair_id="repair-1",
        rule_id="QL-RPR-003",
        description="Convert table HTML to parser-neutral Markdown.",
        affected_block_ids=["block-1"],
        evidence={
            "before": "<table>old</table>",
            "after": "| new |",
            "parameters": {"table_id": "table-1"},
        },
    )
    package = SimpleNamespace(
        quality_report=SimpleNamespace(applied_repairs=[repair, repair])
    )

    changes = _repair_changes(SimpleNamespace(blocks=[block]), package)
    assert len(changes) == 1
    assert changes[0]["title"] == "规范化 HTML 表格"
    assert "表格 table-1" in changes[0]["description"]
    assert changes[0]["location"] == "第 2 页 · 1 个正文位置"
    assert changes[0]["anchor_ids"] == ["block-1"]
    assert changes[0]["duplicate_count"] == 2
    assert not changes[0]["description"].startswith("Convert")

    anchors = _document_anchors(
        SimpleNamespace(blocks=[block]),
        markdown="前言\n\n# 标题\n\n正文",
    )
    assert anchors[0]["line"] == 3
    assert anchors[0]["block_id"] == "block-1"
