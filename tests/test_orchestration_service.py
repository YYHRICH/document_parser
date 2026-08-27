from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser import (  # noqa: E402
    ParseConfidence,
    ParsedDocument,
    ParseRequest,
    ParserProvenance,
)
from document_parser.core.contracts import FallbackAttempt, QualityState  # noqa: E402
from document_parser.composition.gateway import GatewayParseError  # noqa: E402
from document_parser.orchestration import (  # noqa: E402
    ParseJob,
    ParseJobOrchestrator,
    ParseJobStatus,
)
from quality import run_quality  # noqa: E402


class _MemoryRepository:
    def __init__(self, job: ParseJob, request: ParseRequest) -> None:
        self.job = job
        self.request = request
        self.committed: tuple[ParsedDocument, object, dict[str, bytes]] | None = None

    def load_job(self, parse_id: str) -> ParseJob:
        assert parse_id == self.job.parse_id
        return self.job

    def save_job(self, job: ParseJob) -> ParseJob:
        self.job = job.model_copy(update={"revision": job.revision + 1})
        return self.job

    def load_request(self, parse_id: str) -> ParseRequest:
        assert parse_id == self.job.parse_id
        return self.request

    def commit_completed_job(self, *, job, document, quality_package, native_files) -> str:
        self.committed = (document, quality_package, native_files)
        return f"/published/{job.parse_id}"

    def iter_recoverable_jobs(self):
        return ()


class _SuccessGateway:
    def parse_for_package(self, request: ParseRequest):
        digest = hashlib.sha256(request.content).hexdigest()
        document = ParsedDocument(
            filename=request.filename,
            file_type=request.file_type,
            source_size_bytes=len(request.content),
            source_sha256=digest,
            markdown="# Title\n\nBody.",
            blocks=[],
            confidence=ParseConfidence(),
            provenance=ParserProvenance(
                parser_id="fixture-parser",
                version="1.2.3",
                parse_duration_ms=7,
            ),
        )
        return SimpleNamespace(document=document, native_files={})


class _FailingGateway:
    def parse_for_package(self, request: ParseRequest):
        attempts = [
            FallbackAttempt(
                parser_id="primary",
                status="failed",
                reason="TimeoutError: upstream service timed out",
                duration_ms=11,
                failure_kind="transient",
                retryable=True,
                metrics={"wall_duration_ms": 11},
            ),
            FallbackAttempt(
                parser_id="fallback",
                status="failed",
                reason="RuntimeError: parser exited",
                duration_ms=3,
                failure_kind="parser",
                retryable=False,
                metrics={"wall_duration_ms": 3},
            ),
        ]
        cause = TimeoutError("upstream service timed out")
        error = GatewayParseError(attempts=attempts, causes=[cause], routing_decision=None)
        raise error from cause


def _passing_runner(document: ParsedDocument):
    package = run_quality(document)
    report = package.quality_report.model_copy(update={"state": QualityState.PASS})
    return package.model_copy(update={"quality_report": report})


def _job_and_request() -> tuple[ParseJob, ParseRequest]:
    request = ParseRequest(
        filename="notes.md",
        file_type="text/markdown",
        content=b"# Title\n\nBody.",
        parser_id="fixture-parser",
    )
    job = ParseJob(
        parse_id="fixture-job",
        source_sha256=hashlib.sha256(request.content).hexdigest(),
        source_filename=request.filename,
        source_file_type=request.file_type,
        source_size_bytes=len(request.content),
        requested_parser_id=request.parser_id,
    )
    return job, request


def test_orchestrator_persists_timed_success_attempts_and_events() -> None:
    job, request = _job_and_request()
    repository = _MemoryRepository(job, request)
    completed = ParseJobOrchestrator(
        gateway=_SuccessGateway(),
        repository=repository,
        quality_runner=_passing_runner,
    ).run(job.parse_id)

    assert completed.status == ParseJobStatus.SUCCEEDED
    assert completed.document_id is not None
    assert completed.package_path == "/published/fixture-job"
    assert completed.quality_state == QualityState.PASS.value
    assert len(completed.attempts) == 1
    attempt = completed.attempts[0]
    assert attempt.status == "succeeded"
    assert attempt.started_at is not None
    assert attempt.completed_at is not None
    assert attempt.completed_at >= attempt.started_at
    assert attempt.parameters_fingerprint
    assert attempt.metrics["wall_duration_ms"] >= 0
    assert [event.status for event in completed.events] == [
        ParseJobStatus.PREFLIGHT,
        ParseJobStatus.PARSING,
        ParseJobStatus.NORMALIZING,
        ParseJobStatus.QUALITY_CHECKING,
        ParseJobStatus.SUCCEEDED,
    ]
    assert repository.committed is not None


def test_orchestrator_persists_gateway_failure_attempts_with_safe_error() -> None:
    job, request = _job_and_request()
    repository = _MemoryRepository(job, request)
    completed = ParseJobOrchestrator(
        gateway=_FailingGateway(),
        repository=repository,
        quality_runner=run_quality,
    ).run(job.parse_id)

    assert completed.status == ParseJobStatus.FAILED
    assert completed.failure_kind is not None
    assert completed.retryable is True
    assert completed.error == "The parser service is temporarily unavailable; retry is safe."
    assert completed.error_reference
    assert [attempt.parser_id for attempt in completed.attempts] == ["primary", "fallback"]
    assert completed.attempts[0].failure_kind.value == "transient"
    assert completed.attempts[0].retryable is True
    assert completed.events[-1].status == ParseJobStatus.FAILED


def test_quality_review_completes_without_losing_published_document() -> None:
    job, request = _job_and_request()
    repository = _MemoryRepository(job, request)

    def review_runner(document: ParsedDocument):
        package = run_quality(document)
        report = package.quality_report.model_copy(
            update={"state": QualityState.MANUAL_REVIEW_REQUIRED}
        )
        return package.model_copy(update={"quality_report": report})

    completed = ParseJobOrchestrator(
        gateway=_SuccessGateway(),
        repository=repository,
        quality_runner=review_runner,
    ).run(job.parse_id)

    assert completed.status == ParseJobStatus.SUCCEEDED
    assert completed.document_id is not None
    assert completed.package_path == "/published/fixture-job"
    assert completed.quality_state == QualityState.MANUAL_REVIEW_REQUIRED.value
    assert repository.committed is not None


def test_orchestrator_does_not_replay_an_already_claimed_job() -> None:
    job, request = _job_and_request()
    claimed = job.transition(ParseJobStatus.PREFLIGHT)
    repository = _MemoryRepository(claimed, request)
    result = ParseJobOrchestrator(
        gateway=_FailingGateway(),
        repository=repository,
        quality_runner=run_quality,
    ).run(job.parse_id)

    assert result.status == ParseJobStatus.PREFLIGHT
    assert result.events == claimed.events
