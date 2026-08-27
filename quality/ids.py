"""稳定 ID 生成：同一输入、同一配置重复运行产出完全一致的 ID。

所有公共输出 ID（binding/relation/issue/block）必须用确定性哈希生成，
禁止随机 UUID、数组下标或运行时间参与。
"""

from __future__ import annotations

from uuid import UUID, uuid5

# 质量层专属命名空间（固定值，不随运行变化）
QUALITY_NAMESPACE = UUID("b3c1e2d4-5f6a-4b8e-9c1d-2e3f4a5b6c7d")


def stable_id(key: str) -> str:
    """由任意 key 生成确定性 UUIDv5 字符串。"""
    return str(uuid5(QUALITY_NAMESPACE, key))


def is_stable_id(value: str) -> bool:
    """Return whether *value* is a canonical UUIDv5 quality-layer ID."""
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError):
        return False
    return parsed.version == 5


def binding_id(
    document_key: str,
    table_id: str,
    cell_key: str,
    row_key: str,
    column_path: list[str],
) -> str:
    """表格字段绑定的稳定 ID。

    ``cell_key`` 为单元格身份（当前为 "r{row}c{col}" 坐标组合，D-09）；
    ``column_path`` 为完整列路径（合并表头逐级展开）。
    """
    path = "/".join(column_path)
    return stable_id(f"binding|{document_key}|{table_id}|{cell_key}|{row_key}|{path}")


def relation_id(
    document_key: str,
    relation_type: str,
    from_id: str,
    to_id: str,
    marker_key: str = "",
) -> str:
    """文档内关系（parent_child / reference_of 等）的稳定 ID。"""
    return stable_id(
        f"relation|{document_key}|{relation_type}|{from_id}|{to_id}|{marker_key}"
    )


def issue_id(
    document_key: str,
    rule_id: str,
    affected_ids: list[str],
    evidence_key: str = "",
) -> str:
    """质量问题的稳定 ID。"""
    affected = ",".join(sorted(affected_ids))
    return stable_id(f"issue|{document_key}|{rule_id}|{affected}|{evidence_key}")


def block_id(
    document_key: str,
    source_block_id: str,
    order_index: int,
    *,
    block_uuid: str | None = None,
) -> str:
    """生成 canonical block 的稳定 ID。

    ``block_uuid`` 是 ParsedDocument 中 block 的对象身份；未提供时保留
    旧的 source_block_id 方案，兼容外部直接调用。
    """
    identity = block_uuid or source_block_id
    return stable_id(f"block|{document_key}|{identity}|{order_index}")
