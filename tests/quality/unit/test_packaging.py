"""M5 四件套序列化、原子写入和篡改校验。"""

from pathlib import Path

import pytest

from document_parser.domain.model.contracts import ParsedDocument
from document_parser.app.use_cases import run_quality
from document_parser.infra.quality_packaging import write_quality_package
from document_parser.infra.quality_packaging.artifacts import (
    MANIFEST_NAME,
    build_package_artifacts,
    verify_package_files,
)
from document_parser.infra.quality_packaging.writer import verify_package_directory

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "quality" / "fixtures" / "parsed_documents"


def _package():
    doc = ParsedDocument.model_validate_json((FIXTURES / "sdp-006-fallback.json").read_text(encoding="utf-8"))
    return run_quality(doc)


def test_build_artifacts_matches_manifest():
    package = _package()
    artifacts = build_package_artifacts(package)
    assert set(artifacts.files) == {"optimized.md", "canonical_document.json", "quality_report.json", MANIFEST_NAME}
    assert artifacts.manifest.artifacts == package.package_manifest.artifacts
    verify_package_files(artifacts.files)


def test_write_and_verify_package(tmp_path):
    output = write_quality_package(_package(), tmp_path / "package")
    assert output.is_dir()
    assert {p.name for p in output.iterdir()} == {"optimized.md", "canonical_document.json", "quality_report.json", MANIFEST_NAME}
    verify_package_directory(output)


def test_tampered_package_is_rejected(tmp_path):
    output = write_quality_package(_package(), tmp_path / "package")
    target = output / "optimized.md"
    target.write_bytes(target.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="manifest"):
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
