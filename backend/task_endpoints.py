"""HTTP adapter for the durable processing-task workbench."""

from __future__ import annotations

import hashlib
import os
import tempfile
import zipfile
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ..orchestration import JobConflictError, ParseJobStatus
from .schemas import ReparseRequest
from .storage import ApiStorage, SourceIntegrityError
from .task_archives import TaskArchiveError, TaskArchiveKind, archive_availability, write_task_archive
from .tasks import ProcessingTask, TaskConflictError, TaskFile, TaskFileProjection


CreateJobFromUpload = Callable[..., Awaitable[object]]
ValidateOptions = Callable[[dict[str, Any]], dict[str, object]]
ValidateIdempotencyKey = Callable[[str | None], str | None]


def build_task_router(
    *,
    storage: ApiStorage,
    task_queue: object,
    create_job_from_upload: CreateJobFromUpload,
    validate_options: ValidateOptions,
    validate_idempotency_key: ValidateIdempotencyKey,
    max_task_files: int,
) -> APIRouter:
    """Build routes without making routing/quality/parser modules depend on HTTP."""

    router = APIRouter(prefix="/api/tasks", tags=["processing-tasks"])

    def task_payload(task_id: str) -> dict[str, object]:
        projection = storage.project_task(task_id)
        payload = projection.model_dump(mode="json")
        aggregate = payload["aggregate"]
        payload["counts"] = {
            "processing": aggregate["processing_count"],
            "needs_review": aggregate["needs_review_count"],
            "available": aggregate["available_count"],
            "failed": aggregate["failed_count"],
        }
        payload["downloads"] = archive_availability(projection)
        return payload

    def task_file_context(task_id: str, task_file_id: str) -> tuple[ProcessingTask, TaskFile, TaskFileProjection]:
        task = _load_task_or_404(storage, task_id)
        try:
            task_file = task.file_by_id(task_file_id)
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=404, detail="Task file not found.") from error
        projection = storage.project_task(task.task_id)
        for item in projection.files:
            if item.task_file_id == task_file.task_file_id:
                return task, task_file, item
        raise HTTPException(status_code=409, detail="Task file state cannot be verified.")

    @router.post("", status_code=status.HTTP_202_ACCEPTED)
    async def create_processing_task(
        files: Annotated[list[UploadFile], File()],
        parser_id: Annotated[str | None, Form()] = None,
        options_json: Annotated[str | None, Form()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict[str, object]:
        if not files:
            raise HTTPException(status_code=400, detail="Select at least one file.")
        if len(files) > max_task_files:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="The processing task exceeds the configured file-count limit.",
            )
        parent_key = validate_idempotency_key(idempotency_key)
        existing_jobs: list[object | None] = []
        is_replay = False
        if parent_key:
            existing_jobs = [
                storage.find_by_idempotency_key(_child_idempotency_key(parent_key, index))
                for index in range(len(files))
            ]
            any_existing = any(item is not None for item in existing_jobs)
            is_replay = any_existing and all(item is not None for item in existing_jobs)
            if any_existing and not is_replay:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The processing task request conflicts with an existing request.",
                )

        accepted: list[tuple[TaskFile, object, bool]] = []
        rejected: list[dict[str, str]] = []
        for index, upload in enumerate(files):
            child_key = _child_idempotency_key(parent_key, index) if parent_key else None
            prior = existing_jobs[index] if existing_jobs else None
            try:
                job = await create_job_from_upload(
                    file=upload,
                    parser_id=parser_id,
                    options_json=options_json,
                    idempotency_key=child_key,
                )
            except HTTPException as error:
                if prior is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="The processing task request conflicts with an existing request.",
                    ) from error
                rejected.append(
                    {
                        "display_name": _safe_display_name(upload.filename),
                        "reason": _safe_upload_rejection(error.status_code),
                    }
                )
                continue
            task_file = TaskFile(
                display_name=_safe_display_name(getattr(job, "source_filename", upload.filename)),
                source_file_type=str(getattr(job, "source_file_type", "application/octet-stream")),
                source_size_bytes=int(getattr(job, "source_size_bytes", 0)),
            ).attach_initial_parse(str(getattr(job, "parse_id")))
            accepted.append((task_file, job, prior is not None))

        if not accepted:
            raise HTTPException(status_code=400, detail="None of the selected files could be accepted.")

        if is_replay:
            locations = [storage.find_task_file_by_parse_id(item.active_parse_id or "") for item, _, _ in accepted]
            task_ids = {item.task_id for item in locations if item is not None}
            if len(task_ids) == 1 and all(item is not None for item in locations):
                existing_task_id = next(iter(task_ids))
                existing_task = storage.load_task(existing_task_id)
                if len(existing_task.files) != len(files):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="The processing task request conflicts with an existing request.",
                    )
                return {
                    "task_id": existing_task_id,
                    "status_url": f"/api/tasks/{existing_task_id}",
                    "task": task_payload(existing_task_id),
                    "rejected_files": rejected,
                }
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The processing task request conflicts with an incomplete existing request.",
            )

        task = ProcessingTask(
            task_id=storage.new_task_id(),
            files=[item for item, _, _ in accepted],
        )
        try:
            storage.create_task(task)
        except (FileExistsError, ValueError, TaskConflictError) as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The processing task could not be created.",
            ) from error
        for _, job, existed in accepted:
            if not existed and not getattr(job, "status").terminal:
                task_queue.submit(getattr(job, "parse_id"))
        return {
            "task_id": task.task_id,
            "status_url": f"/api/tasks/{task.task_id}",
            "task": task_payload(task.task_id),
            "rejected_files": rejected,
        }

    @router.get("/{task_id}")
    def get_processing_task(task_id: str) -> dict[str, object]:
        _load_task_or_404(storage, task_id)
        return {"task": task_payload(task_id)}

    @router.get("/{task_id}/events")
    def get_processing_task_events(task_id: str) -> dict[str, object]:
        task = _load_task_or_404(storage, task_id)
        events: list[dict[str, object]] = []
        for task_file in task.files:
            if task_file.active_parse_id is None:
                continue
            try:
                job = storage.load_job(task_file.active_parse_id)
            except (FileNotFoundError, ValueError):
                continue
            for event in job.events[-24:]:
                events.append(
                    {
                        "task_file_id": task_file.task_file_id,
                        "status": event.status.value,
                        "occurred_at": event.occurred_at,
                    }
                )
        events.sort(key=lambda item: str(item["occurred_at"]))
        return {"task_id": task.task_id, "task": task_payload(task.task_id), "events": events}

    @router.get("/{task_id}/files/{task_file_id}")
    def get_task_file_detail(task_id: str, task_file_id: str) -> dict[str, object]:
        task, task_file, projection = task_file_context(task_id, task_file_id)
        payload = _task_file_payload(task, task_file, projection)
        parse_id = task_file.active_parse_id
        if parse_id is None:
            return payload
        try:
            document = storage.load_document(parse_id)
        except Exception:
            return payload
        payload["preview_urls"] = {
            "optimized": f"/api/tasks/{task.task_id}/files/{task_file.task_file_id}/preview?view=optimized",
            "original": f"/api/tasks/{task.task_id}/files/{task_file.task_file_id}/preview?view=original",
        }
        try:
            quality_package = storage.load_quality_package(parse_id)
        except Exception:
            return payload
        payload["changes"] = _repair_changes(document, quality_package)
        payload["issues"] = _quality_issues(document, quality_package)
        payload["quality_summary"] = {
            "state": quality_package.quality_report.state.value,
            "applied_repair_count": len(quality_package.quality_report.applied_repairs),
            "issue_count": len(quality_package.quality_report.issues),
        }
        return payload

    @router.get("/{task_id}/files/{task_file_id}/preview")
    def get_task_file_preview(
        task_id: str,
        task_file_id: str,
        view: str = "optimized",
    ) -> dict[str, object]:
        task, task_file, projection = task_file_context(task_id, task_file_id)
        parse_id = task_file.active_parse_id
        if parse_id is None or projection.state.value == "processing":
            raise HTTPException(status_code=409, detail="Document preview is not ready.")
        if view not in {"optimized", "original"}:
            raise HTTPException(status_code=400, detail="Unknown document preview.")
        try:
            document = storage.load_document(parse_id)
            quality_package = None
            markdown = document.markdown
            if view == "optimized":
                quality_package = storage.load_quality_package(parse_id)
                markdown = quality_package.optimized_markdown
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Document preview is not available.") from error
        except Exception as error:
            raise HTTPException(status_code=409, detail="Document preview cannot be verified.") from error
        return {
            "task_id": task.task_id,
            "task_file_id": task_file.task_file_id,
            "view": view,
            "markdown": markdown,
            # The line is calculated against the exact selected representation;
            # the frontend can therefore locate an applied repair without text guessing.
            "anchors": _document_anchors(
                document,
                markdown=markdown,
                content_by_block_id=_quality_block_contents(document, quality_package),
            ),
        }

    @router.post("/{task_id}/files/{task_file_id}/retry", status_code=status.HTTP_202_ACCEPTED)
    def retry_task_file(
        task_id: str,
        task_file_id: str,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict[str, object]:
        task, task_file, _ = task_file_context(task_id, task_file_id)
        if task_file.active_parse_id is None:
            raise HTTPException(status_code=409, detail="This task file has no retryable parse.")
        request_key = validate_idempotency_key(idempotency_key)
        try:
            replay = _find_task_action_replay(
                storage,
                task_file,
                request_key,
                action="retry",
            )
            if replay is not None:
                return _task_action_payload(task, task_file, replay.parse_id, task_payload)
            result = storage.create_retry_job(
                parent_parse_id=task_file.active_parse_id,
                idempotency_key=request_key,
            )
            _switch_task_file(storage, task, task_file, result.job.parse_id)
        except (FileNotFoundError, SourceIntegrityError) as error:
            raise HTTPException(status_code=409, detail="The stored source cannot be verified for retry.") from error
        except (ValueError, JobConflictError, TaskConflictError) as error:
            raise HTTPException(status_code=409, detail="The retry request cannot be accepted.") from error
        if result.created and not result.job.status.terminal:
            task_queue.submit(result.job.parse_id)
        return _task_action_payload(task, task_file, result.job.parse_id, task_payload)

    @router.post("/{task_id}/files/{task_file_id}/reparse", status_code=status.HTTP_202_ACCEPTED)
    def reparse_task_file(
        task_id: str,
        task_file_id: str,
        body: ReparseRequest,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict[str, object]:
        task, task_file, _ = task_file_context(task_id, task_file_id)
        if task_file.active_parse_id is None:
            raise HTTPException(status_code=409, detail="This task file has no source for reprocessing.")
        options = validate_options(dict(body.options))
        request_key = validate_idempotency_key(idempotency_key)
        try:
            replay = _find_task_action_replay(
                storage,
                task_file,
                request_key,
                action="reparse",
                requested_parser_id=body.parser_id,
                options=options,
            )
            if replay is not None:
                return _task_action_payload(task, task_file, replay.parse_id, task_payload)
            result = storage.create_reparse_job(
                parent_parse_id=task_file.active_parse_id,
                requested_parser_id=body.parser_id,
                options=options,
                idempotency_key=request_key,
            )
            _switch_task_file(storage, task, task_file, result.job.parse_id)
        except (FileNotFoundError, SourceIntegrityError) as error:
            raise HTTPException(status_code=409, detail="The stored source cannot be verified for reprocessing.") from error
        except (ValueError, JobConflictError, TaskConflictError) as error:
            raise HTTPException(status_code=409, detail="The reprocessing request cannot be accepted.") from error
        if result.created and not result.job.status.terminal:
            task_queue.submit(result.job.parse_id)
        return _task_action_payload(task, task_file, result.job.parse_id, task_payload)

    @router.get("/{task_id}/downloads/{kind}")
    def download_task_archive(task_id: str, kind: str) -> FileResponse:
        task = _load_task_or_404(storage, task_id)
        try:
            archive_kind = TaskArchiveKind(kind)
        except ValueError as error:
            raise HTTPException(status_code=404, detail="Download package not found.") from error
        archive_fd, archive_name = tempfile.mkstemp(prefix=f"task-{task.task_id}-{archive_kind.value}-", suffix=".zip")
        os.close(archive_fd)
        archive_path = Path(archive_name)
        try:
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                write_task_archive(storage, task, storage.project_task(task.task_id), archive_kind, archive)
        except TaskArchiveError as error:
            archive_path.unlink(missing_ok=True)
            raise HTTPException(status_code=409, detail="The requested download cannot be verified.") from error
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise
        label = "original-parse" if archive_kind == TaskArchiveKind.ORIGINAL else "optimized-documents"
        return FileResponse(
            archive_path,
            media_type="application/zip",
            filename=f"{label}-{task.task_id}.zip",
            background=BackgroundTask(_remove_temp_file, archive_path),
        )

    return router


def _load_task_or_404(storage: ApiStorage, task_id: str) -> ProcessingTask:
    try:
        return storage.load_task(task_id)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=404, detail="Processing task not found.") from error


def _task_file_payload(task: ProcessingTask, task_file: TaskFile, projection: TaskFileProjection) -> dict[str, object]:
    payload = projection.model_dump(mode="json")
    payload.update(
        {
            "task_id": task.task_id,
            "task_file_id": task_file.task_file_id,
            "active_parse_id": task_file.active_parse_id,
            "current_parse_id": task_file.active_parse_id,
            "parse_history": list(task_file.parse_history),
            "allowed_actions": _allowed_actions(projection),
            "changes": [],
            "issues": [],
            "preview_urls": {},
        }
    )
    return payload


def _allowed_actions(projection: TaskFileProjection) -> list[str]:
    actions = ["view"]
    if projection.retryable:
        actions.append("retry")
    if projection.active_parse_id is not None:
        actions.append("reparse")
    return actions


_REPAIR_TITLES = {
    "QL-RPR-001": "清理非语义行尾空白",
    "QL-RPR-002": "对齐 Markdown 表格分隔线",
    "QL-RPR-003": "规范化 HTML 表格",
}


def _repair_description(rule_id: str, parameters: object) -> str:
    values = parameters if isinstance(parameters, dict) else {}
    if rule_id == "QL-RPR-001":
        count = values.get("line_count")
        if isinstance(count, int) and count > 0:
            return f"清理 {count} 行非语义行尾空白，保留 Markdown 硬换行和围栏代码内容。"
        return "清理非语义行尾空白，保留 Markdown 硬换行和围栏代码内容。"
    if rule_id == "QL-RPR-002":
        count = len(values.get("line_indices", ())) if isinstance(values.get("line_indices"), list) else 0
        if count:
            return f"修复 {count} 个 Markdown 表格分隔行，使列数与表头一致。"
        return "修复 Markdown 表格分隔行，使列数与表头一致。"
    if rule_id == "QL-RPR-003":
        table_id = values.get("table_id")
        if isinstance(table_id, str) and table_id:
            return f"将表格 {table_id} 从安全的 HTML 结构转换为 Markdown 表格，并保留原文证据。"
        count = values.get("table_count")
        if isinstance(count, int) and count > 0:
            return f"将 {count} 个安全的 HTML 表格转换为 Markdown 表格，并保留原文证据。"
        return "将安全的 HTML 表格转换为 Markdown 表格，并保留原文证据。"
    return "按质量层白名单规则完成确定性格式整理。"


def _quality_block_contents(document: object, quality_package: object) -> dict[str, str]:
    """Map original ParsedDocument block UUIDs to optimized block Markdown."""
    if quality_package is None:
        return {}
    canonical = getattr(quality_package, "canonical_document", None)
    canonical_blocks = list(getattr(canonical, "blocks", ()) or ())
    by_source = {
        str(getattr(getattr(item, "source_locator", None), "source_block_id", "")): str(getattr(item, "content", ""))
        for item in canonical_blocks
        if getattr(getattr(item, "source_locator", None), "source_block_id", None)
    }
    by_order = {
        getattr(item, "order_index", None): str(getattr(item, "content", ""))
        for item in canonical_blocks
        if getattr(item, "order_index", None) is not None
    }
    result: dict[str, str] = {}
    for block in getattr(document, "blocks", ()) or ():
        block_id = str(getattr(block, "id", ""))
        source_id = str(getattr(block, "source_block_id", "") or "")
        content = by_source.get(source_id) if source_id else None
        if not content:
            content = by_order.get(getattr(block, "order_index", None))
        if content:
            result[block_id] = content
    return result


def _repair_changes(document: object, quality_package: object) -> list[dict[str, object]]:
    block_pages = {
        str(block.id): getattr(getattr(block, "anchor", None), "page_number", None)
        for block in getattr(document, "blocks", ()) or ()
    }
    result: list[dict[str, object]] = []
    seen: dict[tuple[object, ...], dict[str, object]] = {}
    report = getattr(quality_package, "quality_report", None)
    for repair in getattr(report, "applied_repairs", ()) or ():
        rule_id = str(getattr(repair, "rule_id", ""))
        evidence = getattr(repair, "evidence", {}) or {}
        raw_parameters = evidence.get("parameters", {}) if isinstance(evidence, dict) else {}
        parameters = raw_parameters if isinstance(raw_parameters, dict) else {}
        affected = list(dict.fromkeys(str(item) for item in (getattr(repair, "affected_block_ids", ()) or ())))
        before = _safe_text(evidence.get("before") if isinstance(evidence, dict) else "", 600)
        after = _safe_text(evidence.get("after") if isinstance(evidence, dict) else "", 600)
        # A document-level and a block-level execution can describe the same
        # semantic repair with different surrounding before/after text.  The
        # stable rule and affected blocks are the user-facing identity here.
        dedupe_key = (rule_id, tuple(sorted(affected)), str(parameters.get("table_id", "")))
        existing = seen.get(dedupe_key)
        if existing is not None:
            existing["duplicate_count"] = int(existing.get("duplicate_count", 1)) + 1
            continue
        pages = sorted({block_pages.get(block_id) for block_id in affected if block_pages.get(block_id) is not None})
        page_label = "、".join(f"第 {page} 页" for page in pages) or ("相关内容" if affected else "文档内容")
        location = f"{page_label} · {len(affected)} 个正文位置" if affected else page_label
        record = {
            "id": str(getattr(repair, "repair_id", "")),
            "rule_id": rule_id,
            "title": _REPAIR_TITLES.get(rule_id, "自动整理文档格式"),
            "description": _repair_description(rule_id, parameters),
            "state": "applied",
            "status_label": "已自动修复",
            "location": location,
            "page_numbers": pages,
            "affected_block_ids": affected,
            "anchor_ids": affected,
            # This identifier comes directly from the applied repair target and
            # can be matched against preview anchors without guessing from text.
            "block_id": affected[0] if affected else None,
            "before": before,
            "after": after,
            "evidence_summary": "已记录修改前后内容，并完成目标哈希校验。",
            "evidence_complete": bool(isinstance(evidence, dict) and isinstance(evidence.get("before"), str) and isinstance(evidence.get("after"), str)),
            "duplicate_count": 1,
        }
        seen[dedupe_key] = record
        result.append(record)
    return result


def _quality_issues(document: object, quality_package: object) -> list[dict[str, object]]:
    block_pages = {
        str(block.id): getattr(getattr(block, "anchor", None), "page_number", None)
        for block in getattr(document, "blocks", ()) or ()
    }
    result: list[dict[str, object]] = []
    report = getattr(quality_package, "quality_report", None)
    for issue in getattr(report, "issues", ()) or ():
        affected = list(getattr(issue, "affected_block_ids", ()) or ())
        pages = sorted({block_pages.get(str(block_id)) for block_id in affected if block_pages.get(str(block_id)) is not None})
        result.append(
            {
                "id": str(getattr(issue, "issue_id", "")),
                "severity": str(getattr(getattr(issue, "severity", None), "value", "info")),
                "category": _safe_text(getattr(issue, "category", ""), 80),
                "status": str(getattr(getattr(issue, "status", None), "value", "")),
                "message": _safe_text(getattr(issue, "message", ""), 360),
                "affected_block_ids": [str(item) for item in affected],
                "pages": pages,
            }
        )
    return result


def _document_anchors(
    document: object,
    *,
    markdown: str | None = None,
    content_by_block_id: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    """Expose page and exact line anchors for the selected preview representation."""
    anchors: list[dict[str, object]] = []
    searchable = (markdown or "").replace("\r\n", "\n").replace("\r", "\n")
    cursor = 0
    content_by_block_id = content_by_block_id or {}
    for block in getattr(document, "blocks", ()) or ():
        block_id = str(getattr(block, "id", ""))
        content = content_by_block_id.get(block_id) or str(getattr(block, "markdown", "") or "")
        if not content:
            content = str(getattr(block, "text", "") or "")
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        start = searchable.find(content, cursor) if content and searchable else -1
        if start < 0 and content and searchable:
            start = searchable.find(content)
        entry = {
            "block_id": block_id,
            "page_number": getattr(getattr(block, "anchor", None), "page_number", None),
            "kind": str(getattr(getattr(block, "kind", None), "value", getattr(block, "kind", "paragraph"))),
        }
        if start >= 0:
            entry["line"] = searchable.count("\n", 0, start) + 1
            entry["start_line"] = entry["line"]
            cursor = max(cursor, start + len(content))
        anchors.append(entry)
    return anchors


def _task_action_payload(
    task: ProcessingTask,
    task_file: TaskFile,
    parse_id: str,
    task_payload: Callable[[str], dict[str, object]],
) -> dict[str, object]:
    return {
        "task_id": task.task_id,
        "task_file_id": task_file.task_file_id,
        "parse_id": parse_id,
        "task": task_payload(task.task_id),
    }


def _find_task_action_replay(
    storage: ApiStorage,
    task_file: TaskFile,
    idempotency_key: str | None,
    *,
    action: str,
    requested_parser_id: str | None = None,
    options: dict[str, object] | None = None,
) -> object | None:
    """Return only a same-file replay with the same action semantics.

    A task file advances to the new child parse after the first request.  Looking
    up the global key before creating another child preserves retry/reparse
    idempotency even after that active-pointer switch.
    """

    if idempotency_key is None:
        return None
    existing = storage.find_by_idempotency_key(idempotency_key)
    if existing is None:
        return None
    parent_parse_id = existing.parent_parse_id
    if (
        existing.parse_id not in task_file.parse_history
        or parent_parse_id is None
        or parent_parse_id not in task_file.parse_history
    ):
        raise TaskConflictError("Idempotency key is bound to a different task-file action.")
    if action == "retry":
        parent = storage.load_job(parent_parse_id)
        same_action = (
            existing.requested_parser_id == parent.requested_parser_id
            and existing.options == parent.options
        )
    elif action == "reparse":
        same_action = (
            existing.requested_parser_id == requested_parser_id
            and existing.options == (options or {})
        )
    else:
        raise ValueError("Unknown task-file action.")
    if not same_action:
        raise TaskConflictError("Idempotency key is bound to a different task-file action.")
    return existing


def _switch_task_file(storage: ApiStorage, task: ProcessingTask, task_file: TaskFile, parse_id: str) -> None:
    try:
        storage.switch_task_file_active_parse(
            task.task_id,
            task_file.task_file_id,
            parse_id,
            expected_revision=task.revision,
        )
        return
    except TaskConflictError:
        latest = storage.load_task(task.task_id)
        latest_file = latest.file_by_id(task_file.task_file_id)
        if latest_file.active_parse_id == parse_id:
            return
        raise


def _child_idempotency_key(parent_key: str, index: int) -> str:
    return hashlib.sha256(f"processing-task:{parent_key}:{index}".encode("utf-8")).hexdigest()


def _safe_display_name(value: object) -> str:
    raw = str(value or "upload.bin").replace("\\", "/")
    name = raw.rsplit("/", 1)[-1].strip()
    if not name or name in {".", ".."}:
        return "upload.bin"
    return name[:255]


def _safe_upload_rejection(status_code: int) -> str:
    if status_code == status.HTTP_413_CONTENT_TOO_LARGE:
        return "文件超过当前可处理大小。"
    if status_code == status.HTTP_400_BAD_REQUEST:
        return "文件格式或内容无法处理。"
    return "文件暂时无法受理。"


def _safe_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else normalized[: max(0, limit - 1)] + "…"


def _remove_temp_file(path: Path) -> None:
    path.unlink(missing_ok=True)
