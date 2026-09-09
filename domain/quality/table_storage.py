"""大表结构的交付存储策略。

领域层只决定何时停止生成内嵌绑定；SQLite 的物理写入由基础设施层完成。
"""

from __future__ import annotations

from document_parser.domain.model.contracts import ParsedTable


INLINE_TABLE_CELL_LIMIT = 50_000
TABLE_INDEX_NAME = "table_index.sqlite3"


def uses_external_table_index(table: ParsedTable) -> bool:
    """超过内嵌上限的表格改用外部索引，避免 JSON 和内存线性膨胀。"""

    logical_slots = (table.num_rows or 0) * (table.num_cols or 0)
    return max(len(table.cells), logical_slots) > INLINE_TABLE_CELL_LIMIT
