from __future__ import annotations

import hashlib
import multiprocessing
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from uuid import uuid4

import pytest

from document_parser.backend import storage as storage_module
from document_parser.backend.storage import (
    ApiStorage,
    ArtifactManifestError,
    SourceIntegrityError,
    _quality_run_id,
)
from document_parser.core.contracts import (
    BlockKind,
    DocumentBlock,
    EvidenceAvailability,
    EvidenceCapability,
    PackageManifest,
    ParseConfidence,
    ParsedDocument,
    ParserProvenance,
    SourceAnchor,
)
from document_parser.orchestration.models import JobConflictError, ParseJobStatus
from quality import run_quality



def _save_job_from_second_process(
    root: str,
    parse_id: str,
    start_event,
    result_queue,
) -> None:
    """Spawn-safe helper: both children load revision 0 before attempting CAS."""

    storage = ApiStorage(Path(root))
    job = storage.load_job(parse_id)
    result_queue.put("ready")
    if not start_event.wait(timeout=15):
        result_queue.put("timeout")
        return
    try:
        storage.save_job(job.transition(ParseJobStatus.PREFLIGHT))
    except JobConflictError:
        result_queue.put("conflict")
    else:
        result_queue.put("saved")


def _document(source: bytes, *, filename: str = "notes.md") -> ParsedDocument:
    source_sha256 = hashlib.sha256(source).hexdigest()
    return ParsedDocument(
        filename=filename,
        file_type="text/markdown",
        source_size_bytes=len(source),
        source_sha256=source_sha256,
        markdown="# Title\n\nBody.",
        blocks=[
            DocumentBlock(
                source_block_id="title",
                order_index=0,
                kind=BlockKind.HEADING,
                text="Title",
                heading_level=1,
                markdown="# Title",
                anchor=SourceAnchor(page_number=1),
            ),
            DocumentBlock(
                source_block_id="body",
                order_index=1,
                kind=BlockKind.PARAGRAPH,
                text="Body.",
                markdown="Body.",
                anchor=SourceAnchor(page_number=1),
            ),
        ],
        confidence=ParseConfidence(),
        provenance=ParserProvenance(parser_id="storage-test"),
        capabilities={
            "page_bbox": EvidenceCapability(
                state=EvidenceAvailability.AVAILABLE,
                granularity="block",
            )
        },
    )


def _committed(storage: ApiStorage, *, parse_id: str = "parse-one"):
    source = b"# Title\n\nBody."
    job = storage.create_job(
        parse_id=parse_id,
        source_filename="notes.md",
        source_file_type="text/markdown",
        source_content=source,
        requested_parser_id="docling",
        options={"language": "en"},
    )
    document = _document(source)
    quality = run_quality(document)
    storage.commit_completed_job(
        job=job,
        document=document,
        quality_package=quality,
        native_files={"native/evidence.json": b'{"kind":"fixture"}'},
    )
    return job, document, quality


def test_manifest_exactly_covers_published_files_and_only_registered_files_are_exposed(tmp_path: Path):
    storage = ApiStorage(tmp_path)
    job, _, _ = _committed(storage)
    package_root = storage.package_root(job.parse_id)

    manifest = json.loads((package_root / "artifact_manifest.json").read_text(encoding="utf-8"))
    actual = {
        item.relative_to(package_root).as_posix()
        for item in package_root.rglob("*")
        if item.is_file() and item.name != "artifact_manifest.json"
    }
    assert set(manifest["artifacts"]) == actual

    listed = storage.list_package_files(job.parse_id)
    listed_paths = {item["path"] for item in listed}
    assert listed_paths == actual
    assert "artifact_manifest.json" not in listed_paths
    assert {path.relative_to(package_root) for path in storage.registered_package_files(job.parse_id)} == {
        Path(item) for item in actual
    }
    assert storage.resolve_package_file(job.parse_id, "native/evidence.json").is_file()
    with pytest.raises(FileNotFoundError):
        storage.resolve_package_file(job.parse_id, "artifact_manifest.json")

    (package_root / "unregistered.txt").write_text("not authorized", encoding="utf-8")
    with pytest.raises(ArtifactManifestError, match="unregistered"):
        storage.list_package_files(job.parse_id)
    with pytest.raises(ArtifactManifestError, match="unregistered"):
        storage.resolve_package_file(job.parse_id, "parsed_document.json")


