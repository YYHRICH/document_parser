from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from document_parser.backend.storage import ApiStorage
from document_parser.backend.tasks import (
    ProcessingTask,
    TaskConflictError,
    TaskFile,
    TaskFileUserState,
    aggregate_task,
    project_task_file,
)
from document_parser.orchestration.models import (
    ParseFailureKind,
    ParseJob,
    ParseJobStatus,
)


def _job(
    parse_id: str,
    *,
    status: ParseJobStatus = ParseJobStatus.QUEUED,
    quality_state: str | None = None,
    source: bytes = b"source",
    file_type: str = "application/pdf",
    retryable: bool = False,
) -> ParseJob:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "parse_id": parse_id,
        "source_sha256": "a" * 64,
        "source_filename": "source.pdf",
        "source_file_type": file_type,
        "source_size_bytes": len(source),
        "status": status,
        "quality_state": quality_state,
        "retryable": retryable,
        "created_at": now,
        "updated_at": now,
    }
    if status in {ParseJobStatus.SUCCEEDED, ParseJobStatus.NEEDS_REVIEW}:
        payload.update(
            {
                "document_id": uuid4(),
                "package_path": "/private/package",
                "completed_at": now,
            }
        )
    if status in {ParseJobStatus.FAILED, ParseJobStatus.CANCELLED}:
        payload.update(
            {
                "completed_at": now,
                "error": "safe failure",
                "failure_kind": ParseFailureKind.TRANSIENT,
            }
        )
    return ParseJob.model_validate(payload)


@pytest.mark.parametrize(
    ("status", "quality_state", "expected"),
    [
        (ParseJobStatus.QUEUED, None, TaskFileUserState.PROCESSING),
        (ParseJobStatus.SUCCEEDED, "pass", TaskFileUserState.AVAILABLE),
        (ParseJobStatus.SUCCEEDED, "pass_with_warnings", TaskFileUserState.AVAILABLE),
        (ParseJobStatus.SUCCEEDED, "manual_review_required", TaskFileUserState.AVAILABLE),
        (ParseJobStatus.SUCCEEDED, "reparse_required", TaskFileUserState.AVAILABLE),
        (ParseJobStatus.SUCCEEDED, "rejected", TaskFileUserState.AVAILABLE),
        # Existing published review records remain downloadable after the policy change.
        (ParseJobStatus.NEEDS_REVIEW, "manual_review_required", TaskFileUserState.AVAILABLE),
        (ParseJobStatus.FAILED, None, TaskFileUserState.FAILED),
        # Unknown/missing terminal gate output is conservative: never downloadable.
        (ParseJobStatus.SUCCEEDED, None, TaskFileUserState.NEEDS_REVIEW),
    ],
)
def test_file_projection_maps_parse_and_quality_statuses_conservatively(
    status: ParseJobStatus,
    quality_state: str | None,
    expected: TaskFileUserState,
) -> None:
    task_file = TaskFile(
        task_file_id="file-one",
        display_name="report.pdf",
        source_file_type="application/pdf",
        source_size_bytes=6,
        active_parse_id="parse-one",
        parse_history=["parse-one"],
    )
    job = _job("parse-one", status=status, quality_state=quality_state, source=b"source")

    projection = project_task_file(task_file, job)

    assert projection.state == expected
    assert "package_path" not in projection.model_dump()
    assert "source_sha256" not in projection.model_dump()
    assert projection.quality_state in {
        None,
        "pass",
        "pass_with_warnings",
        "manual_review_required",
        "reparse_required",
        "rejected",
    }


def test_pending_file_and_missing_active_job_do_not_become_available() -> None:
    pending = TaskFile(
        task_file_id="pending-file",
        display_name="pending.pdf",
        source_file_type="application/pdf",
        source_size_bytes=1,
    )
    missing = TaskFile(
        task_file_id="missing-file",
        display_name="missing.pdf",
        source_file_type="application/pdf",
        source_size_bytes=1,
        active_parse_id="missing-parse",
        parse_history=["missing-parse"],
    )

    assert project_task_file(pending, None).state == TaskFileUserState.PROCESSING
    assert project_task_file(missing, None).state == TaskFileUserState.FAILED


