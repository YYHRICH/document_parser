"""正式 wheel 的包清单、资源和隔离导入回归。"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "quality" / "fixtures" / "parsed_documents" / "sdp-006-fallback.json"


def test_project_metadata_declares_runtime_packages_data_and_extras():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    setuptools = config["tool"]["setuptools"]

    assert {"pydantic>=2.7,<3", "markdown-it-py>=4,<5"}.issubset(
        project["dependencies"]
    )
    assert {"agent", "markitdown", "docling", "dev"}.issubset(
        project["optional-dependencies"]
    )
    assert {"quality.agent.skills", "quality.agent.tools"}.issubset(
        setuptools["packages"]
    )
    assert setuptools["package-data"]["quality.agent.skills"] == ["*.md"]


def test_built_wheel_supports_isolated_public_agent_smoke(tmp_path):
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheelhouse),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel_path = next(wheelhouse.glob("document_parser-*.whl"))

    with zipfile.ZipFile(wheel_path) as archive:
        names = set(archive.namelist())
        assert {
            "document_parser/__init__.py",
            "document_parser/core/package_loader.py",
            "quality/agent/tools/quality_toolbox.py",
            "quality/agent/skills/catalog.py",
            "quality/agent/skills/document_quality_repair.md",
        }.issubset(names)
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = archive.read(metadata_name).decode("utf-8")
        assert "Requires-Dist: pydantic" in metadata
        assert "Requires-Dist: markdown-it-py" in metadata
        assert "Provides-Extra: agent" in metadata
        assert "Provides-Extra: markitdown" in metadata

    installed = tmp_path / "installed"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            str(wheel_path),
            "--no-deps",
            "--target",
            str(installed),
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    smoke = """
from pathlib import Path
import sys

import document_parser
import quality
from document_parser.core.contracts import ParsedDocument
from quality import RepairExecution, run_quality_repair_detailed
from quality.agent import RepairAgentConfig, RepairedDocumentCandidate, load_skill
from quality.agent.tools import QualityToolbox

install_root = Path(sys.argv[2]).resolve()
assert Path(document_parser.__file__).resolve().is_relative_to(install_root)
assert Path(quality.__file__).resolve().is_relative_to(install_root)
assert QualityToolbox
assert "质量" in load_skill("document_quality_repair")

document = ParsedDocument.model_validate_json(Path(sys.argv[1]).read_text(encoding="utf-8"))

class NoOpAgent:
    def run(self, context, *, feedback=None):
        return RepairedDocumentCandidate(
            base_revision=context.revision_id,
            repaired_markdown=None,
            lineage=[context.revision_id],
            reasoning="wheel smoke：无需修改。",
            change_kind="none",
        )

execution = run_quality_repair_detailed(
    document,
    agent=NoOpAgent(),
    agent_config=RepairAgentConfig(max_rounds=1, session_id="wheel-smoke"),
)
assert isinstance(execution, RepairExecution)
assert execution.accepted
assert execution.session_id == "wheel-smoke"
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(installed)
    environment["PYTHONNOUSERSITE"] = "1"
    subprocess.run(
        [sys.executable, "-c", smoke, str(FIXTURE), str(installed)],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
