"""Filesystem-backed storage for durable parse jobs and verified artifact packages."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from threading import RLock
from typing import Any, Iterable
from uuid import UUID, uuid4

from ..core import load_document_package, write_document_package
from ..core.contracts import ParseRequest, ParsedDocument, QualityPackage
from ..orchestration.models import JobConflictError, ParseJob, ParseJobStatus
from .tasks import (
    ProcessingTask,
    TaskConflictError,
    TaskFile,
    TaskFileLocation,
    TaskProjection,
    aggregate_task,
)
from quality.packaging.artifacts import (
    QUALITY_PACKAGE_ARTIFACTS,
    build_package_artifacts,
    verify_package_files,
)


_ARTIFACT_MANIFEST_NAME = "artifact_manifest.json"
_REVISION_NAME = "revision.json"
_ATOMIC_REPLACE_ATTEMPTS = 5
_ATOMIC_REPLACE_INITIAL_DELAY_SECONDS = 0.02
_LOCK_TIMEOUT_SECONDS = 5.0
_LOCK_POLL_SECONDS = 0.02
_LOCK_STALE_SECONDS = 300.0
_JOB_SAVE_LOCK = RLock()
_TASK_SAVE_LOCK = RLock()


class ArtifactManifestError(ValueError):
    """A published package is missing, contains, or disagrees with its manifest."""


class SourceIntegrityError(ValueError):
    """Persisted source bytes or a parsed document do not match the owning job."""


@dataclass(frozen=True)
class JobCreationResult:
    """Outcome of an idempotent job creation transaction.

    API callers enqueue only when ``created`` is true, so replaying an idempotent
    request never schedules an already-running or terminal child a second time.
    """

    job: ParseJob
    created: bool


class ApiStorage:
    """Filesystem implementation of the job repository and verified artifact store.

    ``.jobs`` holds the control plane and immutable original upload. A completed
    package is assembled below ``.staging`` and only published after its document,
    source, quality result, revision record, and exact artifact manifest agree.
    """

    def __init__(self, root: Path | str = Path("outputs/api")) -> None:
        self.root = Path(root)

    @property
    def jobs_root(self) -> Path:
        return self.root / ".jobs"

    @property
    def staging_root(self) -> Path:
        return self.root / ".staging"

    @property
    def locks_root(self) -> Path:
        return self.jobs_root / ".locks"

    def _job_lock_path(self, parse_id: str) -> Path:
        return self.locks_root / f"{self._validate_parse_id(parse_id)}.lock"

    @property
    def _creation_lock_path(self) -> Path:
        return self.locks_root / "creation.lock"

    def new_parse_id(self) -> str:
        while True:
            parse_id = uuid4().hex
            if not self.package_root(parse_id).exists() and not self.job_root(parse_id).exists():
                return parse_id

    def package_root(self, parse_id: str) -> Path:
        return self.root / self._validate_parse_id(parse_id)

    def job_root(self, parse_id: str) -> Path:
        return self.jobs_root / self._validate_parse_id(parse_id)

    def job_path(self, parse_id: str) -> Path:
        return self.job_root(parse_id) / "job.json"

    @property
    def tasks_root(self) -> Path:
        """Control-plane root for durable user-visible processing tasks."""

        return self.root / ".tasks"

    @property
    def task_locks_root(self) -> Path:
        return self.tasks_root / ".locks"

    @property
    def task_parse_index_path(self) -> Path:
        """Private reverse index of parse id to task/file identity."""

        return self.tasks_root / "parse_index.json"

    def _task_lock_path(self, task_id: str) -> Path:
        return self.task_locks_root / f"{self._validate_task_id(task_id)}.lock"

    @property
    def _task_index_lock_path(self) -> Path:
        return self.task_locks_root / "parse-index.lock"

    def new_task_id(self) -> str:
        """Return a new opaque task identifier without exposing a filesystem path."""

        while True:
            task_id = uuid4().hex
            if not self.task_root(task_id).exists():
                return task_id

    def task_root(self, task_id: str) -> Path:
        return self.tasks_root / self._validate_task_id(task_id)

    def task_path(self, task_id: str) -> Path:
        return self.task_root(task_id) / "task.json"

    def create_task(self, task: ProcessingTask) -> ProcessingTask:
        """Persist a 1/N-file task and its parse associations at revision zero.

        The task contains logical files only.  A file without ``active_parse_id`` is
        allowed while a multi-file upload is being partially accepted; callers attach
        each successfully-created child ParseJob through ``attach_task_file_parse``.
        """

        task_path = self.task_path(task.task_id)
        with _TASK_SAVE_LOCK, _exclusive_file_lock(self._task_index_lock_path):
            if task_path.parent.exists():
                raise FileExistsError(f"Processing task already exists: {task.task_id}")
            index = self._load_task_parse_index_locked()
            for task_file in task.files:
                for parse_id in task_file.parse_history:
                    existing = self._resolve_task_file_location_locked(parse_id, index)
                    if existing is not None:
                        raise ValueError(
                            f"Parse job {parse_id} is already associated with a processing task."
                        )
                    self._validate_parse_for_task_file(task_file, self.load_job(parse_id))
            task_path.parent.mkdir(parents=True, exist_ok=False)
            stored = task.model_copy(update={"updated_at": datetime.now(UTC)})
            self._write_text_atomic(task_path, stored.model_dump_json(indent=2))
            for task_file in stored.files:
                for parse_id in task_file.parse_history:
                    index[parse_id] = TaskFileLocation(
                        task_id=stored.task_id,
                        task_file_id=task_file.task_file_id,
                    )
            self._write_task_parse_index_locked(index)
        return stored

    def load_task(self, task_id: str) -> ProcessingTask:
        """Read one complete task control record under its writer lock."""

        normalized_task_id = self._validate_task_id(task_id)
        path = self.task_path(normalized_task_id)
        if not path.parent.is_dir():
            raise FileNotFoundError(normalized_task_id)
        with _TASK_SAVE_LOCK, _exclusive_file_lock(self._task_lock_path(normalized_task_id)):
            if not path.is_file():
                raise FileNotFoundError(normalized_task_id)
            return ProcessingTask.model_validate_json(path.read_text(encoding="utf-8"))

    def list_tasks(self) -> tuple[ProcessingTask, ...]:
        """Return durable task records sorted by creation time; no paths are projected."""

        if not self.tasks_root.is_dir():
            return ()
        tasks: list[ProcessingTask] = []
        for path in self.tasks_root.glob("*/task.json"):
            try:
                tasks.append(self.load_task(path.parent.name))
            except Exception:
                continue
        return tuple(sorted(tasks, key=lambda item: item.created_at))

    def load_task_file(self, task_id: str, task_file_id: str) -> TaskFile:
        return self.load_task(task_id).file_by_id(task_file_id)

    def attach_task_file_parse(
        self,
        task_id: str,
        task_file_id: str,
        parse_id: str,
        *,
        expected_revision: int,
    ) -> ProcessingTask:
        """CAS-attach the first accepted ParseJob to a pending logical file."""

        normalized_task_id = self._validate_task_id(task_id)
        normalized_task_file_id = self._validate_task_file_id(task_file_id)
        normalized_parse_id = self._validate_parse_id(parse_id)
        parse_job = self.load_job(normalized_parse_id)
        with _TASK_SAVE_LOCK, _exclusive_file_lock(self._task_index_lock_path):
            index = self._load_task_parse_index_locked()
            existing = self._resolve_task_file_location_locked(normalized_parse_id, index)
            with _exclusive_file_lock(self._task_lock_path(normalized_task_id)):
                current = self._load_task_unlocked(normalized_task_id)
                self._require_task_revision(current, expected_revision)
                task_file = current.file_by_id(normalized_task_file_id)
                if task_file.active_parse_id == normalized_parse_id:
                    if existing is not None and existing != TaskFileLocation(
                        task_id=normalized_task_id,
                        task_file_id=normalized_task_file_id,
                    ):
                        raise TaskConflictError("Parse job belongs to a different task file.")
                    if existing is None:
                        index[normalized_parse_id] = TaskFileLocation(
                            task_id=normalized_task_id,
                            task_file_id=normalized_task_file_id,
                        )
                        self._write_task_parse_index_locked(index)
                    return current
                if task_file.active_parse_id is not None:
                    raise ValueError("Task file already has an active parse; use switch_task_file_active_parse.")
                if existing is not None:
                    raise TaskConflictError("Parse job is already associated with a task file.")
                self._validate_parse_for_task_file(task_file, parse_job)
                stored = self._save_task_unlocked(
                    current.replace_file(task_file.attach_initial_parse(normalized_parse_id))
                )
                index[normalized_parse_id] = TaskFileLocation(
                    task_id=normalized_task_id,
                    task_file_id=normalized_task_file_id,
                )
                self._write_task_parse_index_locked(index)
                return stored

    def switch_task_file_active_parse(
        self,
        task_id: str,
        task_file_id: str,
        parse_id: str,
        *,
        expected_revision: int,
    ) -> ProcessingTask:
        """CAS-switch a file to a same-source retry/reparse child while preserving history."""

        normalized_task_id = self._validate_task_id(task_id)
        normalized_task_file_id = self._validate_task_file_id(task_file_id)
        normalized_parse_id = self._validate_parse_id(parse_id)
        parse_job = self.load_job(normalized_parse_id)
        with _TASK_SAVE_LOCK, _exclusive_file_lock(self._task_index_lock_path):
            index = self._load_task_parse_index_locked()
            existing = self._resolve_task_file_location_locked(normalized_parse_id, index)
            with _exclusive_file_lock(self._task_lock_path(normalized_task_id)):
                current = self._load_task_unlocked(normalized_task_id)
                self._require_task_revision(current, expected_revision)
                task_file = current.file_by_id(normalized_task_file_id)
                expected_location = TaskFileLocation(
                    task_id=normalized_task_id,
                    task_file_id=normalized_task_file_id,
                )
                if existing is not None and existing != expected_location:
                    raise TaskConflictError("Parse job is already associated with a different task file.")
                if task_file.active_parse_id == normalized_parse_id:
                    if existing is None:
                        index[normalized_parse_id] = expected_location
                        self._write_task_parse_index_locked(index)
                    return current
                if task_file.active_parse_id is None:
                    if existing is not None:
                        raise TaskConflictError("Parse job is already associated with a task file.")
                    self._validate_parse_for_task_file(task_file, parse_job)
                    replacement = task_file.attach_initial_parse(normalized_parse_id)
                else:
                    active_job = self.load_job(task_file.active_parse_id)
                    self._validate_parse_for_task_file(task_file, parse_job)
                    if not self._same_source_identity(active_job, parse_job):
                        raise ValueError("The new active parse must have the same immutable source identity.")
                    replacement = task_file.activate_parse(normalized_parse_id)
                stored = self._save_task_unlocked(current.replace_file(replacement))
                index[normalized_parse_id] = expected_location
                self._write_task_parse_index_locked(index)
                return stored

    def find_task_file_by_parse_id(self, parse_id: str) -> TaskFileLocation | None:
        """Return an opaque reverse link; never return a task directory or source path."""

        normalized_parse_id = self._validate_parse_id(parse_id)
        with _TASK_SAVE_LOCK, _exclusive_file_lock(self._task_index_lock_path):
            index = self._load_task_parse_index_locked()
            location = self._resolve_task_file_location_locked(normalized_parse_id, index)
            if location is None:
                return None
            # A recovery scan may have repaired a missing/stale index entry.
            if index.get(normalized_parse_id) != location:
                index[normalized_parse_id] = location
                self._write_task_parse_index_locked(index)
            return location

    def project_task(self, task_id: str) -> TaskProjection:
        """Build the path-free processing-center view from task and current ParseJobs."""

        task = self.load_task(task_id)
        jobs: dict[str, ParseJob | None] = {}
        for task_file in task.files:
            parse_id = task_file.active_parse_id
            if parse_id is None:
                continue
            try:
                jobs[parse_id] = self.load_job(parse_id)
            except FileNotFoundError:
                jobs[parse_id] = None
        return aggregate_task(task, jobs)

    def _load_task_unlocked(self, task_id: str) -> ProcessingTask:
        path = self.task_path(task_id)
        if not path.is_file():
            raise FileNotFoundError(task_id)
        return ProcessingTask.model_validate_json(path.read_text(encoding="utf-8"))

    def _save_task_unlocked(self, task: ProcessingTask) -> ProcessingTask:
        path = self.task_path(task.task_id)
        current = self._load_task_unlocked(task.task_id)
        if current.revision != task.revision:
            raise TaskConflictError(
                f"Processing task {task.task_id} changed from revision {task.revision} "
                f"to {current.revision}; reload before saving."
            )
        stored = task.model_copy(
            update={
                "revision": task.revision + 1,
                "updated_at": datetime.now(UTC),
            }
        )
        self._write_text_atomic(path, stored.model_dump_json(indent=2))
        return stored

    @staticmethod
    def _require_task_revision(task: ProcessingTask, expected_revision: int) -> None:
        if expected_revision < 0 or task.revision != expected_revision:
            raise TaskConflictError(
                f"Processing task {task.task_id} changed from revision {expected_revision} "
                f"to {task.revision}; reload before saving."
            )

    def _load_task_parse_index_locked(self) -> dict[str, TaskFileLocation]:
        path = self.task_parse_index_path
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as error:
            raise ValueError("Processing task parse index is invalid.") from error
        if not isinstance(payload, dict) or payload.get("schema_name") != "TaskParseIndex":
            raise ValueError("Processing task parse index is invalid.")
        entries = payload.get("entries")
        if not isinstance(entries, dict):
            raise ValueError("Processing task parse index is invalid.")
        index: dict[str, TaskFileLocation] = {}
        for parse_id, raw_location in entries.items():
            normalized_parse_id = self._validate_parse_id(parse_id)
            index[normalized_parse_id] = TaskFileLocation.model_validate(raw_location)
        return index

    def _write_task_parse_index_locked(self, index: dict[str, TaskFileLocation]) -> None:
        payload = {
            "schema_name": "TaskParseIndex",
            "schema_version": "1.0",
            "entries": {
                parse_id: location.model_dump(mode="json")
                for parse_id, location in sorted(index.items())
            },
        }
        self._write_text_atomic(self.task_parse_index_path, _json_text(payload, sort_keys=True))

    def _resolve_task_file_location_locked(
        self,
        parse_id: str,
        index: dict[str, TaskFileLocation],
    ) -> TaskFileLocation | None:
        """Validate indexed links and recover a missing link by scanning task records."""

        indexed = index.get(parse_id)
        if indexed is not None:
            try:
                task = self.load_task(indexed.task_id)
                task_file = task.file_by_id(indexed.task_file_id)
            except (FileNotFoundError, KeyError, ValueError):
                indexed = None
            else:
                if parse_id in task_file.parse_history:
                    return indexed
        if not self.tasks_root.is_dir():
            return None
        matches: list[TaskFileLocation] = []
        for path in self.tasks_root.glob("*/task.json"):
            try:
                task = self.load_task(path.parent.name)
            except Exception:
                continue
            for task_file in task.files:
                if parse_id in task_file.parse_history:
                    matches.append(
                        TaskFileLocation(
                            task_id=task.task_id,
                            task_file_id=task_file.task_file_id,
                        )
                    )
        if len(matches) > 1:
            raise TaskConflictError("Parse job is associated with more than one task file.")
        return matches[0] if matches else None

    @staticmethod
    def _validate_parse_for_task_file(task_file: TaskFile, job: ParseJob) -> None:
        if (
            job.source_file_type != task_file.source_file_type
            or job.source_size_bytes != task_file.source_size_bytes
        ):
            raise ValueError("Parse job source metadata does not match the logical task file.")

    @staticmethod
    def _same_source_identity(left: ParseJob, right: ParseJob) -> bool:
        return (
            left.source_sha256 == right.source_sha256
            and left.source_size_bytes == right.source_size_bytes
            and left.source_file_type == right.source_file_type
        )

    def create_job(
        self,
        *,
        parse_id: str,
        source_filename: str,
        source_file_type: str,
        source_content: bytes,
        requested_parser_id: str | None,
        options: dict[str, object],
        parent_parse_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ParseJob:
        """Persist an immutable source file and an initial revision-zero job."""

        return self._create_job(
            parse_id=parse_id,
            source_filename=source_filename,
            source_file_type=source_file_type,
            source_content=source_content,
            requested_parser_id=requested_parser_id,
            options=options,
            parent_parse_id=parent_parse_id,
            idempotency_key=idempotency_key,
        ).job

    def create_retry_job(
        self,
        *,
        parent_parse_id: str,
        idempotency_key: str | None = None,
    ) -> JobCreationResult:
        """Create a retry child from a verified immutable source when policy allows it."""

        parent = self.load_job(parent_parse_id)
        parent.require_retryable()
        source_request = self.load_request(parent.parse_id)
        return self._create_job(
            parse_id=self.new_parse_id(),
            source_filename=source_request.filename,
            source_file_type=source_request.file_type,
            source_content=source_request.content,
            requested_parser_id=source_request.parser_id,
            options=dict(source_request.options),
            parent_parse_id=parent.parse_id,
            idempotency_key=idempotency_key,
        )

    def create_reparse_job(
        self,
        *,
        parent_parse_id: str,
        requested_parser_id: str | None,
        options: dict[str, object],
        idempotency_key: str | None = None,
    ) -> JobCreationResult:
        """Create a reparse child from a verified durable source without mutating its parent."""

        source_request = self.load_request(parent_parse_id)
        return self._create_job(
            parse_id=self.new_parse_id(),
            source_filename=source_request.filename,
            source_file_type=source_request.file_type,
            source_content=source_request.content,
            requested_parser_id=requested_parser_id,
            options=dict(options),
            parent_parse_id=parent_parse_id,
            idempotency_key=idempotency_key,
        )

    def _create_job(
        self,
        *,
        parse_id: str,
        source_filename: str,
        source_file_type: str,
        source_content: bytes,
        requested_parser_id: str | None,
        options: dict[str, object],
        parent_parse_id: str | None,
        idempotency_key: str | None,
    ) -> JobCreationResult:
        """Run the idempotency lookup and initial source/job write as one transaction."""

        source_sha256 = hashlib.sha256(source_content).hexdigest()
        with _exclusive_file_lock(self._creation_lock_path):
            if idempotency_key:
                existing = self.find_by_idempotency_key(idempotency_key)
                if existing is not None:
                    same_request = (
                        existing.source_sha256 == source_sha256
                        and existing.source_filename == source_filename
                        and existing.source_file_type == source_file_type
                        and existing.requested_parser_id == requested_parser_id
                        and existing.options == options
                        and existing.parent_parse_id == parent_parse_id
                    )
                    if not same_request:
                        raise ValueError("Idempotency-Key is already bound to a different parse request.")
                    return JobCreationResult(job=existing, created=False)

            job_root = self.job_root(parse_id)
            if job_root.exists() or self.package_root(parse_id).exists():
                raise FileExistsError(f"Parse job already exists: {parse_id}")
            job = ParseJob(
                parse_id=parse_id,
                source_sha256=source_sha256,
                source_filename=source_filename,
                source_file_type=source_file_type,
                source_size_bytes=len(source_content),
                requested_parser_id=requested_parser_id,
                options=dict(options),
                parent_parse_id=parent_parse_id,
                idempotency_key=idempotency_key,
            )
            source_path = self.job_source_path(parse_id, filename=source_filename)
            source_path.parent.mkdir(parents=True, exist_ok=False)
            self._write_bytes_atomic(source_path, source_content)
            return JobCreationResult(job=self.save_job(job), created=True)

    def load_job(self, parse_id: str) -> ParseJob:
        return self._load_job_locked(parse_id)

    def _load_job_locked(self, parse_id: str) -> ParseJob:
        """Read one complete control-record revision under its writer lock.

        On Windows, an atomic ``os.replace`` can fail while another process has
        ``job.json`` open. Readers therefore participate in the per-job lock and
        keep the file handle open only inside that critical section. This gives a
        reader one whole durable revision instead of retrying a partial or racing
        snapshot, while preserving normal ``FileNotFoundError`` semantics.
        """

        normalized_parse_id = self._validate_parse_id(parse_id)
        path = self.job_path(normalized_parse_id)
        if not path.parent.is_dir():
            raise FileNotFoundError(normalized_parse_id)
        with _JOB_SAVE_LOCK, _exclusive_file_lock(self._job_lock_path(normalized_parse_id)):
            if not path.is_file():
                raise FileNotFoundError(normalized_parse_id)
            return ParseJob.model_validate_json(path.read_text(encoding="utf-8"))

    def save_job(self, job: ParseJob) -> ParseJob:
        """Persist a job using revision compare-and-swap across worker processes.

        A newly created job is the sole exception: it is written at revision zero when
        ``job.json`` does not yet exist. Every later successful save requires the
        caller's revision to equal the on-disk revision and returns a copy incremented
        by one. A stale writer receives :class:`JobConflictError` and must reload.
        """

        path = self.job_path(job.parse_id)
        if not path.parent.is_dir():
            raise FileNotFoundError(job.parse_id)
        with _JOB_SAVE_LOCK, _exclusive_file_lock(self._job_lock_path(job.parse_id)):
            if not path.is_file():
                if job.revision != 0:
                    raise JobConflictError(
                        f"Cannot create job {job.parse_id} at revision {job.revision}; expected revision 0."
                    )
                stored = job.model_copy(update={"updated_at": datetime.now(UTC)})
            else:
                current = ParseJob.model_validate_json(path.read_text(encoding="utf-8"))
                if current.revision != job.revision:
                    raise JobConflictError(
                        f"Job {job.parse_id} changed from revision {job.revision} "
                        f"to {current.revision}; reload before saving."
                    )
                stored = job.model_copy(
                    update={
                        "revision": job.revision + 1,
                        "updated_at": datetime.now(UTC),
                    }
                )
            self._write_text_atomic(path, stored.model_dump_json(indent=2))
        return stored

    def iter_jobs(self) -> Iterable[ParseJob]:
        """Return every readable persisted job for metrics and retention workers."""

        if not self.jobs_root.is_dir():
            return ()
        jobs: list[ParseJob] = []
        for path in self.jobs_root.glob("*/job.json"):
            try:
                jobs.append(self._load_job_locked(path.parent.name))
            except Exception:
                continue
        return tuple(sorted(jobs, key=lambda item: item.created_at))

    def iter_recoverable_jobs(self) -> Iterable[ParseJob]:
        if not self.jobs_root.is_dir():
            return ()
        jobs: list[ParseJob] = []
        for path in self.jobs_root.glob("*/job.json"):
            try:
                job = self._load_job_locked(path.parent.name)
            except Exception:
                continue
            if not job.status.terminal:
                jobs.append(job)
        return tuple(jobs)

    def find_by_idempotency_key(self, key: str) -> ParseJob | None:
        if not key or not self.jobs_root.is_dir():
            return None
        for path in self.jobs_root.glob("*/job.json"):
            try:
                job = self._load_job_locked(path.parent.name)
            except Exception:
                continue
            if job.idempotency_key == key:
                return job
        return None
    def job_source_path(self, parse_id: str, *, filename: str | None = None) -> Path:
        """Return the deterministic source path for a new or already-persisted job."""

        source_root = self.job_root(parse_id) / "source"
        if filename is not None:
            return source_root / _source_name_for_filename(filename)
        try:
            job = self.load_job(parse_id)
        except FileNotFoundError:
            candidates = sorted(source_root.glob("original.*"))
            if not candidates:
                raise FileNotFoundError(f"Original source not found for {parse_id}")
            return candidates[0]
        return source_root / _source_name_for_filename(job.source_filename)

    def load_request(self, parse_id: str) -> ParseRequest:
        """Load a request only after rechecking immutable source size and digest."""

        job = self.load_job(parse_id)
        content = self._load_validated_job_source(job)
        return ParseRequest(
            filename=job.source_filename,
            file_type=job.source_file_type,
            content=content,
            parser_id=job.requested_parser_id,
            options=dict(job.options),
        )

    def commit_completed_job(
        self,
        *,
        job: ParseJob,
        document: ParsedDocument,
        quality_package: QualityPackage,
        native_files: dict[str, bytes],
    ) -> str:
        """Atomically publish a complete package after validating all identities."""

        stored_job = self._validate_commit_job(job)
        source_content = self._load_validated_job_source(stored_job)
        self._validate_document_for_job(document, stored_job)
        self._validate_quality_for_document(quality_package, document)
        quality_artifacts = self._build_quality_artifact_files(quality_package)
        self._validate_native_files(native_files)

        target = self.package_root(stored_job.parse_id)
        if target.exists():
            raise FileExistsError(f"Result package already exists: {stored_job.parse_id}")
        stage = self._new_stage_directory(stored_job.parse_id)
        try:
            write_document_package(document, stage, native_files=native_files)
            self._write_quality_artifacts(
                stage,
                quality_package,
                expected_files=quality_artifacts,
            )
            self._write_bytes_atomic(
                stage / "source" / _source_name_for_filename(stored_job.source_filename),
                source_content,
            )
            quality_run_id = _quality_run_id(quality_package)
            self._write_text_atomic(
                stage / "quality_package.json",
                quality_package.model_dump_json(indent=2),
            )
            self._write_text_atomic(
                stage / _REVISION_NAME,
                _json_text(
                    self._revision_payload(
                        parse_id=stored_job.parse_id,
                        parent_parse_id=stored_job.parent_parse_id,
                        document=document,
                        source_filename=stored_job.source_filename,
                        source_file_type=stored_job.source_file_type,
                        source_size_bytes=stored_job.source_size_bytes,
                        source_sha256=stored_job.source_sha256,
                        quality_run_id=quality_run_id,
                    )
                ),
            )
            self.write_artifact_manifest(stage, document_id=str(document.document_id))
            self.verify_artifact_manifest(
                stage,
                require_manifest=True,
                expected_parse_id=stored_job.parse_id,
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            _replace_with_retry(stage, target)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        return str(target.resolve())

    def write_parse_package(
        self,
        *,
        parse_id: str,
        document: ParsedDocument,
        source_filename: str,
        source_content: bytes,
        native_files: dict[str, bytes],
    ) -> Path:
        """Compatibility entry point that still publishes an exact current manifest."""

        source_sha256 = hashlib.sha256(source_content).hexdigest()
        source_size = len(source_content)
        self._validate_document_source_identity(
            document,
            source_filename=source_filename,
            source_file_type=document.file_type,
            source_size_bytes=source_size,
            source_sha256=source_sha256,
            require_complete_identity=False,
        )
        self._validate_native_files(native_files)
        target = self.package_root(parse_id)
        if target.exists():
            raise FileExistsError(f"Result package already exists: {parse_id}")
        stage = self._new_stage_directory(parse_id)
        try:
            write_document_package(document, stage, native_files=native_files)
            self._write_bytes_atomic(
                stage / "source" / _source_name_for_filename(source_filename),
                source_content,
            )
            self._write_text_atomic(
                stage / _REVISION_NAME,
                _json_text(
                    self._revision_payload(
                        parse_id=parse_id,
                        parent_parse_id=None,
                        document=document,
                        source_filename=source_filename,
                        source_file_type=document.file_type,
                        source_size_bytes=source_size,
                        source_sha256=source_sha256,
                        quality_run_id=None,
                    )
                ),
            )
            self.write_artifact_manifest(stage, document_id=str(document.document_id))
            target.parent.mkdir(parents=True, exist_ok=True)
            _replace_with_retry(stage, target)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        return target

    def list_package_files(self, parse_id: str) -> list[dict[str, object]]:
        """List only manifest-authorized artifacts (not the manifest itself)."""

        package_root = self.package_root(parse_id)
        if not package_root.is_dir():
            raise FileNotFoundError(parse_id)
        files: list[dict[str, object]] = []
        for relative_path, metadata in self.iter_manifest_entries(package_root, require_manifest=True):
            files.append(
                {
                    "path": relative_path,
                    "size_bytes": metadata["size_bytes"],
                    "file_type": metadata.get("media_type") or self.content_type_for(package_root / relative_path),
                    "category": metadata.get("category") or _package_file_category(relative_path),
                }
            )
        return files

    def read_quality_delivery_snapshot(
        self,
        parse_id: str,
    ) -> tuple[QualityPackage, dict[str, bytes]]:
        """Read a verified, self-consistent business-delivery snapshot.

        The outer artifact manifest is verified before selection. The selected
        bytes are then matched against that manifest and the QualityPackage's
        inner four-file manifest, so a ZIP is never built from live paths after
        their verification has completed.
        """

        package_root = self.package_root(parse_id)
        if not package_root.is_dir():
            raise FileNotFoundError(parse_id)
        entries = dict(self.iter_manifest_entries(package_root, require_manifest=True))
        required_paths = (*QUALITY_PACKAGE_ARTIFACTS, "quality_package.json")
        missing = set(required_paths) - set(entries)
        if missing:
            raise ArtifactManifestError(
                "Published quality delivery set is incomplete: "
                + ", ".join(sorted(missing))
            )

        snapshot: dict[str, bytes] = {}
        for relative_path in required_paths:
            artifact_path = package_root / relative_path
            try:
                if artifact_path.is_symlink() or not artifact_path.is_file():
                    raise ArtifactManifestError(
                        f"Published delivery artifact is missing or unsafe: {relative_path}."
                    )
                content = artifact_path.read_bytes()
            except OSError as error:
                raise ArtifactManifestError(
                    f"Published delivery artifact cannot be read: {relative_path}."
                ) from error
            metadata = entries[relative_path]
            if (
                len(content) != metadata["size_bytes"]
                or hashlib.sha256(content).hexdigest() != metadata["sha256"]
            ):
                raise ArtifactManifestError(
                    f"Published delivery artifact changed during verification: {relative_path}."
                )
            snapshot[relative_path] = content

        # Recheck the complete outer manifest after the byte snapshot. A writer
        # that publishes another revision during this window causes a safe retry
        # instead of mixing its revision with the selected delivery bytes.
        if dict(self.iter_manifest_entries(package_root, require_manifest=True)) != entries:
            raise ArtifactManifestError(
                "Published package changed during delivery snapshot."
            )

        try:
            quality_package = QualityPackage.model_validate_json(
                snapshot["quality_package.json"]
            )
            delivery_files = {
                relative_path: snapshot[relative_path]
                for relative_path in QUALITY_PACKAGE_ARTIFACTS
            }
            expected_files = dict(build_package_artifacts(quality_package).files)
            verify_package_files(delivery_files)
        except ValueError as error:
            raise ArtifactManifestError(
                "Published quality delivery snapshot is invalid."
            ) from error
        if delivery_files != expected_files:
            raise ArtifactManifestError(
                "Published delivery files do not match quality_package.json."
            )
        return quality_package, delivery_files

    def registered_package_files(self, parse_id: str) -> tuple[Path, ...]:
        """Return verified, manifest-authorized files for a download implementation.

        The returned collection intentionally excludes ``artifact_manifest.json``;
        callers that include the manifest as package metadata must add that one file
        explicitly after this method succeeds.
        """

        package_root = self.package_root(parse_id)
        if not package_root.is_dir():
            raise FileNotFoundError(parse_id)
        return tuple(
            package_root / relative_path
            for relative_path, _ in self.iter_manifest_entries(package_root, require_manifest=True)
        )
    def iter_manifest_entries(
        self,
        package_root: Path | str,
        *,
        require_manifest: bool = False,
        expected_parse_id: str | None = None,
    ) -> tuple[tuple[str, dict[str, object]], ...]:
        """Return exact verified entries in stable path order.

        This is intentionally a read-only storage boundary for API list/download
        handlers. A package with an unregistered, missing, changed, or symlinked
        file is rejected rather than partially exposed.
        """

        root = Path(package_root)
        entries = self._validated_manifest_entries(
            root,
            require_manifest=require_manifest,
            expected_parse_id=expected_parse_id,
        )
        if entries is None:
            return ()
        return tuple((relative, dict(entries[relative])) for relative in sorted(entries))

    def quality_package_path(self, parse_id: str) -> Path:
        return self.package_root(parse_id) / "quality_package.json"

    def write_quality_package(self, parse_id: str, quality_package: QualityPackage) -> Path:
        """Replace a trusted quality result and atomically refresh revision metadata.

        This migration-only operation never accepts a package for a different
        document. On success ``quality_package.json``, ``revision.json`` and the
        outer artifact manifest agree on the same quality run id and document id.
        """

        package_root = self.package_root(parse_id)
        if not package_root.is_dir():
            raise FileNotFoundError(parse_id)
        self.verify_artifact_manifest(package_root)
        document = self.load_document(parse_id, verify_manifest=False)
        self._validate_quality_for_document(quality_package, document)
        quality_artifacts = self._build_quality_artifact_files(quality_package)

        source_path = _single_source_file(package_root, required=False)
        source_content = source_path.read_bytes() if source_path is not None else None
        existing_revision = self._read_revision(package_root, required=False)
        revision = self._revision_payload(
            parse_id=parse_id,
            parent_parse_id=(
                existing_revision.get("parent_parse_id") if existing_revision is not None else None
            ),
            document=document,
            source_filename=(
                existing_revision.get("source_filename")
                if existing_revision is not None
                else (source_path.name.replace("original", "source", 1) if source_path else document.filename)
            ),
            source_file_type=(
                existing_revision.get("source_file_type")
                if existing_revision is not None
                else document.file_type
            ),
            source_size_bytes=(
                len(source_content)
                if source_content is not None
                else document.source_size_bytes
            ),
            source_sha256=(
                hashlib.sha256(source_content).hexdigest()
                if source_content is not None
                else document.source_sha256
            ),
            quality_run_id=_quality_run_id(quality_package),
            created_at=(existing_revision.get("created_at") if existing_revision else None),
        )
        package_path = self.quality_package_path(parse_id)
        self._write_text_atomic(package_path, quality_package.model_dump_json(indent=2))
        self._write_quality_artifacts(
            package_root,
            quality_package,
            expected_files=quality_artifacts,
        )
        self._write_text_atomic(package_root / _REVISION_NAME, _json_text(revision))
        self.write_artifact_manifest(package_root, document_id=str(document.document_id))
        self.verify_artifact_manifest(package_root, require_manifest=True)
        return package_path

    @staticmethod
    def _build_quality_artifact_files(quality_package: QualityPackage) -> dict[str, bytes]:
        """Build and validate the quality delivery set before durable writes."""

        try:
            files = dict(build_package_artifacts(quality_package).files)
            verify_package_files(files)
        except ValueError as error:
            raise SourceIntegrityError(
                "Quality package does not produce a valid four-artifact delivery set."
            ) from error
        return files

    def _write_quality_artifacts(
        self,
        package_root: Path,
        quality_package: QualityPackage,
        *,
        expected_files: dict[str, bytes] | None = None,
    ) -> None:
        """Write the quality layer's prevalidated four-file delivery set."""

        files = expected_files or self._build_quality_artifact_files(quality_package)
        for relative_path, content in files.items():
            self._write_bytes_atomic(package_root / relative_path, content)
        self._verify_quality_artifacts(
            package_root,
            quality_package,
            expected_files=files,
        )

    @staticmethod
    def _verify_quality_artifacts(
        package_root: Path,
        quality_package: QualityPackage,
        *,
        expected_files: dict[str, bytes] | None = None,
    ) -> None:
        """Bind physical quality files to the in-memory QualityPackage contract."""

        try:
            expected = expected_files or dict(build_package_artifacts(quality_package).files)
        except ValueError as error:
            raise ArtifactManifestError(
                "Quality package four-artifact manifest is invalid."
            ) from error

        actual: dict[str, bytes] = {}
        for relative_path in expected:
            artifact_path = package_root / relative_path
            if artifact_path.is_symlink() or not artifact_path.is_file():
                raise ArtifactManifestError(
                    f"Published package is missing quality artifact: {relative_path}."
                )
            actual[relative_path] = artifact_path.read_bytes()

        try:
            verify_package_files(actual)
        except ValueError as error:
            raise ArtifactManifestError(
                "Published quality artifacts do not satisfy the quality package manifest."
            ) from error
        for relative_path, expected_content in expected.items():
            if actual[relative_path] != expected_content:
                raise ArtifactManifestError(
                    f"Quality artifact does not match quality_package.json: {relative_path}."
                )

    def load_quality_package(self, parse_id: str) -> QualityPackage:
        package_root = self.package_root(parse_id)
        self.verify_artifact_manifest(package_root)
        path = self.quality_package_path(parse_id)
        if not path.is_file():
            raise FileNotFoundError(parse_id)
        return QualityPackage.model_validate_json(path.read_text(encoding="utf-8"))

    def has_quality_package(self, parse_id: str) -> bool:
        return self.quality_package_path(parse_id).is_file()

    def load_document(self, parse_id: str, *, verify_manifest: bool = True) -> ParsedDocument:
        package_root = self.package_root(parse_id)
        if verify_manifest:
            self.verify_artifact_manifest(package_root)
        return load_document_package(package_root)

    def resolve_package_file(self, parse_id: str, relative_path: str) -> Path:
        safe_path = _validate_relative_path(relative_path)
        package_root = self.package_root(parse_id).resolve()
        entries = self._validated_manifest_entries(package_root, require_manifest=True)
        assert entries is not None
        if safe_path not in entries:
            raise FileNotFoundError(relative_path)
        target = (package_root / safe_path).resolve()
        if package_root != target and package_root not in target.parents:
            raise ValueError("Artifact path escapes the parse package.")
        if not target.is_file() or target.is_symlink():
            raise FileNotFoundError(relative_path)
        return target

    def content_type_for(self, path: Path) -> str:
        return mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    def write_artifact_manifest(self, package_root: Path | str, *, document_id: str | None = None) -> Path:
        """Write an exact manifest for every regular package file except itself."""

        root = Path(package_root)
        if not root.is_dir():
            raise FileNotFoundError(root)
        if document_id is None:
            document_id = _document_identity_from_file(root / "parsed_document.json")["document_id"]
        entries: dict[str, dict[str, object]] = {}
        for relative, path in _package_files(root, include_manifest=False):
            entries[relative] = {
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
                "media_type": self.content_type_for(path),
                "category": _package_file_category(relative),
            }
        payload = {
            "schema_name": "ArtifactManifest",
            "schema_version": "1.1",
            "document_id": str(document_id),
            "artifacts": entries,
        }
        path = root / _ARTIFACT_MANIFEST_NAME
        self._write_text_atomic(path, _json_text(payload, sort_keys=True))
        return path

    def verify_artifact_manifest(
        self,
        package_root: Path | str,
        *,
        require_manifest: bool = False,
        expected_parse_id: str | None = None,
    ) -> None:
        """Reject incomplete, unregistered, changed, or inconsistent published data.

        Pre-manifest document-package directories remain readable through
        ``load_document_package`` and through ``load_document`` when they contain no
        current ``revision.json``. Any package written by this storage adapter has a
        revision and is therefore required to retain its artifact manifest.
        """

        root = Path(package_root)
        self._validated_manifest_entries(
            root,
            require_manifest=require_manifest,
            expected_parse_id=expected_parse_id,
        )

    def _validated_manifest_entries(
        self,
        package_root: Path,
        *,
        require_manifest: bool,
        expected_parse_id: str | None = None,
    ) -> dict[str, dict[str, object]] | None:
        root = Path(package_root)
        manifest_path = root / _ARTIFACT_MANIFEST_NAME
        if manifest_path.is_symlink():
            raise ArtifactManifestError("Artifact manifest must not be a symlink.")
        if not manifest_path.is_file():
            if require_manifest or (root / _REVISION_NAME).exists():
                raise ArtifactManifestError("Published artifact package is missing artifact_manifest.json.")
            return None
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as error:
            raise ArtifactManifestError("Artifact manifest is invalid.") from error
        if not isinstance(payload, dict):
            raise ArtifactManifestError("Artifact manifest is invalid.")
        if payload.get("schema_name") != "ArtifactManifest":
            raise ArtifactManifestError("Artifact manifest has an invalid schema_name.")
        if not isinstance(payload.get("schema_version"), str):
            raise ArtifactManifestError("Artifact manifest has an invalid schema_version.")
        entries = payload.get("artifacts")
        if not isinstance(entries, dict):
            raise ArtifactManifestError("Artifact manifest has invalid artifacts.")

        normalized_entries: dict[str, dict[str, object]] = {}
        for relative, metadata in entries.items():
            if not isinstance(relative, str):
                raise ArtifactManifestError("Artifact manifest contains a non-string path.")
            safe_relative = _validate_relative_path(relative)
            if safe_relative == _ARTIFACT_MANIFEST_NAME:
                raise ArtifactManifestError("Artifact manifest must not register itself.")
            if safe_relative != relative:
                raise ArtifactManifestError(f"Artifact manifest path is not canonical: {relative}")
            if not isinstance(metadata, dict):
                raise ArtifactManifestError(f"Artifact manifest entry is invalid: {safe_relative}")
            expected_hash = metadata.get("sha256")
            expected_size = metadata.get("size_bytes")
            if (
                not _is_sha256(expected_hash)
                or not isinstance(expected_size, int)
                or isinstance(expected_size, bool)
                or expected_size < 0
            ):
                raise ArtifactManifestError(f"Artifact manifest entry is invalid: {safe_relative}")
            if safe_relative in normalized_entries:
                raise ArtifactManifestError(f"Artifact manifest contains duplicate path: {safe_relative}")
            normalized_entries[safe_relative] = dict(metadata)

        actual = dict(_package_files(root, include_manifest=False))
        actual_paths = set(actual)
        registered_paths = set(normalized_entries)
        missing = sorted(registered_paths - actual_paths)
        unregistered = sorted(actual_paths - registered_paths)
        if missing or unregistered:
            details: list[str] = []
            if missing:
                details.append(f"missing={missing}")
            if unregistered:
                details.append(f"unregistered={unregistered}")
            raise ArtifactManifestError(
                "Artifact manifest does not exactly cover package files: " + "; ".join(details)
            )

        for relative, metadata in normalized_entries.items():
            path = actual[relative]
            expected_hash = metadata["sha256"]
            expected_size = metadata["size_bytes"]
            if expected_hash != _sha256_file(path) or expected_size != path.stat().st_size:
                raise ArtifactManifestError(f"Artifact integrity check failed: {relative}")

        self._verify_package_identity(
            root,
            payload,
            expected_parse_id=expected_parse_id,
        )
        return normalized_entries

    def _verify_package_identity(
        self,
        package_root: Path,
        manifest: dict[str, Any],
        *,
        expected_parse_id: str | None = None,
    ) -> None:
        document = _document_identity_from_file(package_root / "parsed_document.json")
        manifest_document_id = manifest.get("document_id")
        if not isinstance(manifest_document_id, str) or manifest_document_id != document["document_id"]:
            raise ArtifactManifestError("Artifact manifest document_id does not match parsed_document.json.")

        revision = self._read_revision(package_root, required=False)
        if revision is None:
            return
        if revision.get("schema_name") != "DocumentRevision":
            raise ArtifactManifestError("Revision metadata has an invalid schema_name.")
        package_parse_id = (
            self._validate_parse_id(expected_parse_id)
            if expected_parse_id is not None
            else package_root.name
        )
        if revision.get("parse_id") != package_parse_id:
            raise ArtifactManifestError("Revision parse_id does not match its package directory.")
        if revision.get("document_id") != document["document_id"]:
            raise ArtifactManifestError("Revision document_id does not match parsed_document.json.")

        self._verify_revision_source_identity(package_root, revision, document)
        quality_path = package_root / "quality_package.json"
        expected_quality_run_id = revision.get("quality_run_id")
        if quality_path.is_file():
            try:
                quality_package = QualityPackage.model_validate_json(quality_path.read_text(encoding="utf-8"))
            except Exception as error:
                raise ArtifactManifestError("Stored quality package is invalid.") from error
            if str(quality_package.document_id) != document["document_id"]:
                raise ArtifactManifestError("Quality package document_id does not match parsed_document.json.")
            actual_quality_run_id = _quality_run_id(quality_package)
            if expected_quality_run_id != actual_quality_run_id:
                raise ArtifactManifestError("Revision quality_run_id does not match quality_package.json.")
            self._verify_quality_artifacts(package_root, quality_package)
        elif expected_quality_run_id is not None:
            raise ArtifactManifestError("Revision references a missing quality package.")

    def _verify_revision_source_identity(
        self,
        package_root: Path,
        revision: dict[str, Any],
        document: dict[str, Any],
    ) -> None:
        revision_sha = revision.get("source_sha256")
        revision_size = revision.get("source_size_bytes")
        source_path = _single_source_file(
            package_root,
            required=revision_sha is not None or revision_size is not None,
        )
        if source_path is not None:
            source_size = source_path.stat().st_size
            source_sha = _sha256_file(source_path)
            if revision_sha is not None and revision_sha != source_sha:
                raise ArtifactManifestError("Revision source_sha256 does not match the stored source.")
            if revision_size is not None and revision_size != source_size:
                raise ArtifactManifestError("Revision source_size_bytes does not match the stored source.")
        if document.get("source_sha256") is not None and revision_sha is not None:
            if document["source_sha256"] != revision_sha:
                raise ArtifactManifestError("Parsed document source_sha256 does not match revision metadata.")
        if document.get("source_size_bytes") is not None and revision_size is not None:
            if document["source_size_bytes"] != revision_size:
                raise ArtifactManifestError("Parsed document source_size_bytes does not match revision metadata.")
        if revision.get("source_filename") is not None and document.get("filename") is not None:
            if revision["source_filename"] != document["filename"]:
                raise ArtifactManifestError("Parsed document filename does not match revision metadata.")
        if revision.get("source_file_type") is not None and document.get("file_type") is not None:
            if revision["source_file_type"] != document["file_type"]:
                raise ArtifactManifestError("Parsed document file_type does not match revision metadata.")

    def _read_revision(self, package_root: Path, *, required: bool) -> dict[str, Any] | None:
        path = package_root / _REVISION_NAME
        if not path.is_file():
            if required:
                raise ArtifactManifestError("Published artifact package is missing revision.json.")
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as error:
            raise ArtifactManifestError("Revision metadata is invalid.") from error
        if not isinstance(payload, dict):
            raise ArtifactManifestError("Revision metadata is invalid.")
        return payload
    def _validate_commit_job(self, job: ParseJob) -> ParseJob:
        stored_job = self.load_job(job.parse_id)
        if stored_job.revision != job.revision:
            raise JobConflictError(
                f"Job {job.parse_id} changed from revision {job.revision} "
                f"to {stored_job.revision}; reload before committing artifacts."
            )
        identity_fields = (
            "source_sha256",
            "source_filename",
            "source_file_type",
            "source_size_bytes",
            "requested_parser_id",
            "options",
            "parent_parse_id",
        )
        changed = [
            field
            for field in identity_fields
            if getattr(stored_job, field) != getattr(job, field)
        ]
        if changed:
            raise SourceIntegrityError(
                "Commit job identity does not match its persisted control record: " + ", ".join(changed)
            )
        return stored_job

    def _load_validated_job_source(self, job: ParseJob) -> bytes:
        source_path = self.job_source_path(job.parse_id, filename=job.source_filename)
        if not source_path.is_file() or source_path.is_symlink():
            raise SourceIntegrityError(f"Original source is missing for job {job.parse_id}.")
        content = source_path.read_bytes()
        actual_size = len(content)
        actual_sha = hashlib.sha256(content).hexdigest()
        if actual_size != job.source_size_bytes or actual_sha != job.source_sha256:
            raise SourceIntegrityError(
                f"Original source integrity check failed for job {job.parse_id}: "
                f"expected size/hash {job.source_size_bytes}/{job.source_sha256}."
            )
        return content

    @staticmethod
    def _validate_document_for_job(document: ParsedDocument, job: ParseJob) -> None:
        ApiStorage._validate_document_source_identity(
            document,
            source_filename=job.source_filename,
            source_file_type=job.source_file_type,
            source_size_bytes=job.source_size_bytes,
            source_sha256=job.source_sha256,
            require_complete_identity=True,
        )
        if job.document_id is not None and job.document_id != document.document_id:
            raise SourceIntegrityError("Parsed document_id does not match the job's existing document_id.")

    @staticmethod
    def _validate_document_source_identity(
        document: ParsedDocument,
        *,
        source_filename: str,
        source_file_type: str,
        source_size_bytes: int,
        source_sha256: str,
        require_complete_identity: bool,
    ) -> None:
        expected = {
            "filename": source_filename,
            "file_type": source_file_type,
            "source_size_bytes": source_size_bytes,
            "source_sha256": source_sha256,
        }
        missing = [
            name
            for name in ("source_size_bytes", "source_sha256")
            if getattr(document, name) is None
        ]
        if require_complete_identity and missing:
            raise SourceIntegrityError(
                "Parsed document is missing required source identity: " + ", ".join(missing)
            )
        mismatches = [
            name
            for name, value in expected.items()
            if getattr(document, name) is not None and getattr(document, name) != value
        ]
        if mismatches:
            raise SourceIntegrityError(
                "Parsed document source identity does not match the job: " + ", ".join(mismatches)
            )

    @staticmethod
    def _validate_quality_for_document(quality_package: QualityPackage, document: ParsedDocument) -> None:
        if quality_package.document_id != document.document_id:
            raise SourceIntegrityError("Quality package document_id does not match parsed document_id.")

    @staticmethod
    def _validate_native_files(native_files: dict[str, bytes]) -> None:
        """Reserve every non-native path for storage-owned package artifacts."""

        seen: set[str] = set()
        for raw_path, content in native_files.items():
            if not isinstance(raw_path, str) or not isinstance(content, bytes):
                raise ValueError("Native sidecar paths must map to bytes.")
            try:
                safe_path = _validate_relative_path(raw_path)
            except ValueError as error:
                raise ValueError("Native sidecars must use canonical paths below native/.") from error
            if safe_path != raw_path or not safe_path.startswith("native/"):
                raise ValueError("Native sidecars must use canonical paths below native/.")
            if safe_path in seen:
                raise ValueError(f"Native sidecar path is duplicated: {safe_path}")
            seen.add(safe_path)

    @staticmethod
    def _revision_payload(
        *,
        parse_id: str,
        parent_parse_id: str | None,
        document: ParsedDocument,
        source_filename: str | None,
        source_file_type: str | None,
        source_size_bytes: int | None,
        source_sha256: str | None,
        quality_run_id: str | None,
        created_at: str | None = None,
    ) -> dict[str, object]:
        now = datetime.now(UTC).isoformat()
        payload: dict[str, object] = {
            "schema_name": "DocumentRevision",
            "schema_version": "1.1",
            "parse_id": parse_id,
            "parent_parse_id": parent_parse_id,
            "document_id": str(document.document_id),
            "source_filename": source_filename,
            "source_file_type": source_file_type,
            "source_size_bytes": source_size_bytes,
            "source_sha256": source_sha256,
            "quality_run_id": quality_run_id,
            "created_at": created_at or now,
            "updated_at": now,
        }
        return payload

    def _new_stage_directory(self, parse_id: str) -> Path:
        self.staging_root.mkdir(parents=True, exist_ok=True)
        return Path(
            tempfile.mkdtemp(
                prefix=f"{self._validate_parse_id(parse_id)}-",
                dir=self.staging_root,
            )
        )

    @staticmethod
    def _write_text_atomic(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            _replace_with_retry(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _write_bytes_atomic(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            _replace_with_retry(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _validate_parse_id(parse_id: str) -> str:
        if (
            not parse_id
            or parse_id.strip() != parse_id
            or parse_id in {".", ".."}
            or any(character in parse_id for character in "/\\:")
        ):
            raise ValueError("Invalid parse_id.")
        return parse_id

    @staticmethod
    def _validate_task_id(task_id: str) -> str:
        if (
            not task_id
            or task_id.strip() != task_id
            or task_id in {".", ".."}
            or any(character in task_id for character in "/\\:")
        ):
            raise ValueError("Invalid task_id.")
        return task_id

    @staticmethod
    def _validate_task_file_id(task_file_id: str) -> str:
        if (
            not task_file_id
            or task_file_id.strip() != task_file_id
            or task_file_id in {".", ".."}
            or any(character in task_file_id for character in "/\\:")
        ):
            raise ValueError("Invalid task_file_id.")
        return task_file_id


@contextmanager
def _exclusive_file_lock(lock_path: Path):
    """Acquire an O_EXCL lock with bounded waiting and safe stale-lock recovery."""

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    reaper_path = lock_path.with_name(f".{lock_path.name}.reaper")
    owner = uuid4().hex
    deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
    file_descriptor: int | None = None
    while file_descriptor is None:
        if reaper_path.exists():
            _wait_for_file_lock(lock_path, deadline)
            continue
        try:
            file_descriptor = os.open(
                str(lock_path),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            )
        except FileExistsError:
            _try_reap_stale_file_lock(lock_path, reaper_path)
            _wait_for_file_lock(lock_path, deadline)
        except PermissionError:
            _wait_for_file_lock(lock_path, deadline)

    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", closefd=True) as handle:
            file_descriptor = None
            handle.write(json.dumps({"owner": owner, "pid": os.getpid(), "created_at": time.time()}))
            handle.flush()
            os.fsync(handle.fileno())
        yield
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        _release_owned_file_lock(lock_path, owner)


def _release_owned_file_lock(lock_path: Path, owner: str) -> None:
    """Remove only our lock, retrying Windows sharing violations for a bounded time."""

    deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
    while True:
        try:
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (PermissionError, OSError, json.JSONDecodeError):
            _wait_for_file_lock_release(lock_path, deadline)
            continue
        if not isinstance(payload, dict) or payload.get("owner") != owner:
            return
        try:
            lock_path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            _wait_for_file_lock_release(lock_path, deadline)


def _unlink_transient_lock_file(lock_path: Path) -> None:
    """Remove a reaper/graveyard file despite a brief Windows sharing violation."""

    deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
    while True:
        try:
            lock_path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            _wait_for_file_lock_release(lock_path, deadline)


def _wait_for_file_lock_release(lock_path: Path, deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise JobConflictError(
            f"Timed out releasing filesystem lock {lock_path.name}; retry the operation."
        )
    time.sleep(_LOCK_POLL_SECONDS)


def _wait_for_file_lock(lock_path: Path, deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise JobConflictError(
            f"Timed out waiting for the filesystem lock protecting {lock_path.name}; retry the operation."
        )
    time.sleep(_LOCK_POLL_SECONDS)


def _try_reap_stale_file_lock(lock_path: Path, reaper_path: Path) -> None:
    """Only one reaper may move a dead owner's old lock out of the way."""

    try:
        reaper_descriptor = os.open(
            str(reaper_path),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        )
    except (FileExistsError, PermissionError):
        return
    try:
        os.close(reaper_descriptor)
        try:
            stat = lock_path.stat()
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return
        if time.time() - stat.st_mtime < _LOCK_STALE_SECONDS:
            return
        owner_pid = payload.get("pid") if isinstance(payload, dict) else None
        if isinstance(owner_pid, int) and _process_is_alive(owner_pid):
            return
        graveyard = lock_path.with_name(f".{lock_path.name}.{uuid4().hex}.stale")
        try:
            os.replace(lock_path, graveyard)
        except (FileNotFoundError, PermissionError):
            return
        _unlink_transient_lock_file(graveyard)
    finally:
        _unlink_transient_lock_file(reaper_path)


def _process_is_alive(process_id: int) -> bool:
    if process_id <= 0:
        return False
    if process_id == os.getpid():
        return True
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    else:
        return True

def _replace_with_retry(source: Path, target: Path) -> None:
    """Retry transient Windows sharing violations while preserving atomic replace."""

    for attempt in range(_ATOMIC_REPLACE_ATTEMPTS):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt + 1 >= _ATOMIC_REPLACE_ATTEMPTS:
                raise
            time.sleep(_ATOMIC_REPLACE_INITIAL_DELAY_SECONDS * (2**attempt))


def _quality_run_id(quality_package: QualityPackage) -> str:
    payload = quality_package.package_manifest.model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:32]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_files(package_root: Path, *, include_manifest: bool) -> tuple[tuple[str, Path], ...]:
    """Return only safe regular files and reject links anywhere in a package."""

    if not package_root.is_dir():
        raise FileNotFoundError(package_root)
    root = package_root.resolve()
    files: list[tuple[str, Path]] = []
    for path in package_root.rglob("*"):
        if path.is_symlink():
            raise ArtifactManifestError(
                f"Package contains a symlink: {path.relative_to(package_root).as_posix()}"
            )
        if not path.is_file():
            continue
        resolved = path.resolve()
        if root != resolved and root not in resolved.parents:
            raise ArtifactManifestError("Package file escapes its root.")
        relative = path.relative_to(package_root).as_posix()
        if not include_manifest and relative == _ARTIFACT_MANIFEST_NAME:
            continue
        files.append((relative, path))
    return tuple(sorted(files, key=lambda item: item[0]))


def _document_identity_from_file(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ArtifactManifestError("Package is missing a safe parsed_document.json.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise ArtifactManifestError("parsed_document.json is invalid.") from error
    if not isinstance(payload, dict):
        raise ArtifactManifestError("parsed_document.json is invalid.")
    document_id = payload.get("document_id")
    if not isinstance(document_id, str):
        raise ArtifactManifestError("parsed_document.json is missing document_id.")
    try:
        UUID(document_id)
    except (TypeError, ValueError) as error:
        raise ArtifactManifestError("parsed_document.json has an invalid document_id.") from error
    return payload


def _single_source_file(package_root: Path, *, required: bool) -> Path | None:
    source_root = package_root / "source"
    candidates = (
        sorted(
            path
            for path in source_root.glob("original.*")
            if path.is_file() and not path.is_symlink()
        )
        if source_root.is_dir()
        else []
    )
    if len(candidates) != 1:
        if required:
            raise ArtifactManifestError("Package must contain exactly one original source file.")
        return None
    return candidates[0]


def _source_name_for_filename(filename: str) -> str:
    suffix = Path(filename).suffix or ".bin"
    return f"original{suffix}"


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value.lower())


def _json_text(payload: object, *, sort_keys: bool = False) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=sort_keys)


def _package_file_category(relative_path: str) -> str:
    if relative_path.startswith("native/"):
        return "parser_output"
    if relative_path.startswith("source/"):
        return "source"
    if relative_path.startswith("assets/"):
        return "asset"
    if relative_path == "parsed_document.json":
        return "parsed_document"
    if relative_path == "optimized.md":
        return "optimized_markdown"
    if relative_path == "canonical_document.json":
        return "canonical_document"
    if relative_path == "quality_report.json":
        return "quality_report"
    if relative_path == "package_manifest.json":
        return "quality_manifest"
    if relative_path == "document.md":
        return "rendered_markdown"
    if relative_path == "quality_package.json":
        return "quality_package"
    if relative_path == _REVISION_NAME:
        return "document_revision"
    if relative_path == _ARTIFACT_MANIFEST_NAME:
        return "artifact_manifest"
    return "other"


def _validate_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(normalized)
    if (
        not normalized
        or normalized == "."
        or "\x00" in normalized
        or ":" in normalized
        or path.is_absolute()
        or bool(windows_path.drive)
        or ".." in path.parts
        or normalized.endswith("/")
    ):
        raise ValueError("Artifact path must be a safe relative path.")
    return str(path)