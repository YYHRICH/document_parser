"""EvidenceContext：规则读取 ParsedDocument 证据的唯一入口。

- 建立索引（blocks/tables 按 ID 查询）；
- 暴露能力判定（AvailabilityResolver）；
- 检测结构问题（重复 block ID、表格块无对应 ParsedTable 等，QL-CONT 规则使用）。
"""

from __future__ import annotations

from collections import Counter

from document_parser.domain.model.contracts import (
    BlockKind,
    DocumentBlock,
    ParsedDocument,
    ParsedTable,
)

from .availability import AvailabilityResolver, RequirementCheck
from .requirements import EvidenceRequirement


class EvidenceContext:
    """不可变证据视图：从 ParsedDocument 构建，规则只读查询。"""

    def __init__(self, parsed: ParsedDocument) -> None:
        self.parsed = parsed
        self._blocks_by_id: dict[str, DocumentBlock] = {}
        self._blocks_by_source: dict[str, list[DocumentBlock]] = {}
        duplicate_block_ids: list[str] = []
        for block in parsed.blocks:
            block_key = str(block.id)
            if block_key in self._blocks_by_id:
                duplicate_block_ids.append(block_key)
            self._blocks_by_id[block_key] = block
            src = block.source_block_id
            if src:
                self._blocks_by_source.setdefault(src, []).append(block)

        self._tables_by_id: dict[str, ParsedTable] = {
            t.table_id: t for t in parsed.tables
        }
        self._table_by_block: dict[str, ParsedTable] = {
            str(t.block_id): t for t in parsed.tables
        }
        self._duplicate_block_ids = tuple(sorted(set(duplicate_block_ids)))
        self._availability = AvailabilityResolver(
            capabilities=parsed.capabilities,
            table_count=len(parsed.tables),
        )

    # ---------- 查询 ----------

    def block(self, block_id: str) -> DocumentBlock | None:
        return self._blocks_by_id.get(block_id)

    def blocks_by_source(self, source_block_id: str) -> list[DocumentBlock]:
        return self._blocks_by_source.get(source_block_id, [])

    def blocks_by_kind(self, kind: BlockKind) -> list[DocumentBlock]:
        return [b for b in self.parsed.blocks if b.kind == kind]

    def table(self, table_id: str) -> ParsedTable | None:
        return self._tables_by_id.get(table_id)

    def table_for_block(self, block_id: str) -> ParsedTable | None:
        return self._table_by_block.get(block_id)

    def tables_by_page(self, page_number: int) -> list[ParsedTable]:
        return [t for t in self.parsed.tables if t.page_number == page_number]

    # ---------- 能力判定 ----------

    def check_requirements(
        self, requirements: tuple[EvidenceRequirement, ...]
    ) -> tuple[RequirementCheck, ...]:
        return self._availability.check_all(requirements)

    def requirements_summary(
        self, requirements: tuple[EvidenceRequirement, ...]
    ) -> tuple[str, str]:
        """返回 (执行模式, 原因)：allowed / limited / blocked / not_applicable。"""
        return self._availability.summary(requirements)

    def capability_state(self, name: str):
        """ParsedDocument.capabilities 中某项能力的原始状态。"""
        capability = self.parsed.capabilities.get(name)
        return getattr(capability, "state", None) if capability else None

    # ---------- 结构检测（QL-CONT 基础） ----------

    @property
    def duplicate_block_ids(self) -> tuple[str, ...]:
        return self._duplicate_block_ids

    @property
    def duplicate_source_block_ids(self) -> tuple[str, ...]:
        """被多个 block 引用的 source_block_id（回溯模糊）。"""
        return tuple(
            sorted(
                src
                for src, blocks in self._blocks_by_source.items()
                if len(blocks) > 1
            )
        )

    @property
    def unanchored_blocks(self) -> list[DocumentBlock]:
        """没有 page_number 的块（来源定位缺失）。"""
        return [b for b in self.parsed.blocks if b.anchor.page_number is None]

    @property
    def order_indices(self) -> list[int]:
        return [b.order_index for b in self.parsed.blocks if b.order_index is not None]

    @property
    def duplicate_order_indices(self) -> list[int]:
        counts = Counter(self.order_indices)
        return sorted(v for v, c in counts.items() if c > 1)

    def ordered_blocks(self) -> list[DocumentBlock]:
        """按 (order_index, id) 确定性排序的 blocks（spec §5.4）。"""
        return sorted(
            self.parsed.blocks,
            key=lambda b: (b.order_index if b.order_index is not None else -1, str(b.id)),
        )
