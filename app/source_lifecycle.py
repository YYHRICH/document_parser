"""Application orchestration for parser-owned source lifecycle."""

from __future__ import annotations

import mimetypes
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from ..domain.lifecycle import LifecycleEvent, LifecycleEventKind, SourceRecord, SourceState
from ..domain.model.contracts import ParseRequest
from ..domain.ports import MultimodalDeliveryPort, SourceFolderPort, SourceLifecycleRepositoryPort, WikiDeliveryPort
from .use_cases import ParseApplicationResult


class ParseUseCase(Protocol):
    def execute(self, request: ParseRequest) -> ParseApplicationResult: ...


class SourceLifecycleService:
    """Reconcile snapshots, invoke parsing, and publish through explicit ports."""

    def __init__(self, parse_use_case: ParseUseCase, *, sources: SourceFolderPort, repository: SourceLifecycleRepositoryPort, delivery: WikiDeliveryPort | None = None, multimodal_delivery: MultimodalDeliveryPort | None = None) -> None:
        self._parse = parse_use_case
        self._sources = sources
        self._repository = repository
        self._delivery = delivery
        self._multimodal_delivery = multimodal_delivery

    def scan(self, *, parser_id: str | None = None, options: dict[str, object] | None = None) -> list[LifecycleEvent]:
        manifest = self._repository.load()
        active_by_path = {record.path: (source_id, record) for source_id, record in manifest.sources.items() if record.state in {SourceState.ACTIVE, SourceState.PARSE_FAILED}}
        snapshots = {snapshot.path: snapshot for snapshot in self._sources.snapshot()}
        missing = {path: item for path, item in active_by_path.items() if path not in snapshots}
        missing_by_sha: dict[str, list[tuple[str, str, SourceRecord]]] = {}
        for old_path, (source_id, record) in missing.items():
            missing_by_sha.setdefault(record.sha256, []).append((old_path, source_id, record))

        events: list[LifecycleEvent] = []
        consumed_missing: set[str] = set()
        now = datetime.now(UTC)
        for relative, snapshot in snapshots.items():
            existing = active_by_path.get(relative)
            if existing is not None:
                source_id, record = existing
                if record.sha256 == snapshot.sha256 and record.state == SourceState.ACTIVE:
                    events.append(LifecycleEvent(kind=LifecycleEventKind.UNCHANGED, source_id=source_id, path=relative))
                    continue
                kind = LifecycleEventKind.RETRY if record.state == SourceState.PARSE_FAILED else LifecycleEventKind.MODIFIED
                event = self._parse_changed(relative, source_id, kind, parser_id, options)
                events.append(event)
                manifest.sources[source_id] = self._record_after_event(record, event, snapshot.sha256, now)
                continue

            move = next((item for item in missing_by_sha.get(snapshot.sha256, []) if item[0] not in consumed_missing), None)
            if move is not None:
                old_path, source_id, record = move
                consumed_missing.add(old_path)
                error = None
                try:
                    filename = relative.rsplit("/", 1)[-1]
                    if self._delivery is not None:
                        self._delivery.relocate(source_id, filename=filename)
                    if self._multimodal_delivery is not None:
                        self._multimodal_delivery.relocate(source_id, filename=filename)
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                manifest.sources[source_id] = record.model_copy(update={"path": relative, "state": SourceState.PARSE_FAILED if error else SourceState.ACTIVE, "updated_at": now, "last_error": error})
                events.append(LifecycleEvent(kind=LifecycleEventKind.MOVED, source_id=source_id, path=relative, previous_path=old_path, error=error, multimodal_package_path=record.multimodal_package_path, multimodal_state=record.multimodal_state))
                continue

            source_id = f"src_{uuid4().hex[:16]}"
            record = SourceRecord(source_id=source_id, path=relative, sha256=snapshot.sha256, state=SourceState.ACTIVE, created_at=now, updated_at=now)
            event = self._parse_changed(relative, source_id, LifecycleEventKind.ADDED, parser_id, options)
            events.append(event)
            manifest.sources[source_id] = self._record_after_event(record, event, snapshot.sha256, now)

        for old_path, (source_id, record) in missing.items():
            if old_path in consumed_missing:
                continue
            manifest.sources[source_id] = record.model_copy(update={"state": SourceState.DELETED, "updated_at": now})
            if self._delivery is not None:
                self._delivery.withdraw(source_id, reason="source_deleted")
            if self._multimodal_delivery is not None:
                self._multimodal_delivery.withdraw(source_id, reason="source_deleted")
            events.append(LifecycleEvent(kind=LifecycleEventKind.DELETED, source_id=source_id, path=old_path))

        manifest.updated_at = now
        self._repository.save(manifest)
        self._repository.append_events(events)
        return events

    def delivery_status(self) -> dict[str, object]:
        if self._delivery is None:
            return {"configured": False, "active_count": 0, "deleted_count": 0, "sources": []}
        return {"configured": True, **self._delivery.status()}

    def multimodal_delivery_status(self) -> dict[str, object]:
        if self._multimodal_delivery is None:
            return {"configured": False, "ready_count": 0, "withdrawn_count": 0, "sources": []}
        return {"configured": True, **self._multimodal_delivery.status()}

    def _parse_changed(self, relative: str, source_id: str, kind: LifecycleEventKind, parser_id: str | None, options: dict[str, object] | None) -> LifecycleEvent:
        try:
            result = self._parse.execute(ParseRequest(filename=relative.rsplit("/", 1)[-1], file_type=mimetypes.guess_type(relative)[0] or "application/octet-stream", content=self._sources.read_bytes(relative), parser_id=parser_id, options=dict(options or {})))
            multimodal = None
            if self._multimodal_delivery is not None:
                multimodal = self._multimodal_delivery.publish(source_id=source_id, parse_id=result.parse_id, document=result.document)
            if self._delivery is not None:
                self._delivery.publish(source_id=source_id, parse_id=result.parse_id, document=result.document, quality_package=result.quality_package)
            return LifecycleEvent(kind=kind, source_id=source_id, path=relative, parse_id=result.parse_id, package_path=str(result.package_root), parser_id=result.document.provenance.parser_id, quality_state=result.quality_package.quality_report.state.value, multimodal_package_path=str(multimodal["package_path"]) if multimodal else None, multimodal_state=str(multimodal["state"]) if multimodal else None)
        except Exception as error:
            return LifecycleEvent(kind=kind, source_id=source_id, path=relative, error=f"{type(error).__name__}: {error}")

    @staticmethod
    def _record_after_event(record: SourceRecord, event: LifecycleEvent, digest: str, now: datetime) -> SourceRecord:
        if event.error:
            return record.model_copy(update={"sha256": digest, "state": SourceState.PARSE_FAILED, "updated_at": now, "last_error": event.error})
        return record.model_copy(update={"sha256": digest, "state": SourceState.ACTIVE, "updated_at": now, "parse_id": event.parse_id, "package_path": event.package_path, "parser_id": event.parser_id, "quality_state": event.quality_state, "last_error": None, "multimodal_package_path": event.multimodal_package_path, "multimodal_state": event.multimodal_state})