def test_aggregate_counts_one_and_many_files() -> None:
    task = ProcessingTask(
        task_id="task-many",
        files=[
            TaskFile(
                task_file_id="queued-file",
                display_name="queued.pdf",
                source_file_type="application/pdf",
                source_size_bytes=1,
                active_parse_id="queued-parse",
                parse_history=["queued-parse"],
            ),
            TaskFile(
                task_file_id="available-file",
                display_name="available.pdf",
                source_file_type="application/pdf",
                source_size_bytes=1,
                active_parse_id="available-parse",
                parse_history=["available-parse"],
            ),
            TaskFile(
                task_file_id="review-file",
                display_name="review.pdf",
                source_file_type="application/pdf",
                source_size_bytes=1,
                active_parse_id="review-parse",
                parse_history=["review-parse"],
            ),
            TaskFile(
                task_file_id="failed-file",
                display_name="failed.pdf",
                source_file_type="application/pdf",
                source_size_bytes=1,
                active_parse_id="failed-parse",
                parse_history=["failed-parse"],
            ),
        ],
    )

    projection = aggregate_task(
        task,
        {
            "queued-parse": _job("queued-parse", source=b"x"),
            "available-parse": _job(
                "available-parse",
                status=ParseJobStatus.SUCCEEDED,
                quality_state="pass",
                source=b"x",
            ),
            "review-parse": _job(
                "review-parse",
                status=ParseJobStatus.NEEDS_REVIEW,
                quality_state="manual_review_required",
                source=b"x",
            ),
            "failed-parse": _job(
                "failed-parse",
                status=ParseJobStatus.FAILED,
                source=b"x",
                retryable=True,
            ),
        },
    )

    assert projection.aggregate.total_files == 4
    assert projection.aggregate.processing_count == 1
    assert projection.aggregate.available_count == 2
    assert projection.aggregate.needs_review_count == 0
    assert projection.aggregate.failed_count == 1
    assert projection.aggregate.completed_count == 3
    assert projection.aggregate.downloadable_count == 2


def _create_job(storage: ApiStorage, parse_id: str, content: bytes) -> ParseJob:
    return storage.create_job(
        parse_id=parse_id,
        source_filename="report.pdf",
        source_file_type="application/pdf",
        source_content=content,
        requested_parser_id="docling",
        options={},
    )


def test_task_storage_attaches_multiple_files_and_persists_reverse_links(tmp_path: Path) -> None:
    storage = ApiStorage(tmp_path)
    first_job = _create_job(storage, "parse-first", b"first")
    second_job = _create_job(storage, "parse-second", b"second")
    initial = storage.create_task(
        ProcessingTask(
            task_id="task-multi",
            files=[
                TaskFile(
                    task_file_id="file-first",
                    display_name="first.pdf",
                    source_file_type="application/pdf",
                    source_size_bytes=first_job.source_size_bytes,
                ),
                TaskFile(
                    task_file_id="file-second",
                    display_name="second.pdf",
                    source_file_type="application/pdf",
                    source_size_bytes=second_job.source_size_bytes,
                ),
            ],
        )
    )

    after_first = storage.attach_task_file_parse(
        initial.task_id,
        "file-first",
        first_job.parse_id,
        expected_revision=initial.revision,
    )
    after_second = storage.attach_task_file_parse(
        initial.task_id,
        "file-second",
        second_job.parse_id,
        expected_revision=after_first.revision,
    )

    restarted = ApiStorage(tmp_path)
    loaded = restarted.load_task(initial.task_id)
    assert loaded.revision == 2
    assert loaded.file_by_id("file-first").active_parse_id == first_job.parse_id
    assert loaded.file_by_id("file-second").active_parse_id == second_job.parse_id
    assert restarted.find_task_file_by_parse_id(first_job.parse_id).model_dump() == {
        "task_id": initial.task_id,
        "task_file_id": "file-first",
    }
    assert restarted.find_task_file_by_parse_id(second_job.parse_id).model_dump() == {
        "task_id": initial.task_id,
        "task_file_id": "file-second",
    }
    rendered = restarted.project_task(initial.task_id).model_dump(mode="json")
    assert "package_path" not in str(rendered)
    assert "source_sha256" not in str(rendered)
    assert after_second.revision == 2


