"""Regression tests for the storage-free orchestration recommendation adapter."""

from __future__ import annotations

import ast
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.core.contracts import ParserCapability  # noqa: E402
from document_parser.orchestration import (  # noqa: E402
    ParseAttemptRecord,
    ParseFailureKind,
    ParseJob,
    ParseJobStatus,
)
from document_parser.composition import (  # noqa: E402
    recommend_reparse_for_job,
    reparse_context_for_job,
    reparse_signals_for_job,
)
from document_parser.routing import ReparseRecommendationPolicy  # noqa: E402


def _capability(
    parser_id: str,
    *,
    requires_network: bool = False,
) -> ParserCapability:
    return ParserCapability(
        parser_id=parser_id,
        provider="fixture",
        display_name=parser_id,
        formats={".pdf"},
        available=True,
        requires_network=requires_network,
    )


def _job(
    *,
    status: ParseJobStatus = ParseJobStatus.QUEUED,
    source_filename: str = "report.pdf",
    requested_parser_id: str | None = "requested-parser",
    attempts: list[ParseAttemptRecord] | None = None,
    quality_state: str | None = None,
    failure_kind: ParseFailureKind | None = None,
    retryable: bool = False,
    options: dict[str, object] | None = None,
) -> ParseJob:
    payload: dict[str, object] = {
        "parse_id": "parent-job-001",
        "source_sha256": "a" * 64,
        "source_filename": source_filename,
        "source_file_type": "application/pdf",
        "source_size_bytes": 42,
        "requested_parser_id": requested_parser_id,
        "attempts": attempts or [],
        "quality_state": quality_state,
        "status": status,
        "failure_kind": failure_kind,
        "retryable": retryable,
        "options": options or {},
    }
    if status == ParseJobStatus.FAILED:
        payload.update(
            {
                "error": "Bearer secret-not-for-recommendations",
                "completed_at": datetime.now(UTC),
            }
        )
    if status == ParseJobStatus.NEEDS_REVIEW:
        payload.update(
            {
                "document_id": uuid4(),
                "package_path": "/published/parent-job-001",
                "completed_at": datetime.now(UTC),
            }
        )
    return ParseJob.model_validate(payload)


def test_reparse_required_job_projects_safe_context_and_quality_signal() -> None:
    job = _job(
        status=ParseJobStatus.NEEDS_REVIEW,
        source_filename=r"incoming\Report.PDF",
        requested_parser_id="requested-parser",
        attempts=[ParseAttemptRecord(parser_id="actual-parser", status="succeeded")],
        quality_state="REPARSE_REQUIRED",
    )

    context = reparse_context_for_job(job)
    signals = reparse_signals_for_job(job)
    result = recommend_reparse_for_job(
        job,
        [_capability("actual-parser"), _capability("alternative-parser")],
        policy=ReparseRecommendationPolicy(priority_parser_ids=("alternative-parser",)),
    )

    assert context.parent_parse_id == job.parse_id
    assert context.source_extension == ".pdf"
    assert context.current_parser_id == "actual-parser"
    assert context.attempted_parser_ids == ("actual-parser",)
    assert [signal.code for signal in signals] == ["reparse-required"]
    assert result is not None
    assert result.automatic is not None
    assert result.automatic.parser_id == "alternative-parser"


def test_retryable_failure_creates_safe_signal_and_can_enable_current_retry_by_policy() -> None:
    job = _job(
        status=ParseJobStatus.FAILED,
        requested_parser_id="failed-parser",
        attempts=[
            ParseAttemptRecord(
                parser_id="failed-parser",
                status="failed",
                failure_kind=ParseFailureKind.TRANSIENT,
                retryable=True,
            )
        ],
        failure_kind=ParseFailureKind.TRANSIENT,
        retryable=True,
    )

    signals = reparse_signals_for_job(job)
    result = recommend_reparse_for_job(
        job,
        [_capability("failed-parser")],
        policy=ReparseRecommendationPolicy(allow_current_parser_retry=True),
    )

    assert len(signals) == 1
    assert signals[0].code == "failure-transient"
    assert signals[0].retryable is True
    assert "secret-not-for-recommendations" not in signals[0].message
    assert result is not None
    assert result.automatic is not None
    assert result.automatic.parser_id == "failed-parser"
    assert result.automatic.options == {"reparse": True}


def test_job_without_quality_or_actionable_failure_signal_returns_none() -> None:
    job = _job(quality_state="pass")

    assert reparse_signals_for_job(job) == ()
    assert recommend_reparse_for_job(job, [_capability("alternative-parser")]) is None


def test_cloud_is_denied_by_default_even_when_job_options_claim_allow_cloud() -> None:
    job = _job(
        status=ParseJobStatus.NEEDS_REVIEW,
        quality_state="reparse_required",
        options={"allow_cloud": True},
    )
    cloud = _capability("cloud-parser", requires_network=True)

    default_result = recommend_reparse_for_job(job, [cloud])
    assert default_result is not None
    assert default_result.automatic is None
    assert default_result.candidates[0].executable is False
    assert "cloud policy" in default_result.candidates[0].reason.lower()

    explicitly_allowed = recommend_reparse_for_job(
        job,
        [cloud],
        policy=ReparseRecommendationPolicy(allow_cloud=True),
    )
    assert explicitly_allowed is not None
    assert explicitly_allowed.automatic is not None
    assert explicitly_allowed.automatic.parser_id == "cloud-parser"


def test_adapter_has_no_quality_package_storage_or_http_dependency() -> None:
    module_path = PROJECT_ROOT / "composition" / "reparse_recommendations.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    forbidden = {"backend", "fastapi", "frontend", "quality", "storage"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (set((node.module or "").split(".")) & forbidden), node.module
        elif isinstance(node, ast.Import):
            for imported in node.names:
                assert not (set(imported.name.split(".")) & forbidden), imported.name

    command = (
        "import sys; import document_parser.composition.reparse_recommendations; "
        "forbidden=('document_parser.backend', 'document_parser.frontend', 'quality'); "
        "assert not any(name == item or name.startswith(item + '.') "
        "for name in sys.modules for item in forbidden)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=PROJECT_ROOT.parent,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
