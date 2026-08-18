"""从统一 ParsedDocument 构建供 Agent 快速浏览的文档索引。"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from document_parser.core.contracts import ParsedDocument


def _clean(value: str | None) -> str:
    return " ".join((value or "").split())


def _page_number(value: int | None) -> int | None:
    return value if isinstance(value, int) and value >= 1 else None


@dataclass(frozen=True)
class PageIndexEntry:
    """一个页面的轻量结构摘要，不携带完整正文。"""

    page_number: int
    block_ids: tuple[str, ...] = ()
    table_ids: tuple[str, ...] = ()
    headings: tuple[str, ...] = ()
    kind_counts: tuple[tuple[str, int], ...] = ()
    text_preview: str = ""
    char_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "block_ids": list(self.block_ids),
            "table_ids": list(self.table_ids),
            "headings": list(self.headings),
            "kind_counts": dict(self.kind_counts),
            "text_preview": self.text_preview,
            "char_count": self.char_count,
        }

    def prompt_line(self) -> str:
        kinds = ", ".join(f"{key}={value}" for key, value in self.kind_counts)
        headings = " / ".join(self.headings) or "（无标题）"
        preview = self.text_preview or "（无文本预览）"
        return (
            f"- 第 {self.page_number} 页 | blocks={len(self.block_ids)} "
            f"| tables={len(self.table_ids)} | chars={self.char_count} "
            f"| kinds={kinds or 'none'} | headings={headings} "
            f"| preview={preview}"
        )


@dataclass(frozen=True)
class DocumentIndex:
    """文档级页面索引。

    索引只保存稳定 ID 和短摘要；页面正文仍从当前 revision 按需读取。
    """

    total_pages: int
    pages: tuple[PageIndexEntry, ...] = ()
    unknown_block_ids: tuple[str, ...] = ()
    unknown_table_ids: tuple[str, ...] = ()

    @classmethod
    def from_document(
        cls,
        document: ParsedDocument,
        *,
        preview_chars: int = 180,
    ) -> "DocumentIndex":
        page_blocks: dict[int, list[Any]] = defaultdict(list)
        page_tables: dict[int, list[Any]] = defaultdict(list)
        unknown_blocks: list[str] = []
        unknown_tables: list[str] = []
        page_numbers: set[int] = set()

        for block in sorted(
            document.blocks,
            key=lambda item: (item.order_index is None, item.order_index or 0),
        ):
            page = _page_number(block.anchor.page_number)
            if page is None:
                unknown_blocks.append(str(block.id))
                continue
            page_blocks[page].append(block)
            page_numbers.add(page)

        for table in document.tables:
            page = _page_number(table.page_number)
            if page is None:
                unknown_tables.append(table.table_id)
                continue
            page_tables[page].append(table)
            page_numbers.add(page)

        total_pages = max(page_numbers, default=0)
        entries: list[PageIndexEntry] = []
        for page in range(1, total_pages + 1):
            blocks = page_blocks.get(page, [])
            tables = page_tables.get(page, [])
            headings = tuple(
                _clean(block.text or block.markdown)[:120]
                for block in blocks
                if block.kind.value == "heading" or block.heading_level is not None
            )
            kinds = Counter(block.kind.value for block in blocks)
            snippets: list[str] = []
            chars = 0
            for block in blocks:
                chars += len(block.markdown or "")
                if block.kind.value == "table":
                    continue
                snippet = _clean(block.text or block.markdown)
                if snippet and sum(len(item) for item in snippets) < preview_chars:
                    snippets.append(snippet)
            preview = " ".join(snippets)
            if len(preview) > preview_chars:
                preview = preview[:preview_chars].rstrip() + "…"
            entries.append(
                PageIndexEntry(
                    page_number=page,
                    block_ids=tuple(str(block.id) for block in blocks),
                    table_ids=tuple(table.table_id for table in tables),
                    headings=headings,
                    kind_counts=tuple(sorted(kinds.items())),
                    text_preview=preview,
                    char_count=chars,
                )
            )

        return cls(
            total_pages=total_pages,
            pages=tuple(entries),
            unknown_block_ids=tuple(unknown_blocks),
            unknown_table_ids=tuple(unknown_tables),
        )

    def page(self, page_number: int) -> PageIndexEntry | None:
        return next(
            (entry for entry in self.pages if entry.page_number == page_number),
            None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_pages": self.total_pages,
            "pages": [entry.to_dict() for entry in self.pages],
            "unknown_block_ids": list(self.unknown_block_ids),
            "unknown_table_ids": list(self.unknown_table_ids),
        }

    def to_prompt(self, *, max_chars: int = 5000) -> str:
        """生成概览 Prompt，不包含页面完整正文。"""

        lines = [
            f"total_pages={self.total_pages}",
            "pages:",
        ]
        for entry in self.pages:
            line = entry.prompt_line()
            if sum(len(item) + 1 for item in lines) + len(line) > max_chars:
                lines.append("...[page index truncated]")
                break
            lines.append(line)
        if self.unknown_block_ids or self.unknown_table_ids:
            lines.append(
                "unknown_page="
                f"blocks={len(self.unknown_block_ids)}, "
                f"tables={len(self.unknown_table_ids)}"
            )
        return "\n".join(lines)[:max_chars]


__all__ = ["DocumentIndex", "PageIndexEntry"]
