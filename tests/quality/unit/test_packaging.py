"""双文件质量包序列化、原子写入和结构校验。"""

from pathlib import Path

import pytest

from document_parser.domain.model.contracts import ParsedDocument
from document_parser.app.use_cases import run_quality
from document_parser.infra.quality_packaging import write_quality_package
from document_parser.infra.quality_packaging.artifacts import (
    OPTIMIZED_NAME,
    QUALITY_NAME,
    build_package_artifacts,
    verify_package_files,
)
from document_parser.infra.quality_packaging.writer import verify_package_directory

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "quality" / "fixtures" / "parsed_documents"


def _package():
    doc = ParsedDocument.model_validate_json((FIXTURES / "sdp-006-fallback.json").read_text(encoding="utf-8"))
    return run_quality(doc)


def test_build_artifacts_contains_only_markdown_and_json():
    package = _package()
    artifacts = build_package_artifacts(package)
    assert set(artifacts.files) == {OPTIMIZED_NAME, QUALITY_NAME}
    verify_package_files(artifacts.files)

    quality_json = artifacts.files[QUALITY_NAME].decode("utf-8")
    assert "optimized_markdown" not in quality_json
    assert "package_manifest" not in quality_json
    assert "sha256" not in quality_json


def test_write_and_verify_package(tmp_path):
    output = write_quality_package(_package(), tmp_path / "package")
    assert output.is_dir()
    assert {p.name for p in output.iterdir()} == {OPTIMIZED_NAME, QUALITY_NAME}
    verify_package_directory(output)


def test_quality_json_tampering_is_detected_as_invalid_json(tmp_path):
    output = write_quality_package(_package(), tmp_path / "package")
    target = output / QUALITY_NAME
    target.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="quality_package"):
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
