"""Deliver quality-approved parser output to a mobilework Wiki checkout."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from ...domain.model.contracts import ParsedDocument, QualityPackage, QualityState


class DeliveryRejectedError(ValueError):
    """The candidate must not replace a previously published Wiki source."""


class MobileworkDeliveryAdapter:
    """Materialize one parser Source in mobilework's existing ``raw`` contract.

    mobilework watches only ``raw/sources/*.md``.  Stable filenames turn parser
    modifications into Wiki ``modified`` events and source withdrawal into
    ``deleted`` without coupling either side's private manifest.
    """

    _SOURCE_ID = re.compile(r"^src_[A-Za-z0-9_-]{4,128}$")
    _ALLOWED_STATES = {QualityState.PASS, QualityState.PASS_WITH_WARNINGS}

    def __init__(self, mobilework_root: Path | str) -> None:
        self.root = Path(mobilework_root)
        self.raw = self.root / "raw"
        self.sources = self.raw / "sources"
        self.assets = self.raw / "assets"
        self.metadata = self.raw / "metadata"
        self.state = self.raw / ".llmwiki" / ".document_parser"
        self.manifest_path = self.state / "delivery-manifest.json"

    def publish(
        self,
        *,
        source_id: str,
        parse_id: str,
        document: ParsedDocument,
        quality_package: QualityPackage,
    ) -> dict[str, Any]:
        self._validate_identity(source_id, parse_id)
        if document.document_id != quality_package.document_id:
            raise DeliveryRejectedError("ParsedDocument 与 QualityPackage 的 document_id 不一致。")
        state = quality_package.quality_report.state
        if state not in self._ALLOWED_STATES:
            raise DeliveryRejectedError(f"质量状态 {state.value} 不允许发布到 Wiki。")
        markdown = quality_package.optimized_markdown.strip()
        if not markdown:
            raise DeliveryRejectedError("空 Markdown 不允许发布到 Wiki。")

        source_asset_root = self.assets / source_id
        asset_rows: list[dict[str, Any]] = []
        rewritten = markdown
        for asset in document.assets:
            relative = self._safe_relative(asset.path)
            actual_sha = hashlib.sha256(asset.content).hexdigest()
            if asset.sha256 is not None and asset.sha256 != actual_sha:
                raise DeliveryRejectedError(f"资源 SHA-256 不匹配：{asset.path}")
            destination = source_asset_root / relative
            self._atomic_bytes(destination, asset.content)
            wiki_reference = (PurePosixPath("..") / "assets" / source_id / relative).as_posix()
            rewritten = self._rewrite_asset_reference(rewritten, asset.path, wiki_reference)
            asset_rows.append(
                {
                    "path": (PurePosixPath("assets") / source_id / relative).as_posix(),
                    "source_path": asset.path,
                    "kind": asset.kind.value,
                    "file_type": asset.file_type,
                    "sha256": actual_sha,
                    "size_bytes": len(asset.content),
                    "referenced_by_block_ids": list(asset.referenced_by_block_ids),
                    "page_number": asset.anchor.page_number if asset.anchor else None,
                    "bbox": list(asset.anchor.bbox) if asset.anchor and asset.anchor.bbox else None,
                    "metadata": asset.metadata,
                }
            )

        asset_manifest_sha = hashlib.sha256(
            json.dumps(asset_rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        marker = {
            "schema": "document-parser-mobilework/1.0",
            "parser_source_id": source_id,
            "parse_id": parse_id,
            "document_id": str(document.document_id),
            "parser_id": document.provenance.parser_id,
            "quality_state": state.value,
            "source_filename": document.filename,
            "source_sha256": document.source_sha256,
            "assets_manifest_sha256": asset_manifest_sha,
        }
        delivered_markdown = (
            f"<!-- document-parser: {json.dumps(marker, ensure_ascii=False, sort_keys=True)} -->\n\n"
            f"{rewritten.rstrip()}\n"
        )
        manifest = self._manifest()
        source_path = self.sources / self._visible_source_name(
            document.filename, source_id, manifest
        )
        self._atomic_text(source_path, delivered_markdown)

        # 文件重命名后撤下旧路径。写入新文件成功后再删除，避免发布失败丢失旧版本。
        previous = manifest["sources"].get(source_id, {})
        previous_relative = previous.get("source_path")
        if isinstance(previous_relative, str):
            previous_path = self.root / PurePosixPath(previous_relative)
            if previous_path != source_path:
                previous_path.unlink(missing_ok=True)

        metadata_root = self.metadata / source_id
        self._atomic_json(metadata_root / "assets.json", {"assets": asset_rows, "sha256": asset_manifest_sha})
        quality_payload = quality_package.model_dump(mode="json", exclude={"optimized_markdown"})
        self._atomic_json(metadata_root / "quality_package.json", quality_payload)
        delivery = {
            **marker,
            "state": "active",
            "source_path": source_path.relative_to(self.root).as_posix(),
            "assets_path": source_asset_root.relative_to(self.root).as_posix(),
            "quality_package_path": (metadata_root / "quality_package.json").relative_to(self.root).as_posix(),
            "published_at": datetime.now(UTC).isoformat(),
        }
        self._atomic_json(metadata_root / "delivery.json", delivery)
        manifest["sources"][source_id] = delivery
        manifest["updated_at"] = datetime.now(UTC).isoformat()
        self._atomic_json(self.manifest_path, manifest)
        return delivery

    def withdraw(self, source_id: str, *, reason: str = "source_deleted") -> dict[str, Any]:
        self._validate_identity(source_id, "withdraw")
        manifest = self._manifest()
        previous = manifest["sources"].get(source_id, {})
        source_relative = previous.get("source_path")
        if isinstance(source_relative, str):
            source_path = self.root / PurePosixPath(source_relative)
        else:
            # 兼容 1.0 旧 manifest。
            source_path = self.sources / f"{source_id}.md"
        source_path.unlink(missing_ok=True)
        record = {
            **previous,
            "parser_source_id": source_id,
            "state": "deleted",
            "withdraw_reason": reason,
            "withdrawn_at": datetime.now(UTC).isoformat(),
        }
        manifest["sources"][source_id] = record
        manifest["updated_at"] = datetime.now(UTC).isoformat()
        self._atomic_json(self.manifest_path, manifest)
        self._atomic_json(self.metadata / source_id / "delivery.json", record)
        return record

    def relocate(self, source_id: str, *, filename: str) -> dict[str, Any]:
        """只移动展示文件名；内容和 Source 身份保持不变。"""

        self._validate_identity(source_id, "relocate")
        manifest = self._manifest()
        previous = manifest["sources"].get(source_id)
        if not isinstance(previous, dict) or previous.get("state") != "active":
            raise FileNotFoundError(f"找不到可移动的 Wiki Source：{source_id}")
        previous_relative = str(previous.get("source_path") or "")
        previous_path = self.root / self._safe_relative(previous_relative)
        if not previous_path.is_file():
            raise FileNotFoundError(previous_path)
        target = self.sources / self._visible_source_name(filename, source_id, manifest)
        if previous_path != target:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(previous_path, target)
        record = {
            **previous,
            "source_filename": filename,
            "source_path": target.relative_to(self.root).as_posix(),
            "relocated_at": datetime.now(UTC).isoformat(),
        }
        manifest["sources"][source_id] = record
        manifest["updated_at"] = datetime.now(UTC).isoformat()
        self._atomic_json(self.manifest_path, manifest)
        self._atomic_json(self.metadata / source_id / "delivery.json", record)
        return record

    def status(self) -> dict[str, Any]:
        """Return a read-only delivery snapshot for operations and demos."""
        manifest = self._manifest()
        sources = list(manifest["sources"].values())
        return {
            "root": str(self.root.resolve()),
            "watched_sources_root": str(self.sources.resolve()),
            "manifest_path": str(self.manifest_path.resolve()),
            "active_count": sum(item.get("state") == "active" for item in sources),
            "deleted_count": sum(item.get("state") == "deleted" for item in sources),
            "sources": sorted(sources, key=lambda item: str(item.get("parser_source_id", ""))),
        }

    def _manifest(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            return {"schema_name": "MobileworkDeliveryManifest", "version": 1, "sources": {}}
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if payload.get("version") != 1 or not isinstance(payload.get("sources"), dict):
            raise ValueError(f"不支持的交付 manifest：{self.manifest_path}")
        return payload

    @classmethod
    def _validate_identity(cls, source_id: str, parse_id: str) -> None:
        if not cls._SOURCE_ID.fullmatch(source_id):
            raise ValueError("source_id 必须是安全的 src_ 标识。")
        if not parse_id or any(character in parse_id for character in "/\\:"):
            raise ValueError("parse_id 不是安全标识。")

    @staticmethod
    def _safe_relative(value: str) -> PurePosixPath:
        normalized = value.replace("\\", "/").strip()
        path = PurePosixPath(normalized)
        if not normalized or path.is_absolute() or ".." in path.parts:
            raise DeliveryRejectedError(f"不安全的资源路径：{value}")
        return path

    @staticmethod
    def _visible_source_name(
        filename: str, source_id: str, manifest: dict[str, Any]
    ) -> str:
        """生成用户可读且不会覆盖其他 Source 的 Markdown 文件名。"""

        basename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
        stem = Path(basename).stem.strip(" .")
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem).strip(" .")
        if not stem:
            stem = "未命名文档"
        candidate = f"{stem}.md"
        occupied = {
            str(record.get("source_path", "")).casefold()
            for existing_id, record in manifest.get("sources", {}).items()
            if existing_id != source_id and record.get("state") == "active"
        }
        relative = (PurePosixPath("raw/sources") / candidate).as_posix()
        if relative.casefold() in occupied:
            candidate = f"{stem}--{source_id.removeprefix('src_')[:8]}.md"
        return candidate

    @staticmethod
    def _rewrite_asset_reference(markdown: str, old: str, new: str) -> str:
        variants = {old, old.replace("\\", "/")}
        for value in variants:
            markdown = markdown.replace(f"]({value})", f"]({new})")
            markdown = markdown.replace(f']({value} "', f']({new} "')
            markdown = markdown.replace(f'src="{value}"', f'src="{new}"')
            markdown = markdown.replace(f"src='{value}'", f"src='{new}'")
        return markdown

    @staticmethod
    def _atomic_bytes(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
            os.replace(temporary, path)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise

    @classmethod
    def _atomic_text(cls, path: Path, content: str) -> None:
        cls._atomic_bytes(path, content.encode("utf-8"))

    @classmethod
    def _atomic_json(cls, path: Path, payload: Any) -> None:
        cls._atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
