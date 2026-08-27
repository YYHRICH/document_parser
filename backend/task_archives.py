"""Verified task-level archive construction for the processing workbench."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from zipfile import ZipFile

from ..core.contracts import QualityState
from .delivery import delivery_eligibility
from .tasks import ProcessingTask, TaskFile, TaskFileProjection, TaskFileUserState

if TYPE_CHECKING:
    from .storage import ApiStorage


class TaskArchiveError(ValueError):
    """A requested workbench archive cannot be constructed from verified snapshots."""


class TaskArchiveKind(StrEnum):
    ORIGINAL = "original"
    OPTIMIZED = "optimized"


_ORIGINAL_ROOT_FILES = frozenset({"document.md", "parsed_document.json"})
_OPTIMIZED_ROOT_FILES = frozenset(
    {
        "optimized.md",
        "canonical_document.json",
        "quality_report.json",
        "package_manifest.json",
    }
)


def archive_availability(
    task_projection: object,
) -> dict[str, dict[str, object]]:
    """Return UI-safe counts from the task's conservative state projection.

    A final ZIP build revalidates all manifest and quality facts.  This helper is
    intentionally only an affordance for rendering a disabled/enabled menu.
    """

    files = list(getattr(task_projection, "files", ()) or ())
    available = sum(
        item.state == TaskFileUserState.AVAILABLE
        for item in files
    )
    return {
        TaskArchiveKind.ORIGINAL.value: {
            "available": available > 0,
            "count": available,
        },
        TaskArchiveKind.OPTIMIZED.value: {
            "available": available > 0,
            "count": available,
        },
    }


def write_task_archive(
    storage: "ApiStorage",
    task: ProcessingTask,
    task_projection: object,
    kind: TaskArchiveKind | str,
    archive: ZipFile,
) -> dict[str, object]:
    """Write one exact, verified archive to an already-open ZIP file.

    Each selectable member is read from an immutable manifest snapshot. A member
    that is not in the available state is described in the root manifest but is
    never emitted. Optimized members include ``quality_report.json`` so their
    downstream quality guidance is delivered with the content. A selected member
    with a changed/unsafe package aborts the whole archive rather than silently
    exporting a partial unverified result.
    """

    try:
        archive_kind = TaskArchiveKind(kind)
    except ValueError as error:
        raise TaskArchiveError("Unknown task archive kind.") from error
    projections = {
        item.task_file_id: item
        for item in (getattr(task_projection, "files", ()) or ())
    }
    included: list[dict[str, object]] = []
    omitted: list[dict[str, object]] = []
    for task_file in task.files:
        projection = projections.get(task_file.task_file_id)
        if projection is None or projection.state != TaskFileUserState.AVAILABLE:
            omitted.append(_omitted_payload(task_file, projection))
            continue
        try:
            member = _member_snapshot(storage, task_file, projection, archive_kind)
        except Exception as error:
            raise TaskArchiveError("A selected document archive cannot be verified.") from error
        prefix = f"{task_file.task_file_id}/"
        for relative_path, content in member["files"].items():
            archive.writestr(prefix + relative_path, content)
        archive.writestr(
            prefix + ("parse_manifest.json" if archive_kind == TaskArchiveKind.ORIGINAL else "delivery_manifest.json"),
            _json_bytes(member["manifest"]),
        )
        included.append(member["summary"])

    if not included:
        raise TaskArchiveError("There are no verified documents available for this archive.")
    manifest = {
        "schema_name": "TaskArchiveManifest",
        "schema_version": "1.0",
        "task_id": task.task_id,
        "archive_kind": archive_kind.value,
        "generated_at": datetime.now(UTC).isoformat(),
        "included": included,
        "omitted": omitted,
    }
    archive.writestr("archive_manifest.json", _json_bytes(manifest))
    return manifest


def _member_snapshot(
    storage: "ApiStorage",
    task_file: TaskFile,
    projection: TaskFileProjection,
    kind: TaskArchiveKind,
) -> dict[str, object]:
    parse_id = task_file.active_parse_id
    if parse_id is None or projection.active_parse_id != parse_id:
        raise TaskArchiveError("Task file has no stable active parse.")
    job = storage.load_job(parse_id)
    document = storage.load_document(parse_id)
    quality_package = storage.load_quality_package(parse_id)
    eligibility = delivery_eligibility(quality_package.quality_report.state)
    if not eligibility.allowed:
        raise TaskArchiveError("Quality policy does not allow this archive member.")

    if kind == TaskArchiveKind.ORIGINAL:
        paths = set(_ORIGINAL_ROOT_FILES)
        member_kind = "original_parse"
    else:
        paths = set(_OPTIMIZED_ROOT_FILES)
        member_kind = "optimized_delivery"
    paths.update(_asset_paths(document))
    snapshot = _read_package_snapshot(storage, parse_id, paths)
    quality_state = quality_package.quality_report.state.value
    source = {
        "schema_name": "TaskArchiveMemberManifest",
        "schema_version": "1.0",
        "task_file_id": task_file.task_file_id,
        "parse_id": parse_id,
        "document_id": str(document.document_id),
        "archive_member_kind": member_kind,
        "source_file_type": task_file.source_file_type,
        "source_size_bytes": task_file.source_size_bytes,
        "parser_id": job.requested_parser_id,
        "quality_state": quality_state,
        "files": {
            relative_path: {
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
            for relative_path, content in sorted(snapshot.items())
        },
    }
    return {
        "files": snapshot,
        "manifest": source,
        "summary": {
            "task_file_id": task_file.task_file_id,
            "parse_id": parse_id,
            "document_id": str(document.document_id),
            "quality_state": quality_state,
            "file_count": len(snapshot),
        },
    }


def _read_package_snapshot(
    storage: "ApiStorage",
    parse_id: str,
    paths: set[str],
) -> dict[str, bytes]:
    package_root = storage.package_root(parse_id)
    entries = dict(
        storage.iter_manifest_entries(
            package_root,
            require_manifest=True,
            expected_parse_id=parse_id,
        )
    )
    missing = paths - set(entries)
    if missing:
        raise TaskArchiveError("A required archive artifact is unavailable.")
    snapshot: dict[str, bytes] = {}
    for relative_path in sorted(paths):
        path = package_root / relative_path
        if path.is_symlink() or not path.is_file():
            raise TaskArchiveError("A selected archive artifact is unsafe.")
        content = path.read_bytes()
        metadata = entries[relative_path]
        if (
            len(content) != metadata.get("size_bytes")
            or hashlib.sha256(content).hexdigest() != metadata.get("sha256")
        ):
            raise TaskArchiveError("A selected archive artifact changed during verification.")
        snapshot[relative_path] = content
    if dict(
        storage.iter_manifest_entries(
            package_root,
            require_manifest=True,
            expected_parse_id=parse_id,
        )
    ) != entries:
        raise TaskArchiveError("The published package changed during archive construction.")
    return snapshot


def _asset_paths(document: object) -> set[str]:
    result: set[str] = set()
    for asset in getattr(document, "assets", ()) or ():
        path = getattr(asset, "path", None)
        if isinstance(path, str) and path:
            result.add("assets/" + path)
    return result


def _omitted_payload(
    task_file: TaskFile,
    projection: TaskFileProjection | None,
) -> dict[str, object]:
    state = projection.state.value if projection is not None else "failed"
    return {
        "task_file_id": task_file.task_file_id,
        "state": state,
        "reason": {
            "processing": "Document processing is not complete.",
            "needs_review": "Document processing requires further action.",
            "failed": "Document processing did not produce a downloadable result.",
        }.get(state, "Document is not available for download."),
    }


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
