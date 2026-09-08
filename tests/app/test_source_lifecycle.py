from pathlib import Path
from types import SimpleNamespace

from document_parser.app.source_lifecycle import SourceLifecycleService
from document_parser.infra.lifecycle import FileSystemSourceFolder, JsonSourceLifecycleRepository


class FakeParse:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, request):
        self.calls.append(request)
        return SimpleNamespace(
            parse_id=f"parse-{len(self.calls)}",
            package_root=Path("packages") / f"parse-{len(self.calls)}",
            document=SimpleNamespace(provenance=SimpleNamespace(parser_id="fake")),
            quality_package=SimpleNamespace(
                quality_report=SimpleNamespace(state=SimpleNamespace(value="pass"))
            ),
        )


class FailOnceParse(FakeParse):
    def execute(self, request):
        if not self.calls:
            self.calls.append(request)
            raise RuntimeError("temporary failure")
        return super().execute(request)


class FakeDelivery:
    def __init__(self) -> None:
        self.withdrawn = []

    def publish(self, **kwargs):
        return kwargs

    def withdraw(self, source_id, *, reason="source_deleted"):
        self.withdrawn.append((source_id, reason))
        return {"source_id": source_id}

    def relocate(self, source_id, *, filename):
        return {"source_id": source_id, "source_filename": filename}


class FakeMultimodalDelivery(FakeDelivery):
    def publish(self, **kwargs):
        return {"package_path": "mmwiki/package", "state": "ready_for_enrichment"}

    def status(self):
        return {"ready_count": 1, "withdrawn_count": 0, "sources": []}


def build_service(raw, parser, *, delivery=None, multimodal_delivery=None):
    state = raw / ".llmwiki" / ".document_parser"
    return SourceLifecycleService(
        parser,
        sources=FileSystemSourceFolder(raw, excluded_roots=(state,)),
        repository=JsonSourceLifecycleRepository(state),
        delivery=delivery,
        multimodal_delivery=multimodal_delivery,
    )


def test_folder_lifecycle_added_unchanged_modified_moved_deleted(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    source = raw / "a.md"
    source.write_text("one", encoding="utf-8")
    parser = FakeParse()
    service = build_service(raw, parser)

    first = service.scan()
    source_id = first[0].source_id
    assert [event.kind for event in first] == ["added"]
    assert service.scan()[0].kind == "unchanged"

    source.write_text("two", encoding="utf-8")
    modified = service.scan()
    assert [(event.kind, event.source_id) for event in modified] == [("modified", source_id)]

    moved = raw / "nested" / "b.md"
    moved.parent.mkdir()
    source.rename(moved)
    move_events = service.scan()
    assert [(event.kind, event.source_id, event.previous_path) for event in move_events] == [("moved", source_id, "a.md")]

    moved.unlink()
    deleted = service.scan()
    assert [(event.kind, event.source_id) for event in deleted] == [("deleted", source_id)]
    assert len(parser.calls) == 2


def test_failed_source_retries_without_changing_source_id(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "a.md").write_text("one", encoding="utf-8")
    parser = FailOnceParse()
    service = build_service(raw, parser)

    failed = service.scan()[0]
    retried = service.scan()[0]

    assert failed.kind == "added"
    assert failed.error
    assert retried.kind == "retry"
    assert retried.source_id == failed.source_id
    assert retried.error is None


def test_deleted_source_is_withdrawn_from_downstream(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    source = raw / "a.md"
    source.write_text("one", encoding="utf-8")
    delivery = FakeDelivery()
    service = build_service(raw, FakeParse(), delivery=delivery)
    added = service.scan()[0]
    source.unlink()
    deleted = service.scan()[0]
    assert deleted.kind == "deleted"
    assert delivery.withdrawn == [(added.source_id, "source_deleted")]


def test_lifecycle_auto_publishes_multimodal_and_relocates_both_outputs(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    source = raw / "a.md"
    source.write_text("one", encoding="utf-8")
    wiki = FakeDelivery()
    multimodal = FakeMultimodalDelivery()
    service = build_service(raw, FakeParse(), delivery=wiki, multimodal_delivery=multimodal)

    added = service.scan()[0]
    assert added.multimodal_state == "ready_for_enrichment"
    moved = raw / "新名称.md"
    source.rename(moved)
    event = service.scan()[0]

    assert event.kind == "moved"
    assert event.source_id == added.source_id
    assert event.error is None
