"""Opt-in real Docling/MinerU end-to-end verification.

This suite is deliberately disabled by default: it can require local model
artifacts or a server-owned MinerU cloud token.  It invokes the operational
runner instead of mocking either parser or the quality layer.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_SWITCH = "RUN_REAL_PARSER_E2E"
DEFAULT_SOURCE = (
    PROJECT_ROOT
    / "datasets"
    / "shared-dev-v1"
    / "files"
    / "procurement_table_positive.pdf"
)


def _enabled(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _choice(name: str, *, default: str, allowed: set[str]) -> str:
    value = (os.getenv(name) or default).strip().lower()
    if value not in allowed:
        pytest.fail(f"{name} must be one of {sorted(allowed)}, got {value!r}")
    return value


def _timeout_seconds() -> int:
    raw = (os.getenv("REAL_PARSER_E2E_TIMEOUT_SECONDS") or "1800").strip()
    try:
        timeout = int(raw)
    except ValueError:
        pytest.fail("REAL_PARSER_E2E_TIMEOUT_SECONDS must be an integer")
    if timeout < 1:
        pytest.fail("REAL_PARSER_E2E_TIMEOUT_SECONDS must be positive")
    return timeout


def _resolve_source() -> Path:
    raw = os.getenv("REAL_PARSER_E2E_SOURCE")
    source = Path(raw).expanduser() if raw else DEFAULT_SOURCE
    if not source.is_absolute():
        source = (PROJECT_ROOT / source).resolve()
    return source


def _output_dir() -> Path:
    raw = os.getenv("REAL_PARSER_E2E_OUTPUT_DIR")
    output_dir = Path(raw).expanduser() if raw else (
        PROJECT_ROOT / "outputs" / "e2e" / f"pytest-{os.getpid()}-{time.time_ns()}"
    )
    if not output_dir.is_absolute():
        output_dir = (PROJECT_ROOT / output_dir).resolve()
    return output_dir


def _redact(value: str) -> str:
    value = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1<redacted>", value)
    token = os.getenv("MINERU_API_TOKEN")
    return value.replace(token, "<redacted>") if token else value


def _failure_details(completed: subprocess.CompletedProcess[str]) -> str:
    stdout = _redact(completed.stdout[-6000:])
    stderr = _redact(completed.stderr[-6000:])
    return (
        f"runner return code: {completed.returncode}\n"
        f"--- stdout (tail) ---\n{stdout}\n"
        f"--- stderr (tail) ---\n{stderr}"
    )


@pytest.mark.e2e
def test_opt_in_real_parser_run_records_execution_evidence() -> None:
    """Run the actual adapters and quality package only when an operator opts in."""

    if not _enabled(RUN_SWITCH):
        pytest.skip(
            f"real parser E2E is opt-in; set {RUN_SWITCH}=1 to enable this test"
        )

    source = _resolve_source()
    if not source.is_file():
        pytest.fail(f"REAL_PARSER_E2E_SOURCE does not exist: {source}")

    parser_choice = _choice(
        "REAL_PARSER_E2E_PARSER",
        default="all",
        allowed={"all", "docling", "mineru"},
    )
    mineru_mode = _choice(
        "REAL_PARSER_E2E_MINERU_MODE",
        default="local",
        allowed={"local", "cloud", "auto"},
    )
    allow_skips = _enabled("REAL_PARSER_E2E_ALLOW_SKIPS")
    output_dir = _output_dir()
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_real_parser_e2e.py"),
        str(source),
        "--parser",
        parser_choice,
        "--mineru-mode",
        mineru_mode,
        "--output-dir",
        str(output_dir),
    ]
    if _enabled("REAL_PARSER_E2E_ALLOW_MODEL_DOWNLOAD"):
        command.append("--allow-model-download")
    if allow_skips:
        command.append("--allow-skips")

    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_timeout_seconds(),
        )
    except subprocess.TimeoutExpired as error:
        pytest.fail(
            f"real parser E2E exceeded {_timeout_seconds()} seconds; "
            f"partial output: {_redact((error.stdout or '')[-2000:])}"
        )

    summary_path = output_dir / "run-summary.json"
    assert summary_path.is_file(), _failure_details(completed)
    summary: dict[str, Any] = json.loads(summary_path.read_text(encoding="utf-8"))
    records = summary.get("records")
    assert isinstance(records, list) and records, _failure_details(completed)

    expected_ids = {"docling", "mineru"} if parser_choice == "all" else {parser_choice}
    assert {record["parser_id"] for record in records} == expected_ids
    assert summary["dry_run"] is False

    if allow_skips:
        # This is an availability check only.  The summary retains every skip;
        # an operator must not treat it as proof that a parser really executed.
        assert completed.returncode == 0, _failure_details(completed)
        assert {record["outcome"] for record in records} <= {"succeeded", "skipped"}
    else:
        assert completed.returncode == 0, _failure_details(completed)
        assert all(record["outcome"] == "succeeded" for record in records), (
            _failure_details(completed)
        )

    for record in records:
        if record["outcome"] == "skipped":
            assert record.get("skip_reason")
            continue
        assert record["actual_execution"] is True
        assert record.get("execution_engine")
        assert Path(record["parsed_document_path"]).is_file()
        assert Path(record["native_artifacts_path"]).is_file()
        assert Path(record["quality_package_path"]).is_file()
