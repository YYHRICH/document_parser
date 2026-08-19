import base64
import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest

from document_parser import (
    AssetKind,
    BlockKind,
    DocumentAsset,
    DocumentBlock,
    DocumentPackageError,
    NativeArtifact,
    ParseConfidence,
    ParsedDocument,
    ParserProvenance,
    load_document_package,
)


BLOCK_ID = UUID("11111111-1111-4111-8111-111111111111")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _document(native_bytes: bytes, asset_bytes: bytes) -> ParsedDocument:
    return ParsedDocument(
        filename="sample.pdf",
        file_type="application/pdf",
        markdown="正文",
        blocks=[
            DocumentBlock(
                id=BLOCK_ID,
                kind=BlockKind.PARAGRAPH,
                markdown="正文",
            )
        ],
        assets=[
            DocumentAsset(
                path="assets/images/figure-1.png",
                kind=AssetKind.IMAGE,
                file_type="image/png",
                content=asset_bytes,
                sha256=_sha256(asset_bytes),
                referenced_by_block_ids=[str(BLOCK_ID)],
            )
        ],
        confidence=ParseConfidence(),
        provenance=ParserProvenance(parser_id="docling", version="test"),
        native_artifacts=[
            NativeArtifact(
                artifact_id="native-1",
                artifact_type="json",
                path="native/result.json",
                file_type="application/json",
                size_bytes=len(native_bytes),
                sha256=_sha256(native_bytes),
            )
        ],
    )


def _write_package(
    package_dir: Path,
    document: ParsedDocument,
    *,
    write_asset: bool = True,
    omit_asset_content: bool = False,
) -> None:
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "native").mkdir()
    (package_dir / "native" / "result.json").write_bytes(b'{"ok": true}')
    if write_asset:
        asset_path = package_dir / "assets" / "images"
        asset_path.mkdir(parents=True)
        (asset_path / "figure-1.png").write_bytes(b"asset-bytes")

    payload = json.loads(document.model_dump_json())
    if omit_asset_content:
        payload["assets"][0].pop("content")
    (package_dir / "parsed_document.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def test_loads_inline_asset_and_verifies_native_artifact(tmp_path: Path) -> None:
    document = _document(b'{"ok": true}', b"asset-bytes")
    _write_package(tmp_path, document)

    loaded = load_document_package(tmp_path)

    assert loaded.document_id == document.document_id
    assert loaded.assets[0].content == b"asset-bytes"
    assert loaded.native_artifacts[0].sha256 == _sha256(b'{"ok": true}')


def test_hydrates_asset_content_from_sidecar(tmp_path: Path) -> None:
    document = _document(b'{"ok": true}', b"asset-bytes")
    _write_package(tmp_path, document, omit_asset_content=True)

    loaded = load_document_package(tmp_path)

    assert loaded.assets[0].content == b"asset-bytes"


def test_rejects_tampered_native_artifact(tmp_path: Path) -> None:
    document = _document(b'{"ok": true}', b"asset-bytes")
    _write_package(tmp_path, document)
    (tmp_path / "native" / "result.json").write_text("tampered", encoding="utf-8")

    with pytest.raises(DocumentPackageError, match="native artifact"):
        load_document_package(tmp_path)


def test_rejects_unsafe_asset_path_before_reading_sidecar(tmp_path: Path) -> None:
    document = _document(b'{"ok": true}', b"asset-bytes")
    _write_package(tmp_path, document)
    payload = json.loads((tmp_path / "parsed_document.json").read_text(encoding="utf-8"))
    payload["assets"][0]["path"] = "../outside.png"
    payload["assets"][0]["content"] = base64.b64encode(b"asset-bytes").decode()
    (tmp_path / "parsed_document.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    with pytest.raises(DocumentPackageError, match="安全的包内相对路径"):
        load_document_package(tmp_path)
