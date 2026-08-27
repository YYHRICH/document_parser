"""Quality layer can run from a fixture without the document_parser package."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = PROJECT_ROOT / "tests" / "quality" / "fixtures" / "parsed_documents" / "sdp-004-mineru.json"


def test_quality_module_cli_runs_from_project_root_without_parent_package_path() -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [sys.executable, "-m", "quality", "--input", str(FIXTURE), "--json"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    package = json.loads(completed.stdout)
    assert package["schema_name"] == "QualityPackage"
    assert package["document_id"]
    assert package["quality_report"]["state"]


def test_quality_cli_can_show_repair_policy_and_verification_audit() -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality",
            "--input",
            str(FIXTURE),
            "--show-repairs",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "repair_proposals:" in completed.stdout
    assert '"repair_workflow_audit"' in completed.stdout
    assert '"verification"' in completed.stdout
