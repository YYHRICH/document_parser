"""Filesystem adapters for source snapshots and lifecycle persistence."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from ...domain.lifecycle import LifecycleEvent, SourceManifest, SourceSnapshot


DEFAULT_SOURCE_SUFFIXES = frozenset(
    {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".md", ".txt", ".png", ".jpg", ".jpeg", ".webp"}
)


class FileSystemSourceFolder:
    def __init__(self, root: Path, *, excluded_roots: tuple[Path, ...] = (), suffixes: frozenset[str] = DEFAULT_SOURCE_SUFFIXES) -> None:
        self.root = root.resolve()
        self.excluded_roots = tuple(path.resolve() for path in excluded_roots)
        self.suffixes = suffixes

    def snapshot(self) -> list[SourceSnapshot]:
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)
        result = []
        for path in sorted(self.root.rglob("*")):
            resolved = path.resolve()
            if not path.is_file() or path.suffix.lower() not in self.suffixes:
                continue
            if any(excluded == resolved or excluded in resolved.parents for excluded in self.excluded_roots):
                continue
            result.append(SourceSnapshot(path=path.relative_to(self.root).as_posix(), sha256=self._sha256(path), size_bytes=path.stat().st_size))
        return result

    def read_bytes(self, relative_path: str) -> bytes:
        target = (self.root / relative_path).resolve()
        if self.root != target and self.root not in target.parents:
            raise ValueError("source path escapes managed folder")
        return target.read_bytes()

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


class JsonSourceLifecycleRepository:
    def __init__(self, state_root: Path) -> None:
        self.state_root = state_root
        self.manifest_path = state_root / "manifest.json"
        self.events_path = state_root / "events.jsonl"

    def load(self) -> SourceManifest:
        if not self.manifest_path.is_file():
            return SourceManifest()
        return SourceManifest.model_validate_json(self.manifest_path.read_text(encoding="utf-8"))

    def save(self, manifest: SourceManifest) -> None:
        self._atomic_text(self.manifest_path, manifest.model_dump_json(indent=2) + "\n")

    def append_events(self, events: list[LifecycleEvent]) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        occurred_at = datetime.now(UTC).isoformat()
        with self.events_path.open("a", encoding="utf-8", newline="\n") as handle:
            for event in events:
                handle.write(json.dumps({"occurred_at": occurred_at, **event.as_dict()}, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _atomic_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
            os.replace(temporary, path)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise
