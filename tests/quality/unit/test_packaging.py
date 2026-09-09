"""三文件质量包序列化、原子写入和结构校验。"""

from pathlib import Path

import pytest

from document_parser.domain.model.contracts import ParsedDocument
from document_parser.app.use_cases import run_quality
from document_parser.infra.quality_packaging import write_quality_package
from document_parser.infra.quality_packaging.artifacts import (
    ISSUES_NAME,
    OPTIMIZED_NAME,
    STRUCTURE_NAME,
    build_package_artifacts,
    verify_package_files,
)
from document_parser.infra.quality_packaging.writer import verify_package_directory

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "quality" / "fixtures" / "parsed_documents"


def _package():
    doc = ParsedDocument.model_validate_json((FIXTURES / "sdp-006-fallback.json").read_text(encoding="utf-8"))
    return run_quality(doc)


def test_build_artifacts_contains_markdown_structure_and_issue_json():
    package = _package()
    artifacts = build_package_artifacts(package)
    assert set(artifacts.files) == {OPTIMIZED_NAME, STRUCTURE_NAME, ISSUES_NAME}
    verify_package_files(artifacts.files)

    structure_json = artifacts.files[STRUCTURE_NAME].decode("utf-8")
    issues_json = artifacts.files[ISSUES_NAME].decode("utf-8")
    assert "optimized_markdown" not in structure_json
    assert "optimized_markdown" not in issues_json
    assert "quality_report" not in structure_json
    assert "canonical_document" not in issues_json
    assert "package_manifest" not in structure_json + issues_json
    assert '"review_summary"' in issues_json
    assert '"review_items"' in issues_json


def test_write_and_verify_package(tmp_path):
    output = write_quality_package(_package(), tmp_path / "package")
    assert output.is_dir()
    assert {p.name for p in output.iterdir()} == {OPTIMIZED_NAME, STRUCTURE_NAME, ISSUES_NAME}
    verify_package_directory(output)


def test_quality_json_tampering_is_detected_as_invalid_json(tmp_path):
    output = write_quality_package(_package(), tmp_path / "package")
    target = output / ISSUES_NAME
    target.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="质量层三文件"):
        verify_package_directory(output)


def test_existing_directory_requires_explicit_replace(tmp_path):
    output = tmp_path / "package"
    output.mkdir()
    (output / "old.txt").write_text("old", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_quality_package(_package(), output)
    write_quality_package(_package(), output, replace_existing=True)
    assert not (output / "old.txt").exists()
    verify_package_directory(output)
