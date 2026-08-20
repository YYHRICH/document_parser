import json
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser import ParsedDocument  # noqa: E402
from document_parser.core import (  # noqa: E402
    DocumentPackageValidationError,
    load_document_package,
    validate_parsed_document_integrity,
    write_document_package,
)


EXAMPLE_DIR = PROJECT_ROOT / "examples" / "contracts"


def load_parsed_payload() -> dict:
    with (EXAMPLE_DIR / "parsed_document.json").open("r", encoding="utf-8") as stream:
        return json.load(stream)


def test_fixed_parsed_document_passes_integrity_check() -> None:
    document = ParsedDocument.model_validate(load_parsed_payload())

    validate_parsed_document_integrity(document)


def test_document_package_loads_when_sidecars_exist(tmp_path: Path) -> None:
    payload = load_parsed_payload()
    package_root = tmp_path / "document_package"
    (package_root / "native" / "images").mkdir(parents=True)
    (package_root / "native" / "content_list.json").write_text("{}", encoding="utf-8")
    (package_root / "native" / "full.md").write_text("# full", encoding="utf-8")
    (package_root / "native" / "images" / "table-001.jpg").write_bytes(b"image")
    (package_root / "parsed_document.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    document = load_document_package(package_root)

    assert document.schema_version == "2.2"
    assert document.tables[0].table_id == "table-001"


def test_write_document_package_materializes_assets_and_source(tmp_path: Path) -> None:
    payload = load_parsed_payload()
    payload["assets"] = [
        {
            "path": "images/figure-1.png",
            "kind": "image",
            "file_type": "image/png",
            "content": "AQID",
            "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "width": 10,
            "height": 10,
            "anchor": None,
            "referenced_by_block_ids": [payload["blocks"][0]["id"]],
            "metadata": {},
        }
    ]
    payload["native_artifacts"] = []
    document = ParsedDocument.model_validate(payload)
    source_path = tmp_path / "original.pdf"
    source_path.write_bytes(b"pdf")
    package_root = tmp_path / "document_package"

    write_document_package(
        document,
        package_root,
        source_path=source_path,
        native_files={"native/images/table-001.jpg": b"table"},
    )

    assert (package_root / "parsed_document.json").is_file()
    assert (package_root / "assets" / "images" / "figure-1.png").is_file()
    assert (package_root / "source" / "original.pdf").is_file()
    assert (package_root / "native" / "images" / "table-001.jpg").is_file()
    loaded = load_document_package(package_root)
    assert loaded.assets[0].path == "images/figure-1.png"


def test_write_document_package_rejects_unsafe_native_file_paths(tmp_path: Path) -> None:
    payload = load_parsed_payload()
    payload["native_artifacts"] = []
    document = ParsedDocument.model_validate(payload)

    with pytest.raises(DocumentPackageValidationError):
        write_document_package(
            document,
            tmp_path / "document_package",
            native_files={"../escape.json": b"{}"},
        )


def test_table_block_reference_must_point_to_table_block() -> None:
    payload = load_parsed_payload()
    payload["tables"][0]["block_id"] = payload["blocks"][0]["id"]
    document = ParsedDocument.model_validate(payload)

    with pytest.raises(DocumentPackageValidationError) as error:
        validate_parsed_document_integrity(document)

    assert "未指向 table block" in str(error.value)


def test_package_validation_rejects_missing_sidecar(tmp_path: Path) -> None:
    package_root = tmp_path / "document_package"
    package_root.mkdir()
    (package_root / "parsed_document.json").write_text(
        json.dumps(load_parsed_payload()),
        encoding="utf-8",
    )

    with pytest.raises(DocumentPackageValidationError) as error:
        load_document_package(package_root)

    assert "侧车文件不存在" in str(error.value)


def test_build_document_package_script(tmp_path: Path) -> None:
    native_dir = tmp_path / "native_input"
    (native_dir / "images").mkdir(parents=True)
    (native_dir / "content_list.json").write_text("{}", encoding="utf-8")
    (native_dir / "full.md").write_text("# full", encoding="utf-8")
    (native_dir / "images" / "table-001.jpg").write_bytes(b"table")
    source_path = tmp_path / "complex-paper.pdf"
    source_path.write_bytes(b"pdf")
    package_root = tmp_path / "document_package"

    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "build_document_package.py"),
            str(EXAMPLE_DIR / "parsed_document.json"),
            str(package_root),
            "--source",
            str(source_path),
            "--native-dir",
            str(native_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert (package_root / "parsed_document.json").is_file()
    assert (package_root / "native" / "content_list.json").is_file()
    assert (package_root / "source" / "original.pdf").is_file()
    assert load_document_package(package_root).filename == "complex-paper.pdf"