def test_switch_active_parse_keeps_history_and_requires_same_source(tmp_path: Path) -> None:
    storage = ApiStorage(tmp_path)
    parent = _create_job(storage, "parse-parent", b"identical-source")
    child = storage.create_reparse_job(
        parent_parse_id=parent.parse_id,
        requested_parser_id="mineru",
        options={},
    ).job
    unrelated = _create_job(storage, "parse-unrelated", b"different-source")
    task = storage.create_task(
        ProcessingTask(
            task_id="task-switch",
            files=[
                TaskFile(
                    task_file_id="file-switch",
                    display_name="switch.pdf",
                    source_file_type="application/pdf",
                    source_size_bytes=parent.source_size_bytes,
                )
            ],
        )
    )
    attached = storage.attach_task_file_parse(
        task.task_id,
        "file-switch",
        parent.parse_id,
        expected_revision=task.revision,
    )
    switched = storage.switch_task_file_active_parse(
        task.task_id,
        "file-switch",
        child.parse_id,
        expected_revision=attached.revision,
    )

    task_file = switched.file_by_id("file-switch")
    assert task_file.active_parse_id == child.parse_id
    assert task_file.parse_history == [parent.parse_id, child.parse_id]
    assert storage.find_task_file_by_parse_id(parent.parse_id).task_file_id == "file-switch"
    assert storage.find_task_file_by_parse_id(child.parse_id).task_file_id == "file-switch"

    with pytest.raises(ValueError, match="same immutable source"):
        storage.switch_task_file_active_parse(
            task.task_id,
            "file-switch",
            unrelated.parse_id,
            expected_revision=switched.revision,
        )
    assert storage.load_task(task.task_id).revision == switched.revision


def test_task_storage_rejects_stale_compare_and_swap_revision(tmp_path: Path) -> None:
    storage = ApiStorage(tmp_path)
    first = _create_job(storage, "parse-cas-one", b"one")
    second = _create_job(storage, "parse-cas-two", b"two")
    task = storage.create_task(
        ProcessingTask(
            task_id="task-cas",
            files=[
                TaskFile(
                    task_file_id="file-cas-one",
                    display_name="one.pdf",
                    source_file_type="application/pdf",
                    source_size_bytes=first.source_size_bytes,
                ),
                TaskFile(
                    task_file_id="file-cas-two",
                    display_name="two.pdf",
                    source_file_type="application/pdf",
                    source_size_bytes=second.source_size_bytes,
                ),
            ],
        )
    )
    updated = storage.attach_task_file_parse(
        task.task_id,
        "file-cas-one",
        first.parse_id,
        expected_revision=task.revision,
    )

    with pytest.raises(TaskConflictError, match="changed from revision"):
        storage.attach_task_file_parse(
            task.task_id,
            "file-cas-two",
            second.parse_id,
            expected_revision=task.revision,
        )

    assert storage.load_task(task.task_id).revision == updated.revision
    assert storage.find_task_file_by_parse_id(second.parse_id) is None


@pytest.mark.parametrize("display_name", ["../secret.pdf", "C:\\secret.pdf", "folder/name.pdf"])
def test_task_file_rejects_filesystem_paths(display_name: str) -> None:
    with pytest.raises(ValueError, match="filesystem path"):
        TaskFile(
            display_name=display_name,
            source_file_type="application/pdf",
            source_size_bytes=1,
        )