@pytest.mark.parametrize("mutation", ["missing", "tampered"])
def test_manifest_rejects_missing_and_tampered_registered_files(tmp_path: Path, mutation: str):
    storage = ApiStorage(tmp_path)
    job, _, _ = _committed(storage, parse_id=f"parse-{mutation}")
    artifact = storage.package_root(job.parse_id) / "native" / "evidence.json"
    if mutation == "missing":
        artifact.unlink()
        expected = "missing"
    else:
        artifact.write_bytes(b"changed")
        expected = "integrity"

    with pytest.raises(ArtifactManifestError, match=expected):
        storage.verify_artifact_manifest(storage.package_root(job.parse_id), require_manifest=True)


def test_load_request_rechecks_persisted_source_hash_and_size(tmp_path: Path):
    storage = ApiStorage(tmp_path)
    job = storage.create_job(
        parse_id="source-check",
        source_filename="notes.md",
        source_file_type="text/markdown",
        source_content=b"original",
        requested_parser_id="docling",
        options={},
    )
    storage.job_source_path(job.parse_id).write_bytes(b"tampered")

    with pytest.raises(SourceIntegrityError, match="source integrity"):
        storage.load_request(job.parse_id)


def test_commit_rejects_document_or_quality_identity_that_does_not_match_job(tmp_path: Path):
    storage = ApiStorage(tmp_path)
    source = b"# Title\n\nBody."
    job = storage.create_job(
        parse_id="identity-check",
        source_filename="notes.md",
        source_file_type="text/markdown",
        source_content=source,
        requested_parser_id="docling",
        options={},
    )
    document = _document(source)
    quality = run_quality(document)

    with pytest.raises(SourceIntegrityError, match="source identity"):
        storage.commit_completed_job(
            job=job,
            document=document.model_copy(update={"source_sha256": "a" * 64}),
            quality_package=quality,
            native_files={},
        )
    with pytest.raises(SourceIntegrityError, match="Quality package document_id"):
        storage.commit_completed_job(
            job=job,
            document=document,
            quality_package=quality.model_copy(update={"document_id": uuid4()}),
            native_files={},
        )


def test_completed_package_publishes_quality_four_pack_with_matching_hashes(tmp_path: Path):
    storage = ApiStorage(tmp_path)
    job, _, quality = _committed(storage)
    package_root = storage.package_root(job.parse_id)
    core_artifacts = {
        "optimized.md",
        "canonical_document.json",
        "quality_report.json",
    }
    published_artifacts = {*core_artifacts, "package_manifest.json"}

    assert all((package_root / name).is_file() for name in published_artifacts)
    assert set(quality.package_manifest.artifacts) == core_artifacts
    for artifact_path in core_artifacts:
        digest = hashlib.sha256((package_root / artifact_path).read_bytes()).hexdigest()
        assert digest == quality.package_manifest.artifacts[artifact_path]

    package_manifest = json.loads(
        (package_root / "package_manifest.json").read_text(encoding="utf-8")
    )
    assert package_manifest["artifacts"] == quality.package_manifest.artifacts
    assert storage.load_quality_package(job.parse_id).package_manifest.artifacts == quality.package_manifest.artifacts
    listed_paths = {item["path"] for item in storage.list_package_files(job.parse_id)}
    assert published_artifacts <= listed_paths


def test_quality_rewrite_rejects_forged_manifest_without_corrupting_published_package(tmp_path: Path):
    storage = ApiStorage(tmp_path)
    job, _, quality = _committed(storage)
    package_root = storage.package_root(job.parse_id)
    original_quality_bytes = storage.quality_package_path(job.parse_id).read_bytes()
    forged_hashes = dict(quality.package_manifest.artifacts)
    forged_hashes["optimized.md"] = "a" * 64
    forged_quality = quality.model_copy(
        update={"package_manifest": PackageManifest(artifacts=forged_hashes)}
    )

    with pytest.raises(SourceIntegrityError, match="valid four-artifact"):
        storage.write_quality_package(job.parse_id, forged_quality)

    assert storage.quality_package_path(job.parse_id).read_bytes() == original_quality_bytes
    assert storage.load_quality_package(job.parse_id).package_manifest.artifacts == quality.package_manifest.artifacts
    storage.verify_artifact_manifest(package_root, require_manifest=True)


def test_quality_rewrite_refreshes_revision_and_outer_manifest_together(tmp_path: Path):
    storage = ApiStorage(tmp_path)
    job, document, quality = _committed(storage)

    storage.write_quality_package(job.parse_id, quality)
    revision = json.loads(
        (storage.package_root(job.parse_id) / "revision.json").read_text(encoding="utf-8")
    )
    assert revision["document_id"] == str(document.document_id)
    assert revision["source_sha256"] == document.source_sha256
    assert revision["source_size_bytes"] == document.source_size_bytes
    assert revision["quality_run_id"] == _quality_run_id(quality)
    assert storage.load_quality_package(job.parse_id).package_manifest.artifacts == quality.package_manifest.artifacts
    storage.verify_artifact_manifest(storage.package_root(job.parse_id), require_manifest=True)


