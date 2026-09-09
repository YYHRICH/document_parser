"""修复注册表：按顺序应用白名单修复，产出 AppliedRepair 列表。

幂等保证：修复本身天然幂等（rstrip 二次无变化；分隔行对齐二次无变化），
应用顺序固定，重复运行不产生第二次修复记录。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping
from uuid import UUID

from document_parser.domain.model.contracts import AppliedRepair, ParsedDocument, ParsedTable

from ..ids import stable_id
from ..hashing import sha256_text
from ..models_internal import EvidenceRef
from ..renderers.table_markdown import render_anchor_copy_table
from .base import RepairOutcome, RepairRule
from .table_html import HtmlTableParseError, convert_table_html, table_needs_html_conversion
from .whitelist import (
    QL_RPR_001_TrailingWhitespace,
    QL_RPR_002_TableSeparator,
)

# MVP 白名单修复（顺序固定）
WHITELIST_REPAIRS: tuple[type[RepairRule], ...] = (
    QL_RPR_001_TrailingWhitespace,
    QL_RPR_002_TableSeparator,
)


@dataclass(frozen=True)
class RepairResult:
    """修复应用结果。"""

    markdown: str
    applied: tuple[AppliedRepair, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DocumentRepairResult:
    """面向 ParsedDocument 的修复结果。

    ``rejected`` 只保存转换失败的结构化原因；任何失败都不会覆盖原始
    table.html 或 block.markdown。
    """

    document: ParsedDocument
    applied: tuple[AppliedRepair, ...] = field(default_factory=tuple)
    rejected: tuple[dict[str, str], ...] = field(default_factory=tuple)


def apply_repairs(
    markdown: str,
    *,
    document_key: str,
    rules: tuple[type[RepairRule], ...] = WHITELIST_REPAIRS,
    affected_block_ids_by_rule: Mapping[str, list[str]] | None = None,
) -> RepairResult:
    """按注册顺序应用全部白名单修复。

    只有实际产生变化的修复才记录（no-op 不计入 applied_repairs）。
    """
    current = markdown
    applied: list[AppliedRepair] = []
    for rule_type in rules:
        rule = rule_type()
        outcome = rule.apply(current)
        if outcome.applied:
            current = outcome.after
            repair_id = stable_id(
                f"repair|{document_key}|{rule.rule_id}|{sha256_text(outcome.before)}"
            )
            block_ids = (affected_block_ids_by_rule or {}).get(rule.rule_id, [])
            if block_ids:
                outcome = RepairOutcome(
                    before=outcome.before,
                    after=outcome.after,
                    description=outcome.description,
                    affected_block_ids=list(block_ids),
                    evidence_refs=outcome.evidence_refs,
                    parameters=outcome.parameters,
                )
            applied.append(outcome.to_applied_repair(repair_id, rule.rule_id))
    return RepairResult(markdown=current, applied=tuple(applied))


def apply_document_repairs(
    parsed_document: ParsedDocument,
    *,
    document_key: str,
    affected_block_ids_by_rule: Mapping[str, list[str]] | None = None,
) -> DocumentRepairResult:
    """对 ParsedDocument 应用安全修复，并同步 block/table/正文三份表示。

    该入口供质量流水线使用：HTML 表格必须先完成对象级转换，随后才执行
    Markdown 格式修复。转换失败时保留原文并返回 rejected 记录。
    """

    current_markdown = parsed_document.markdown
    current_blocks = list(parsed_document.blocks)
    current_tables = list(parsed_document.tables)
    applied: list[AppliedRepair] = []
    rejected: list[dict[str, str]] = []

    # 先记录全局 Markdown 的无损格式修复，保持其 block 影响范围可追踪。
    markdown_result = apply_repairs(
        current_markdown,
        document_key=document_key,
        affected_block_ids_by_rule=affected_block_ids_by_rule,
    )
    current_markdown = markdown_result.markdown
    applied.extend(markdown_result.applied)

    block_index = {str(block.id): index for index, block in enumerate(current_blocks)}
    for table_index, table in enumerate(current_tables):
        if not table_needs_html_conversion(table) and not (
            table.html and table.html in current_markdown
        ):
            continue
        block_position = block_index.get(str(table.block_id))
        block = current_blocks[block_position] if block_position is not None else None
        try:
            conversion = convert_table_html(table, block)
        except (HtmlTableParseError, ValueError) as error:
            rejected.append(
                {
                    "rule_id": "QL-RPR-003",
                    "table_id": table.table_id,
                    "reason": str(error),
                }
            )
            continue
        if (
            conversion.block is None
            or conversion.block.kind.value != "table"
            or not conversion.after_markdown
        ):
            rejected.append(
                {
                    "rule_id": "QL-RPR-003",
                    "table_id": table.table_id,
                    "reason": "table 没有唯一对应的 table block，无法同步正文。",
                }
            )
            continue
        old_block_markdown = block.markdown if block is not None else ""
        source_before = old_block_markdown or table.html or ""
        if old_block_markdown and old_block_markdown in current_markdown:
            current_markdown = current_markdown.replace(
                old_block_markdown, conversion.after_markdown, 1
            )
        elif table.html and table.html in current_markdown:
            source_before = table.html
            current_markdown = current_markdown.replace(
                table.html, conversion.after_markdown, 1
            )
        else:
            rejected.append(
                {
                    "rule_id": "QL-RPR-003",
                    "table_id": table.table_id,
                    "reason": "table block 内容未出现在文档 Markdown 中，无法安全替换。",
                }
            )
            continue
        current_tables[table_index] = conversion.table
        assert block_position is not None
        current_blocks[block_position] = conversion.block
        outcome = RepairOutcome(
            before=source_before,
            after=conversion.after_markdown,
            description=(
                f"将 table {table.table_id} 的 HTML 转为 Markdown。"
                + (
                    " Markdown 无法表达 rowspan/colspan，覆盖位置保留为空。"
                    if conversion.representation_loss
                    else ""
                )
            ),
            affected_block_ids=[str(table.block_id)],
            evidence_refs=[
                EvidenceRef(
                    object_type="table",
                    object_id=table.table_id,
                    field_path="html",
                ),
                EvidenceRef(
                    object_type="table",
                    object_id=table.table_id,
                    field_path="cells",
                ),
            ],
            parameters={
                "operation": "html_table_to_markdown",
                "table_id": table.table_id,
                "html": table.html or "",
                "markdown_representation_loss": conversion.representation_loss,
            },
        )
        repair_id = stable_id(
            f"repair|{document_key}|QL-RPR-003|{table.table_id}|{sha256_text(outcome.before)}"
        )
        applied.append(outcome.to_applied_repair(repair_id, "QL-RPR-003"))

    # Excel 原始值明确保留了单元格内换行时，用源值修复结构文本，并从逻辑
    # 网格重新派生 Markdown。只有四份表示能够原子同步时才允许落盘。
    block_index = {str(block.id): index for index, block in enumerate(current_blocks)}
    for table_index, table in enumerate(current_tables):
        if table.metadata.get("markdown_rendering") != "anchor_copy" or not table.grid:
            continue
        restored_cells = []
        restored_cell_ids: list[str] = []
        for cell in table.cells:
            raw_value = cell.raw_value
            normalized_raw = (
                raw_value.replace("\r\n", "\n").replace("\r", "\n")
                if isinstance(raw_value, str)
                else None
            )
            normalized_text = cell.text.replace("\r\n", "\n").replace("\r", "\n")
            if (
                cell.value_type == "string"
                and normalized_raw is not None
                and "\n" in normalized_raw
                and normalized_raw.strip() != normalized_text.strip()
            ):
                restored_cells.append(
                    cell.model_copy(
                        update={
                            "text": normalized_raw,
                            "display_value": normalized_raw,
                            "normalized_value": normalized_raw.strip(),
                        }
                    )
                )
                restored_cell_ids.append(
                    cell.cell_id
                    or f"{table.table_id}:r{cell.start_row}c{cell.start_col}"
                )
            else:
                restored_cells.append(cell)
        if not restored_cell_ids:
            continue

        restored_table = table.model_copy(update={"cells": restored_cells})
        restored_markdown = render_anchor_copy_table(restored_table)
        block_position = block_index.get(str(table.block_id))
        block = current_blocks[block_position] if block_position is not None else None
        old_markdown = block.markdown if block is not None else table.markdown or ""
        if (
            block is None
            or block.kind.value != "table"
            or not old_markdown
            or old_markdown not in current_markdown
            or not restored_markdown
        ):
            rejected.append(
                {
                    "rule_id": "QL-RPR-004",
                    "table_id": table.table_id,
                    "reason": "源单元格换行存在，但表格 block 无法与全文安全同步。",
                }
            )
            continue

        current_markdown = current_markdown.replace(old_markdown, restored_markdown, 1)
        restored_table = restored_table.model_copy(update={"markdown": restored_markdown})
        current_tables[table_index] = restored_table
        assert block_position is not None
        current_blocks[block_position] = block.model_copy(update={"markdown": restored_markdown})
        outcome = RepairOutcome(
            before=old_markdown,
            after=restored_markdown,
            description=(
                f"依据源工作表恢复 table {table.table_id} 中 "
                f"{len(restored_cell_ids)} 个单元格的内部换行，并同步所有表格表示。"
            ),
            affected_block_ids=[str(table.block_id)],
            evidence_refs=[
                EvidenceRef(
                    object_type="cell",
                    object_id=cell_id,
                    field_path="raw_value",
                )
                for cell_id in restored_cell_ids
            ],
            parameters={
                "operation": "restore_source_cell_line_breaks",
                "table_id": table.table_id,
                "cell_ids": restored_cell_ids,
            },
        )
        repair_id = stable_id(
            f"repair|{document_key}|QL-RPR-004|{table.table_id}|{sha256_text(old_markdown)}"
        )
        applied.append(outcome.to_applied_repair(repair_id, "QL-RPR-004"))

    # block 级文本同步在表格转换之后执行，确保 canonical 使用最终内容。
    for index, block in enumerate(current_blocks):
        block_result = apply_repairs(block.markdown, document_key=document_key)
        if block_result.markdown != block.markdown:
            current_blocks[index] = block.model_copy(update={"markdown": block_result.markdown})

    # ParsedTable.markdown 是 table block 的派生表示，应保持与修复后 block 一致。
    block_by_id = {str(block.id): block for block in current_blocks}
    for index, table in enumerate(current_tables):
        block = block_by_id.get(str(table.block_id))
        if block is not None and block.kind.value == "table":
            current_tables[index] = table.model_copy(update={"markdown": block.markdown})

    repaired_document = parsed_document.model_copy(
        update={
            "markdown": current_markdown,
            "blocks": current_blocks,
            "tables": current_tables,
        }
    )
    return DocumentRepairResult(
        document=repaired_document,
        applied=tuple(applied),
        rejected=tuple(rejected),
    )


def replay_repair(markdown: str, applied_repair: AppliedRepair, *, rules: tuple[type[RepairRule], ...] = WHITELIST_REPAIRS) -> str:
    """按 AppliedRepair 的 rule_id 重放一次；结果必须与记录 after 一致。"""
    if applied_repair.rule_id == "QL-RPR-003":
        html = applied_repair.evidence.get("parameters", {}).get("html")
        if not isinstance(html, str) or not html:
            raise ValueError("HTML table repair lacks replay html evidence")
        outcome = convert_table_html(
            # This branch is only for replaying the block-level before/after pair;
            # full ParsedTable context is intentionally not reconstructed here.
            ParsedTable(
                table_id=applied_repair.evidence.get("parameters", {}).get("table_id", "replay"),
                block_id=UUID(int=0),
                html=html,
                markdown=markdown,
            )
        )
        expected = applied_repair.evidence.get("after")
        if expected is not None and outcome.after_markdown != expected:
            raise ValueError("replayed repair does not match recorded after")
        return outcome.after_markdown
    if applied_repair.rule_id == "QL-RPR-004":
        before = applied_repair.evidence.get("before")
        after = applied_repair.evidence.get("after")
        if not isinstance(before, str) or not isinstance(after, str) or markdown != before:
            raise ValueError("source cell line-break repair replay source does not match")
        return after
    rule_type = next((r for r in rules if r.rule_id == applied_repair.rule_id), None)
    if rule_type is None:
        raise ValueError(f"unknown repair rule: {applied_repair.rule_id}")
    outcome = rule_type().replay(markdown, applied_repair.evidence.get("parameters", {}))
    expected = applied_repair.evidence.get("after")
    if expected is not None and outcome.after != expected:
        raise ValueError("replayed repair does not match recorded after")
    return outcome.after


def rollback_repair(markdown: str, applied_repair: AppliedRepair) -> str:
    """按记录的 before/after 安全回滚一次修复。"""
    before = applied_repair.evidence.get("before")
    after = applied_repair.evidence.get("after")
    if not isinstance(before, str) or not isinstance(after, str) or markdown != after:
        raise ValueError("rollback source does not match recorded repair")
    return before
