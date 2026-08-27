"""Pure task-workbench domain models and safe state projections.

A :class:`ProcessingTask` groups one or more logical user files.  It deliberately
keeps the existing ``ParseJob`` as the file-level execution record: task records
only retain opaque parse identifiers and never contain package paths, source
bytes, source hashes, parser options, or raw failures.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from ..orchestration.models import JobConflictError, ParseFailureKind, ParseJob, ParseJobStatus


_MAX_IDENTIFIER_LENGTH = 128
_MAX_DISPLAY_NAME_LENGTH = 255
_MAX_FILE_TYPE_LENGTH = 128
_SAFE_QUALITY_STATES = frozenset(
    {
        "pass",
        "pass_with_warnings",
        "manual_review_required",
        "reparse_required",
        "rejected",
    }
)


class TaskConflictError(JobConflictError):
    """A task control record changed after a caller read its CAS revision."""


class TaskFileUserState(StrEnum):
    """The only four file states presented by the processing workbench."""

    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    AVAILABLE = "available"
    FAILED = "failed"


# Short alias for callers that do not need to distinguish storage state from UI state.
TaskFileState = TaskFileUserState


class TaskFileAction(StrEnum):
    """The primary safe action for the file row in the processing center."""

    VIEW_PROGRESS = "view_progress"
    REVIEW_RESULT = "review_result"
    VIEW_RESULT = "view_result"
    VIEW_FAILURE = "view_failure"


class TaskFile(BaseModel):
    """One logical file in a user-visible processing task.

    ``parse_history`` is oldest-to-newest and append-only at the domain boundary.
    ``active_parse_id`` is nullable only before a successfully accepted child job
    has been attached.  This supports partial acceptance without inventing a
    failed ParseJob for a rejected upload.
    """

    schema_name: str = "TaskFile"
    schema_version: str = "1.0"
    task_file_id: str = Field(default_factory=lambda: uuid4().hex)
    display_name: str
    source_file_type: str
    source_size_bytes: int = Field(ge=0)
    active_parse_id: str | None = None
    parse_history: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("task_file_id")
    @classmethod
    def validate_task_file_id(cls, value: str) -> str:
        return _validate_identifier(value, field_name="task_file_id")

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ValueError("display_name must be a non-empty file name.")
        if len(value) > _MAX_DISPLAY_NAME_LENGTH:
            raise ValueError("display_name is too long.")
        if value in {".", ".."} or any(character in value for character in "\\/\x00:"):
            raise ValueError("display_name must not contain a filesystem path.")
        return value

    @field_validator("source_file_type")
    @classmethod
    def validate_source_file_type(cls, value: str) -> str:
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ValueError("source_file_type must be a non-empty media type.")
        if len(value) > _MAX_FILE_TYPE_LENGTH or any(character in value for character in "\\\x00"):
            raise ValueError("source_file_type must be a safe media type.")
        return value

    @field_validator("active_parse_id")
    @classmethod
    def validate_active_parse_id(cls, value: str | None) -> str | None:
        return None if value is None else _validate_identifier(value, field_name="active_parse_id")

    @field_validator("parse_history")
    @classmethod
    def validate_parse_history(cls, value: list[str]) -> list[str]:
        normalized = [_validate_identifier(item, field_name="parse_history") for item in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("parse_history cannot contain duplicate parse identifiers.")
        return normalized

    @model_validator(mode="after")
    def validate_parse_association(self) -> "TaskFile":
        if self.active_parse_id is None and self.parse_history:
            raise ValueError("parse_history requires an active_parse_id.")
        if self.active_parse_id is not None and self.active_parse_id not in self.parse_history:
            raise ValueError("active_parse_id must be present in parse_history.")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at.")
        return self

    def attach_initial_parse(self, parse_id: str) -> "TaskFile":
        """Attach the first accepted child job without changing logical file identity."""

        normalized_parse_id = _validate_identifier(parse_id, field_name="parse_id")
        if self.active_parse_id is not None:
            if self.active_parse_id == normalized_parse_id:
                return self
            raise ValueError("A TaskFile already has an active parse; use activate_parse instead.")
        return self.model_copy(
            update={
                "active_parse_id": normalized_parse_id,
                "parse_history": [normalized_parse_id],
                "updated_at": datetime.now(UTC),
            }
        )

    def activate_parse(self, parse_id: str) -> "TaskFile":
        """Make an existing or newly-created same-source child parse current."""

        normalized_parse_id = _validate_identifier(parse_id, field_name="parse_id")
        if self.active_parse_id == normalized_parse_id:
            return self
        history = list(self.parse_history)
        if normalized_parse_id not in history:
            history.append(normalized_parse_id)
        return self.model_copy(
            update={
                "active_parse_id": normalized_parse_id,
                "parse_history": history,
                "updated_at": datetime.now(UTC),
            }
        )


class ProcessingTask(BaseModel):
    """Durable aggregate for one user submission containing one or more files."""

    schema_name: str = "ProcessingTask"
    schema_version: str = "1.0"
    task_id: str = Field(default_factory=lambda: uuid4().hex)
    # P0 can bind this opaque value to a tenant/owner scope later.  It is never
    # included in the safe workbench projection until an authorization layer owns it.
    scope: str | None = None
    files: list[TaskFile] = Field(min_length=1)
    revision: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        return _validate_identifier(value, field_name="task_id")

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, value: str | None) -> str | None:
        return None if value is None else _validate_identifier(value, field_name="scope")

    @model_validator(mode="after")
    def validate_files(self) -> "ProcessingTask":
        file_ids = [item.task_file_id for item in self.files]
        if len(file_ids) != len(set(file_ids)):
            raise ValueError("A ProcessingTask cannot contain duplicate task_file_id values.")
        parse_ids = [parse_id for item in self.files for parse_id in item.parse_history]
        if len(parse_ids) != len(set(parse_ids)):
            raise ValueError("A parse_id can belong to only one TaskFile.")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at.")
        return self

    def file_by_id(self, task_file_id: str) -> TaskFile:
        normalized_id = _validate_identifier(task_file_id, field_name="task_file_id")
        for task_file in self.files:
            if task_file.task_file_id == normalized_id:
                return task_file
        raise KeyError(normalized_id)

    def replace_file(self, replacement: TaskFile) -> "ProcessingTask":
        """Return a validated aggregate with one logical file replaced."""

        found = False
        files: list[TaskFile] = []
        for task_file in self.files:
            if task_file.task_file_id == replacement.task_file_id:
                files.append(replacement)
                found = True
            else:
                files.append(task_file)
        if not found:
            raise KeyError(replacement.task_file_id)
        return self.model_copy(update={"files": files, "updated_at": datetime.now(UTC)})


class TaskFileLocation(BaseModel):
    """Opaque reverse association from a parse job to its task and logical file."""

    task_id: str
    task_file_id: str

    @field_validator("task_id", "task_file_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return _validate_identifier(value, field_name=info.field_name)


class TaskFileProjection(BaseModel):
    """Path-free, content-free view of a logical file for workbench consumers."""

    task_file_id: str
    display_name: str
    source_file_type: str
    source_size_bytes: int = Field(ge=0)
    active_parse_id: str | None = None
    state: TaskFileUserState
    next_action: TaskFileAction
    stage: ParseJobStatus | None = None
    quality_state: str | None = None
    failure_kind: ParseFailureKind | None = None
    retryable: bool = False
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class TaskAggregate(BaseModel):
    """Counts derived from file projections; never a delivery or quality authority."""

    task_id: str
    total_files: int = Field(ge=0)
    processing_count: int = Field(ge=0)
    needs_review_count: int = Field(ge=0)
    available_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    downloadable_count: int = Field(ge=0)
    updated_at: datetime


class TaskProjection(BaseModel):
    """Safe task-center projection with no storage paths or raw ParseJob fields."""

    task_id: str
    revision: int = Field(ge=0)
    files: list[TaskFileProjection]
    aggregate: TaskAggregate
    created_at: datetime
    updated_at: datetime


class TaskRepository(Protocol):
    """Storage port for task aggregation, independent of HTTP and parser internals."""

    def new_task_id(self) -> str: ...

    def create_task(self, task: ProcessingTask) -> ProcessingTask: ...

    def load_task(self, task_id: str) -> ProcessingTask: ...

    def list_tasks(self) -> Sequence[ProcessingTask]: ...

    def attach_task_file_parse(
        self,
        task_id: str,
        task_file_id: str,
        parse_id: str,
        *,
        expected_revision: int,
    ) -> ProcessingTask: ...

    def switch_task_file_active_parse(
        self,
        task_id: str,
        task_file_id: str,
        parse_id: str,
        *,
        expected_revision: int,
    ) -> ProcessingTask: ...

    def find_task_file_by_parse_id(self, parse_id: str) -> TaskFileLocation | None: ...

    def project_task(self, task_id: str) -> TaskProjection: ...


def project_task_file(task_file: TaskFile, job: ParseJob | None) -> TaskFileProjection:
    """Map one current ParseJob to a conservative, safe user-facing state."""

    if task_file.active_parse_id is None:
        return TaskFileProjection(
            task_file_id=task_file.task_file_id,
            display_name=task_file.display_name,
            source_file_type=task_file.source_file_type,
            source_size_bytes=task_file.source_size_bytes,
            active_parse_id=None,
            state=TaskFileUserState.PROCESSING,
            next_action=TaskFileAction.VIEW_PROGRESS,
            created_at=task_file.created_at,
            updated_at=task_file.updated_at,
        )
    if job is None:
        # A durable task points at a missing control record.  Do not claim that
        # it is still executing or that its output is available for download.
        return TaskFileProjection(
            task_file_id=task_file.task_file_id,
            display_name=task_file.display_name,
            source_file_type=task_file.source_file_type,
            source_size_bytes=task_file.source_size_bytes,
            active_parse_id=task_file.active_parse_id,
            state=TaskFileUserState.FAILED,
            next_action=TaskFileAction.VIEW_FAILURE,
            created_at=task_file.created_at,
            updated_at=task_file.updated_at,
        )
    if job.parse_id != task_file.active_parse_id:
        raise ValueError("TaskFile projection received a job other than its active parse.")

    quality_state = _safe_quality_state(job.quality_state)
    state = _user_state_for_job(job, quality_state=quality_state)
    action = {
        TaskFileUserState.PROCESSING: TaskFileAction.VIEW_PROGRESS,
        TaskFileUserState.NEEDS_REVIEW: TaskFileAction.REVIEW_RESULT,
        TaskFileUserState.AVAILABLE: TaskFileAction.VIEW_RESULT,
        TaskFileUserState.FAILED: TaskFileAction.VIEW_FAILURE,
    }[state]
    return TaskFileProjection(
        task_file_id=task_file.task_file_id,
        display_name=task_file.display_name,
        source_file_type=task_file.source_file_type,
        source_size_bytes=task_file.source_size_bytes,
        active_parse_id=task_file.active_parse_id,
        state=state,
        next_action=action,
        stage=job.status,
        quality_state=quality_state,
        failure_kind=job.failure_kind,
        retryable=bool(job.retryable and state == TaskFileUserState.FAILED),
        created_at=task_file.created_at,
        updated_at=max(task_file.updated_at, job.updated_at),
        completed_at=job.completed_at,
    )


def aggregate_task(
    task: ProcessingTask,
    jobs_by_parse_id: Mapping[str, ParseJob | None],
) -> TaskProjection:
    """Build a task-center projection from already-loaded current ParseJobs."""

    files = [
        project_task_file(task_file, jobs_by_parse_id.get(task_file.active_parse_id))
        for task_file in task.files
    ]
    counts = {state: 0 for state in TaskFileUserState}
    for item in files:
        counts[item.state] += 1
    updated_at = max([task.updated_at, *(item.updated_at for item in files)])
    aggregate = TaskAggregate(
        task_id=task.task_id,
        total_files=len(files),
        processing_count=counts[TaskFileUserState.PROCESSING],
        needs_review_count=counts[TaskFileUserState.NEEDS_REVIEW],
        available_count=counts[TaskFileUserState.AVAILABLE],
        failed_count=counts[TaskFileUserState.FAILED],
        completed_count=(
            counts[TaskFileUserState.NEEDS_REVIEW]
            + counts[TaskFileUserState.AVAILABLE]
            + counts[TaskFileUserState.FAILED]
        ),
        downloadable_count=counts[TaskFileUserState.AVAILABLE],
        updated_at=updated_at,
    )
    return TaskProjection(
        task_id=task.task_id,
        revision=task.revision,
        files=files,
        aggregate=aggregate,
        created_at=task.created_at,
        updated_at=updated_at,
    )


def _user_state_for_job(
    job: ParseJob,
    *,
    quality_state: str | None,
) -> TaskFileUserState:
    if job.status in {ParseJobStatus.FAILED, ParseJobStatus.CANCELLED}:
        return TaskFileUserState.FAILED
    if not job.status.terminal:
        return TaskFileUserState.PROCESSING
    if quality_state in _SAFE_QUALITY_STATES:
        # A quality state describes how downstream consumers should handle the
        # document. It is not a task-completion gate. This also releases legacy
        # NEEDS_REVIEW records that already have a valid package.
        return TaskFileUserState.AVAILABLE
    # A terminal result without a recognised quality gate must never appear as
    # downloadable. The user can inspect it, while the system retains evidence.
    return TaskFileUserState.NEEDS_REVIEW


def _safe_quality_state(value: str | None) -> str | None:
    return value if value in _SAFE_QUALITY_STATES else None


def _validate_identifier(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{field_name} must be a non-empty identifier.")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise ValueError(f"{field_name} is too long.")
    if value in {".", ".."} or any(character in value for character in "\\/\x00:"):
        raise ValueError(f"{field_name} must not contain a filesystem path.")
    return value
