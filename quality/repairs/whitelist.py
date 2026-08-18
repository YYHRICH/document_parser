"""MVP 白名单修复实现（spec §6.2 低风险子集）。

- QL-RPR-001 行尾空白规范化：去除明确的行尾空白（不改变文本内容）；
- QL-RPR-002 表格分隔行修复：分隔行列数与表头列数不一致时对齐，
  不改变任何单元格文字。

禁止（spec §6.3）：猜测 OCR 字符、改写句子、补数字/公式/表头/标题、
推算缺失值、伪造 bbox、按 LLM 建议改变事实、为唯一性追加序号。
"""

from __future__ import annotations

import re

from quality.models_internal import EvidenceRef
from quality.repairs.base import RepairOutcome, RepairRule


class QL_RPR_001_TrailingWhitespace(RepairRule):
    """去除行尾空白（含空行的纯空白）。"""

    rule_id = "QL-RPR-001"

    def apply(self, markdown: str) -> RepairOutcome:
        lines = markdown.splitlines()
        cleaned = [line.rstrip() for line in lines]
        fixed_count = sum(1 for a, b in zip(lines, cleaned) if a != b)
        if fixed_count == 0:
            return RepairOutcome(
                before=markdown,
                after=markdown,
                description="无行尾空白，无需修复。",
            )
        # 保留原文本的尾部换行结构（splitlines 会丢弃末尾换行）
        suffix = "\n" if markdown.endswith("\n") else ""
        return RepairOutcome(
            before=markdown,
            after="\n".join(cleaned) + suffix,
            description=f"去除 {fixed_count} 行的行尾空白。",
            evidence_refs=[
                EvidenceRef(
                    object_type="document",
                    object_id="markdown",
                    field_path="lines",
                )
            ],
        )


class QL_RPR_002_TableSeparator(RepairRule):
    """修复 Markdown 表格分隔行：列数与表头列数对齐（不改变单元格文字）。"""

    rule_id = "QL-RPR-002"

    def apply(self, markdown: str) -> RepairOutcome:
        lines = markdown.splitlines()
        changed_lines: list[tuple[int, str]] = []

        def _col_count(line: str) -> int:
            return len([c for c in line.strip().strip("|").split("|")])

        for i, line in enumerate(lines):
            if i == 0 or not re.match(r"^\|[\s:\-|]+\|$", line):
                continue
            prev = lines[i - 1]
            if not prev.strip().startswith("|"):
                continue
            header_cols = _col_count(prev)
            sep_cols = _col_count(line)
            if header_cols == sep_cols:
                continue
            # 修复分隔行：保留原有列样式（- 或 :-），只调整列数
            cols = line.strip().strip("|").split("|")
            new_cols = (cols + ["---"] * header_cols)[:header_cols]
            fixed = "|" + "|".join(c.strip() or "---" for c in new_cols) + "|"
            changed_lines.append((i, fixed))

        if not changed_lines:
            return RepairOutcome(
                before=markdown,
                after=markdown,
                description="无表格分隔行列数问题，无需修复。",
            )
        after = lines.copy()
        for i, fixed in changed_lines:
            after[i] = fixed
        return RepairOutcome(
            before=markdown,
            after="\n".join(after),
            description=f"修复 {len(changed_lines)} 个表格分隔行（列数对齐）。",
            evidence_refs=[
                EvidenceRef(
                    object_type="document",
                    object_id="markdown",
                    field_path="table_separator",
                )
            ],
        )