def test_save_job_uses_revision_compare_and_swap(tmp_path: Path):
    storage = ApiStorage(tmp_path)
    initial = storage.create_job(
        parse_id="job-cas",
        source_filename="notes.md",
        source_file_type="text/markdown",
        source_content=b"source",
        requested_parser_id="docling",
        options={},
    )
    stale = storage.load_job(initial.parse_id)
    current = storage.save_job(initial.transition(ParseJobStatus.PREFLIGHT))
    assert current.revision == initial.revision + 1
    with pytest.raises(JobConflictError, match="reload"):
        storage.save_job(stale.transition(ParseJobStatus.PREFLIGHT))


def test_atomic_replace_retries_short_windows_permission_error(tmp_path: Path, monkeypatch):
    target = tmp_path / "atomic.txt"
    original_replace = storage_module.os.replace
    attempts = 0

    def flaky_replace(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError("sharing violation")
        return original_replace(source, destination)

    monkeypatch.setattr(storage_module.os, "replace", flaky_replace)
    ApiStorage._write_text_atomic(target, "ok")
    assert attempts == 2
    assert target.read_text(encoding="utf-8") == "ok"


def test_load_job_serializes_reader_against_atomic_job_replace(tmp_path: Path, monkeypatch):
    storage = ApiStorage(tmp_path)
    initial = storage.create_job(
        parse_id="read-lock",
        source_filename="notes.md",
        source_file_type="text/markdown",
        source_content=b"source",
        requested_parser_id="docling",
        options={},
    )
    writer_started = threading.Event()
    release_writer = threading.Event()
    reader_finished = threading.Event()
    writer_errors: list[BaseException] = []
    reader_errors: list[BaseException] = []
    read_results = []
    original_write = ApiStorage._write_text_atomic

    def hold_atomic_replace(path: Path, content: str) -> None:
        if path == storage.job_path(initial.parse_id):
            writer_started.set()
            assert release_writer.wait(timeout=5)
        original_write(path, content)

    monkeypatch.setattr(
        ApiStorage,
        "_write_text_atomic",
        staticmethod(hold_atomic_replace),
    )

    def save_transition() -> None:
        try:
            storage.save_job(initial.transition(ParseJobStatus.PREFLIGHT))
        except BaseException as error:
            writer_errors.append(error)

    def read_current_job() -> None:
        try:
            read_results.append(storage.load_job(initial.parse_id))
        except BaseException as error:
            reader_errors.append(error)
        finally:
            reader_finished.set()

    writer = threading.Thread(target=save_transition)
    reader = threading.Thread(target=read_current_job)
    writer.start()
    assert writer_started.wait(timeout=5)
    reader.start()
    try:
        # The read must wait for the writer's per-job lock rather than opening the
        # replace target and observing an old revision (or a Windows sharing error).
        assert not reader_finished.wait(timeout=0.15)
    finally:
        release_writer.set()
    writer.join(timeout=5)
    reader.join(timeout=5)

    assert not writer.is_alive()
    assert not reader.is_alive()
    assert not writer_errors
    assert not reader_errors
    assert len(read_results) == 1
    assert read_results[0].status == ParseJobStatus.PREFLIGHT
    assert read_results[0].revision == initial.revision + 1


def test_legacy_document_package_remains_readable_without_a_manifest(tmp_path: Path):
    storage = ApiStorage(tmp_path)
    source = b"# Title\n\nBody."
    document = _document(source)
    package_root = storage.package_root("legacy")
    from document_parser.core import write_document_package

    write_document_package(document, package_root)
    loaded = storage.load_document("legacy")
    assert loaded.document_id == document.document_id


@pytest.mark.parametrize(
    "bad_path",
    [
        "parsed_document.json",
        "revision.json",
        "artifact_manifest.json",
        "assets/overwritten.bin",
        "native/../parsed_document.json",
    ],
)
def test_native_sidecars_cannot_write_storage_owned_package_paths(tmp_path: Path, bad_path: str):
    storage = ApiStorage(tmp_path)
    source = b"# Title\n\nBody."
    document = _document(source)
    with pytest.raises(ValueError, match="Native sidecars"):
        storage.write_parse_package(
            parse_id="native-compat",
            document=document,
            source_filename="notes.md",
            source_content=source,
            native_files={bad_path: b"forbidden"},
        )

    job = storage.create_job(
        parse_id="native-commit",
        source_filename="notes.md",
        source_file_type="text/markdown",
        source_content=source,
        requested_parser_id="docling",
        options={},
    )
    with pytest.raises(ValueError, match="Native sidecars"):
        storage.commit_completed_job(
            job=job,
            document=document,
            quality_package=run_quality(document),
            native_files={bad_path: b"forbidden"},
        )


def test_idempotency_lookup_and_create_are_serialized_across_threads(tmp_path: Path):
    start = __import__("threading").Barrier(2)

    def create(index: int) -> str:
        start.wait(timeout=10)
        job = ApiStorage(tmp_path).create_job(
            parse_id=f"idem-{index}",
            source_filename="notes.md",
            source_file_type="text/markdown",
            source_content=b"same source",
            requested_parser_id="docling",
            options={"language": "en"},
            idempotency_key="same-key",
        )
        return job.parse_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        parse_ids = list(executor.map(create, range(2)))
    assert parse_ids[0] == parse_ids[1]
    assert len(tuple(ApiStorage(tmp_path).iter_jobs())) == 1


def test_job_compare_and_swap_is_serialized_across_processes(tmp_path: Path):
    storage = ApiStorage(tmp_path)
    initial = storage.create_job(
        parse_id="process-cas",
        source_filename="notes.md",
        source_file_type="text/markdown",
        source_content=b"source",
        requested_parser_id="docling",
        options={},
    )
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    result_queue = context.Queue()
    workers = [
        context.Process(
            target=_save_job_from_second_process,
            args=(str(tmp_path), initial.parse_id, start_event, result_queue),
        )
        for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    assert [result_queue.get(timeout=20) for _ in workers] == ["ready", "ready"]
    start_event.set()
    outcomes = [result_queue.get(timeout=20) for _ in workers]
    for worker in workers:
        worker.join(timeout=20)
        assert worker.exitcode == 0
    assert sorted(outcomes) == ["conflict", "saved"]
    assert storage.load_job(initial.parse_id).revision == 1


def test_dead_stale_file_lock_is_reaped_without_deleting_a_live_owner(tmp_path: Path):
    lock_path = tmp_path / "dead.lock"
    lock_path.write_text('{"owner":"dead","pid":999999,"created_at":0}', encoding="utf-8")
    stale_at = time.time() - storage_module._LOCK_STALE_SECONDS - 1
    os.utime(lock_path, (stale_at, stale_at))

    with storage_module._exclusive_file_lock(lock_path):
        assert lock_path.is_file()
    assert not lock_path.exists()



def test_owned_file_lock_release_retries_short_windows_sharing_violation(tmp_path: Path, monkeypatch):
    lock_path = tmp_path / "release.lock"
    original_unlink = storage_module.os.unlink
    attempts = 0

    def flaky_unlink(candidate, *args, **kwargs):
        nonlocal attempts
        if Path(candidate) == lock_path and attempts < 2:
            attempts += 1
            raise PermissionError("sharing violation")
        return original_unlink(candidate, *args, **kwargs)

    monkeypatch.setattr(storage_module.os, "unlink", flaky_unlink)
    with storage_module._exclusive_file_lock(lock_path):
        assert lock_path.is_file()
    assert attempts == 2
    assert not lock_path.exists()


def test_retry_creation_is_idempotent_and_serialized_across_threads(tmp_path: Path):
    storage = ApiStorage(tmp_path)
    source = b"# Retry source\n\nBody."
    parent = storage.create_job(
        parse_id="retry-parent",
        source_filename="retry.md",
        source_file_type="text/markdown",
        source_content=source,
        requested_parser_id="docling",
        options={"language": "en"},
    )
    parent = storage.save_job(
        parent.transition(
            ParseJobStatus.FAILED,
            error="Temporary parser service interruption.",
            failure_kind="transient",
            retryable=True,
        )
    )
    start = __import__("threading").Barrier(2)

    def create_retry() -> tuple[str, bool]:
        start.wait(timeout=10)
        result = ApiStorage(tmp_path).create_retry_job(
            parent_parse_id=parent.parse_id,
            idempotency_key="retry-thread-key",
        )
        return result.job.parse_id, result.created

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create_retry(), range(2)))

    child_ids = {parse_id for parse_id, _ in results}
    assert len(child_ids) == 1
    assert sorted(created for _, created in results) == [False, True]
    child = storage.load_job(child_ids.pop())
    assert child.parent_parse_id == parent.parse_id
    assert child.source_sha256 == parent.source_sha256
    assert child.source_size_bytes == parent.source_size_bytes
    assert storage.job_source_path(child.parse_id).read_bytes() == source
    assert len(tuple(storage.iter_jobs())) == 2

