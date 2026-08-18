"""Agent 使用的只读文档上下文工具。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from quality.agent.index import DocumentIndex
from quality.agent.revision import DocumentRevision
from quality.agent.validator import content_fingerprint


@dataclass(frozen=True)
class DocumentReadTools:
    """绑定到一个 revision 的只读工具集合。"""

    revision: DocumentRevision
    max_chars: int = 8000

    def get_document_summary(self) -> dict[str, Any]:
        document = self.revision.document
        return {
            "document_id": str(document.document_id),
            "revision_id": self.revision.revision_id,
            "filename": document.filename,
            "file_type": document.file_type,
            "markdown_chars": len(document.markdown),
            "block_count": len(document.blocks),
            "table_count": len(document.tables),
            "asset_count": len(document.assets),
            "warning_count": len(document.warnings),
            "capabilities": {
                key: value.state.value for key, value in document.capabilities.items()
            },
        }

    def get_document_index(self) -> dict[str, Any]:
        return DocumentIndex.from_document(self.revision.document).to_dict()

    def get_document_outline(self) -> list[dict[str, Any]]:
        return [
            {
                "block_id": str(block.id),
                "heading_level": block.heading_level,
                "title": block.text or block.markdown,
                "order_index": block.order_index,
                "section_path": block.anchor.section_path,
            }
            for block in self.revision.document.blocks
            if block.kind.value == "heading"
        ]

    def get_page_context(
        self,
        page_number: int,
        *,
        include_neighbors: bool = False,
    ) -> dict[str, Any]:
        """按页返回有限 block/table 证据；不返回整篇 Markdown。"""

        index = DocumentIndex.from_document(self.revision.document)
        entry = index.page(page_number)
        if entry is None:
            return {"page_number": page_number, "found": False}
        payload: dict[str, Any] = {
            "page_number": page_number,
            "found": True,
            "index": entry.to_dict(),
            "blocks": self.get_region_context(list(entry.block_ids)),
            "tables": [
                table
                for table_id in entry.table_ids
                if (table := self.get_table_context(table_id)) is not None
            ],
        }
        if include_neighbors:
            payload["neighbors"] = [
                neighbor.to_dict()
                for neighbor in index.pages
                if abs(neighbor.page_number - page_number) == 1
            ]
        return payload

    def get_neighbor_page_context(
        self,
        page_number: int,
        *,
        radius: int = 1,
    ) -> list[dict[str, Any]]:
        """返回相邻页索引，供跨页判断而非直接扩大正文上下文。"""

        index = DocumentIndex.from_document(self.revision.document)
        return [
            entry.to_dict()
            for entry in index.pages
            if 0 < abs(entry.page_number - page_number) <= max(radius, 1)
        ]

    def get_cross_page_table_context(self, table_ids: list[str]) -> list[dict[str, Any]]:
        """按 table ID 返回跨页表格及其页码证据。"""

        result = []
        for table_id in table_ids:
            table = self.get_table_context(table_id)
            if table is not None:
                result.append(table)
        return result

    def get_region_context(self, block_ids: list[str]) -> list[dict[str, Any]]:
        requested = set(block_ids)
        result: list[dict[str, Any]] = []
        remaining = self.max_chars
        for block in self.revision.document.blocks:
            if str(block.id) not in requested:
                continue
            markdown = block.markdown[:remaining]
            result.append(
                {
                    "block_id": str(block.id),
                    "kind": block.kind.value,
                    "markdown": markdown,
                    "anchor": block.anchor.model_dump(mode="json"),
                }
            )
            remaining -= len(markdown)
            if remaining <= 0:
                break
        return result

    def get_table_context(self, table_id: str) -> dict[str, Any] | None:
        for table in self.revision.document.tables:
            if table.table_id == table_id:
                payload = table.model_dump(mode="json", exclude={"image_path"})
                for cell in payload.get("cells", []):
                    cell.pop("bbox", None)
                return payload
        return None

    def get_asset_context(self, path: str) -> dict[str, Any] | None:
        for asset in self.revision.document.assets:
            if asset.path == path:
                return asset.model_dump(mode="json", exclude={"content"})
        return None

    def get_revision_digest(self) -> dict[str, Any]:
        document = self.revision.document
        return {
            "revision_id": self.revision.revision_id,
            "parent_revision_id": self.revision.parent_revision_id,
            "attempt": self.revision.attempt,
            "document_id": str(document.document_id),
            "source_sha256": document.source_sha256,
            "content_fingerprint": content_fingerprint(document.markdown),
        }

    def as_agno_tools(self) -> list[Callable[..., Any]]:
        """返回可直接传给 ``Agent(tools=...)`` 的只读函数。"""

        return [
            self.get_document_summary,
            self.get_document_index,
            self.get_document_outline,
            self.get_page_context,
            self.get_neighbor_page_context,
            self.get_cross_page_table_context,
            self.get_region_context,
            self.get_table_context,
            self.get_asset_context,
            self.get_revision_digest,
        ]
