"""Source lifecycle domain types; independent of filesystem persistence."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SourceState(StrEnum):
    ACTIVE = "active"
    PARSE_FAILED = "parse_failed"
    DELETED = "deleted"


class LifecycleEventKind(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    MOVED = "moved"
    DELETED = "deleted"
    UNCHANGED = "unchanged"
    RETRY = "retry"


class SourceSnapshot(BaseModel):
    path: str
    sha256: str
    size_bytes: int = Field(ge=0)


class SourceRecord(BaseModel):
    source_id: str
    path: str
    sha256: str
    state: SourceState
    created_at: datetime
    updated_at: datetime
    parse_id: str | None = None
    package_path: str | None = None
    parser_id: str | None = None
    quality_state: str | None = None
    last_error: str | None = None
    multimodal_package_path: str | None = None
    multimodal_state: str | None = None


class SourceManifest(BaseModel):
    version: int = 1
    updated_at: datetime | None = None
    sources: dict[str, SourceRecord] = Field(default_factory=dict)


class LifecycleEvent(BaseModel):
    kind: LifecycleEventKind
    source_id: str
    path: str
    previous_path: str | None = None
    parse_id: str | None = None
    package_path: str | None = None
    parser_id: str | None = None
    quality_state: str | None = None
    error: str | None = None
    multimodal_package_path: str | None = None
    multimodal_state: str | None = None

    def as_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude_none=True)
