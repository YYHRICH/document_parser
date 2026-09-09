"""将领域 ``ParsedDocument`` 发布为杨组可直接加载的 mmwiki-0.1 包。

这是反腐层（ACL）：领域层不知道 mmwiki，外部协议的目录、字段和兼容规则
全部收敛在基础设施层。
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from ...domain.model.contracts import BlockKind, ParsedDocument, ParsedTable, SourceAnchor
from ..packaging.document_package import validate_parsed_document_integrity


class MmwikiDeliveryError(ValueError):
    """ParsedDocument 无法无损、安全地交给 mmwiki。"""


class MmwikiPackageAdapter:
    """出站适配器：ParsedDocument → mmwiki-0.1 文件包。"""

    _KIND = {
        BlockKind.HEADING: "title",
        BlockKind.PARAGRAPH: "paragraph",
        BlockKind.LIST: "list",
        BlockKind.TABLE: "table",
        BlockKind.IMAGE: "image",
        BlockKind.FORMULA: "equation",
        BlockKind.HEADER: "page_header",
        BlockKind.FOOTER: "page_footer",
        BlockKind.PAGE_NUMBER: "page_number",
        BlockKind.ASIDE: "paragraph",
        BlockKind.FOOTNOTE: "paragraph",
        BlockKind.REFERENCE: "paragraph",
    }

    def publish(self, document: ParsedDocument, package_root: Path | str) -> dict[str, Any]:
        validate_parsed_document_integrity(document)
        target = Path(package_root)
        if target.exists():
            raise MmwikiDeliveryError(f"目标 mmwiki package 已存在：{target}")
        target.mkdir(parents=True)
        try:
            return self._write(document, target)
        except Exception:
            shutil.rmtree(target)
            raise

    def _write(self, document: ParsedDocument, target: Path) -> dict[str, Any]:
        assets_dir = target / "assets"
        assets_dir.mkdir()
        block_to_item: dict[str, str] = {}
        items: list[dict[str, Any]] = []
        sorted_blocks = sorted(
            enumerate(document.blocks),
            key=lambda pair: (
                pair[1].order_index if pair[1].order_index is not None else pair[0],
                pair[0],
            ),
        )
        for sequence, (_, block) in enumerate(sorted_blocks, 1):
            item_id = block.source_block_id or f"item-{str(block.id)}"
            block_to_item[str(block.id)] = item_id
            block_to_item[item_id] = item_id

        asset_rows, asset_ids_by_block = self._write_assets(
            document, assets_dir, block_to_item
        )
        table_by_block = {str(table.block_id): table for table in document.tables}
        for sequence, (_, block) in enumerate(sorted_blocks, 1):
            item_id = block_to_item[str(block.id)]
            item_type = self._KIND[block.kind]
            raw_text = block.text if block.text is not None else block.markdown
            breadcrumb = " > ".join(block.anchor.section_path)
            table = table_by_block.get(str(block.id))
            content: dict[str, Any] = {
                "raw_text": raw_text,
                "caption": str(block.metadata.get("caption") or ""),
                "search_text": " ".join(
                    value for value in (breadcrumb, raw_text) if value
                ),
                "semantic": {},
            }
            if table is not None:
                content["table"] = self._table_content(table)
            if block.kind == BlockKind.FORMULA:
                content["equation"] = {"latex": raw_text, "math_type": "latex"}
            asset_ids = asset_ids_by_block.get(item_id, [])
            searchable = bool(content["search_text"].strip() or asset_ids)
            items.append(
                {
                    "item_id": item_id,
                    "sequence": sequence,
                    "type": item_type,
                    "raw_type": block.native_type or item_type,
                    "page_start": block.anchor.page_number,
                    "page_end": block.anchor.page_end or block.anchor.page_number,
                    "bbox": self._bbox(block.anchor),
                    "breadcrumb": breadcrumb,
                    "content": content,
                    "assets": [{"asset_id": value} for value in asset_ids],
                    "provenance": {
                        "parser": document.provenance.parser_id,
                        "raw_ref": block.source_block_id or str(block.id),
                        "page": block.anchor.page_number,
                        "block_index": sequence,
                    },
                    "metadata": {
                        **block.metadata,
                        "resource_type": item_type,
                    },
                    "quality": {"needs_review": False, "review_reasons": []},
                    "retrieval": {"searchable": searchable, "exclude": not searchable},
                }
            )

        chunks = self._chunks(document, items, block_to_item, asset_rows)
        self._jsonl(target / "items.jsonl", items)
        self._jsonl(target / "chunks.jsonl", chunks)
        self._json(target / "assets.json", asset_rows)
        package_id = self._package_id(document)
        manifest = {
            "schema_version": "mmwiki-0.1",
            "package_id": package_id,
            "document": {
                "title": Path(document.filename).stem,
                "source": {
                    "filename": document.filename,
                    "media_type": document.file_type,
                },
            },
            "parser": {
                "name": document.provenance.parser_id,
                "version": document.provenance.version,
                "source_schema": document.schema_name,
            },
            "artifacts": {
                "items": "items.jsonl",
                "chunks": "chunks.jsonl",
                "assets": "assets/",
                "assets_index": "assets.json",
            },
            "counts": {
                "records": len(items),
                "chunks": len(chunks),
                "assets": len(asset_rows),
            },
            "handoff": {
                "text_index": "chunks.text",
                "image_index": "chunks.asset_ids",
                "table_index": "items.content.table",
                "answer_citation": "chunks.provenance",
            },
        }
        self._json(target / "manifest.json", manifest)
        return {"package_root": str(target.resolve()), "manifest": manifest}

    def _write_assets(
        self,
        document: ParsedDocument,
        assets_dir: Path,
        block_to_item: dict[str, str],
    ) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
        rows: list[dict[str, Any]] = []
        by_block: dict[str, list[str]] = {}
        seen: set[str] = set()
        for asset in document.assets:
            digest = hashlib.sha256(asset.content).hexdigest()
            if asset.sha256 is not None and asset.sha256 != digest:
                raise MmwikiDeliveryError(f"资源 SHA-256 不匹配：{asset.path}")
            asset_id = asset.asset_id or f"asset-{digest[:20]}"
            if asset_id in seen:
                raise MmwikiDeliveryError(f"重复 asset_id：{asset_id}")
            seen.add(asset_id)
            suffix = PurePosixPath(asset.path).suffix.lower() or ".bin"
            relative = f"assets/{digest[:20]}{suffix}"
            (assets_dir / f"{digest[:20]}{suffix}").write_bytes(asset.content)
            rows.append(
                {
                    "asset_id": asset_id,
                    "path": relative,
                    "media_type": asset.file_type,
                    "sha256": digest,
                    "source_path": asset.path,
                }
            )
            for block_id in asset.referenced_by_block_ids:
                item_id = block_to_item.get(block_id)
                if item_id is not None:
                    by_block.setdefault(item_id, []).append(asset_id)
        return rows, by_block

    @staticmethod
    def _bbox(anchor: SourceAnchor) -> dict[str, Any]:
        if anchor.bbox is None:
            return {}
        if anchor.coordinate_system == "normalized_1000":
            values = list(anchor.bbox)
        elif anchor.coordinate_system == "normalized_1":
            values = [value * 1000 for value in anchor.bbox]
        elif (
            anchor.page_width is not None
            and anchor.page_height is not None
            and anchor.origin in {None, "top_left"}
        ):
            left, top, right, bottom = anchor.bbox
            values = [
                left / anchor.page_width * 1000,
                top / anchor.page_height * 1000,
                right / anchor.page_width * 1000,
                bottom / anchor.page_height * 1000,
            ]
        else:
            raise MmwikiDeliveryError(
                "bbox 无法可靠转换为 normalized_1000；需提供坐标系、左上角原点和页面宽高。"
            )
        if any(value < 0 or value > 1000 for value in values):
            raise MmwikiDeliveryError("转换后的 bbox 超出 0-1000。")
        return {
            "values": values,
            "coordinate_system": "normalized_1000",
            "origin": "top_left",
        }

    @staticmethod
    def _table_content(table: ParsedTable) -> dict[str, Any]:
        rows = table.metadata.get("rows")
        if not (
            isinstance(rows, list)
            and all(
                isinstance(row, list) and all(isinstance(cell, str) for cell in row)
                for row in rows
            )
        ):
            row_count = table.num_rows or max(
                (cell.start_row + 1 for cell in table.cells), default=0
            )
            col_count = table.num_cols or max(
                (cell.start_col + 1 for cell in table.cells), default=0
            )
            rows = [["" for _ in range(col_count)] for _ in range(row_count)]
            for cell in table.cells:
                rows[cell.start_row][cell.start_col] = cell.text
        return {"rows": rows, "html": table.html or ""}

    @staticmethod
    def _chunks(
        document: ParsedDocument,
        items: list[dict[str, Any]],
        block_to_item: dict[str, str],
        asset_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        known_assets = {row["asset_id"] for row in asset_rows}
        if document.retrieval_chunks:
            return [
                {
                    "chunk_id": chunk.chunk_id,
                    "item_ids": [block_to_item.get(value, value) for value in chunk.item_ids],
                    "text": chunk.text,
                    "breadcrumb": chunk.breadcrumb or "",
                    "modalities": chunk.modalities,
                    "asset_ids": [value for value in chunk.asset_ids if value in known_assets],
                    "page_refs": chunk.page_refs,
                    "provenance": {
                        "item_ids": [block_to_item.get(value, value) for value in chunk.item_ids],
                        "pages": chunk.page_refs,
                        "context_item_ids": [
                            block_to_item.get(value, value) for value in chunk.context_item_ids
                        ],
                    },
                    "quality": {"needs_review": chunk.needs_review},
                }
                for chunk in document.retrieval_chunks
                if chunk.searchable
            ]
        return [
            {
                "chunk_id": f"chunk-{index:05d}",
                "item_ids": [item["item_id"]],
                "text": item["content"]["search_text"],
                "breadcrumb": item["breadcrumb"],
                "modalities": [item["type"]],
                "asset_ids": [asset["asset_id"] for asset in item["assets"]],
                "page_refs": [item["page_start"]] if item["page_start"] else [],
                "provenance": {
                    "item_ids": [item["item_id"]],
                    "pages": [item["page_start"]] if item["page_start"] else [],
                    "context_item_ids": [],
                },
                "quality": {"needs_review": False},
            }
            for index, item in enumerate(items, 1)
            if item["retrieval"]["searchable"]
        ]

    @staticmethod
    def _package_id(document: ParsedDocument) -> str:
        stem = re.sub(r"[/\\@#\s]+", "-", Path(document.filename).stem).strip("-")
        return stem or f"document-{document.document_id.hex[:12]}"

    @staticmethod
    def _json(path: Path, value: Any) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    @staticmethod
    def _jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )


class MmwikiLifecycleDeliveryAdapter:
    """为文件夹生命周期管理 mmwiki 交付版本与状态。"""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.manifest_path = self.root / "delivery-manifest.json"
        self.package_adapter = MmwikiPackageAdapter()

    def publish(
        self, *, source_id: str, parse_id: str, document: ParsedDocument
    ) -> dict[str, Any]:
        package_root = self.root / source_id / parse_id
        result = self.package_adapter.publish(document, package_root)
        manifest = self._manifest()
        record = {
            "source_id": source_id,
            "parse_id": parse_id,
            "source_filename": document.filename,
            "state": "ready_for_enrichment",
            "package_path": str(package_root.resolve()),
            "published_at": datetime.now(UTC).isoformat(),
        }
        manifest["sources"][source_id] = record
        manifest["updated_at"] = datetime.now(UTC).isoformat()
        self._write_manifest(manifest)
        return {**record, "manifest": result["manifest"]}

    def withdraw(self, source_id: str, *, reason: str = "source_deleted") -> dict[str, Any]:
        manifest = self._manifest()
        previous = manifest["sources"].get(source_id, {})
        record = {
            **previous,
            "source_id": source_id,
            "state": "withdrawn",
            "withdraw_reason": reason,
            "withdrawn_at": datetime.now(UTC).isoformat(),
        }
        manifest["sources"][source_id] = record
        manifest["updated_at"] = datetime.now(UTC).isoformat()
        self._write_manifest(manifest)
        return record

    def relocate(self, source_id: str, *, filename: str) -> dict[str, Any]:
        manifest = self._manifest()
        previous = manifest["sources"].get(source_id)
        if not isinstance(previous, dict) or previous.get("state") != "ready_for_enrichment":
            raise FileNotFoundError(f"找不到可重命名的 mmwiki Source：{source_id}")
        package_root = Path(str(previous["package_path"]))
        package_manifest_path = package_root / "manifest.json"
        package_manifest = json.loads(package_manifest_path.read_text(encoding="utf-8"))
        package_manifest["document"]["source"]["filename"] = filename
        package_manifest["document"]["title"] = Path(filename).stem
        self._atomic_json(package_manifest_path, package_manifest)
        record = {
            **previous,
            "source_filename": filename,
            "relocated_at": datetime.now(UTC).isoformat(),
        }
        manifest["sources"][source_id] = record
        manifest["updated_at"] = datetime.now(UTC).isoformat()
        self._write_manifest(manifest)
        return record

    def status(self) -> dict[str, Any]:
        manifest = self._manifest()
        sources = list(manifest["sources"].values())
        return {
            "root": str(self.root.resolve()),
            "manifest_path": str(self.manifest_path.resolve()),
            "ready_count": sum(
                item.get("state") == "ready_for_enrichment" for item in sources
            ),
            "withdrawn_count": sum(item.get("state") == "withdrawn" for item in sources),
            "sources": sources,
        }

    def _manifest(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            return {"schema_name": "MmwikiDeliveryManifest", "version": 1, "sources": {}}
        value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if value.get("version") != 1 or not isinstance(value.get("sources"), dict):
            raise MmwikiDeliveryError("不支持的 mmwiki delivery manifest。")
        return value

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(self.manifest_path)

    @staticmethod
    def _atomic_json(path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(path)
