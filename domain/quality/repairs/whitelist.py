"""MVP 白名单修复实现（spec §6.2 低风险子集）。

- QL-RPR-001 行尾空白规范化：去除明确的行尾空白（不改变文本内容）；
- QL-RPR-002 表格分隔行修复：分隔行列数与表头列数不一致时对齐，
  不改变任何单元格文字。

禁止（spec §6.3）：猜测 OCR 字符、改写句子、补数字/公式/表头/标题、
推算缺失值、伪造 bbox、按 LLM 建议改变事实、为唯一性追加序号。
"""

from __future__ import annotations

import re

from ..models_internal import EvidenceRef
from .base import RepairOutcome, RepairRule


class QL_RPR_001_TrailingWhitespace(RepairRule):
    """去除行尾空白（含空行的纯空白）。"""

    rule_id = "QL-RPR-001"

    def apply(self, markdown: str) -> RepairOutcome:
        # 只删除行尾空格/制表符，保留 CRLF/LF 和末尾换行结构。
        lines = markdown.splitlines(keepends=True)
        cleaned = [re.sub(r"[ \t]+(?=\r?(?:\n|$))", "", line) for line in lines]
        fixed_count = sum(a != b for a, b in zip(lines, cleaned))
        if fixed_count == 0:
            return RepairOutcome(before=markdown, after=markdown, description="无行尾空白，无需修复。")
        return RepairOutcome(
            before=markdown,
            after="".join(cleaned),
            description=f"去除 {fixed_count} 行的行尾空白。",
            parameters={"operation": "rstrip_line_spaces", "line_count": fixed_count},
            evidence_refs=[EvidenceRef(object_type="document", object_id="markdown", field_path="lines")],
        )



class QL_RPR_002_TableSeparator(RepairRule):
    """修复 Markdown 表格分隔行：列数与表头列数对齐（不改变单元格文字）。"""

    rule_id = "QL-RPR-002"

    def apply(self, markdown: str) -> RepairOutcome:
        lines = markdown.splitlines(keepends=True)
        changed_lines: list[tuple[int, str]] = []
        in_fence = False

        def _row_cells(line: str) -> list[str] | None:
            stripped = line.strip()
            if not (stripped.startswith("|") and stripped.endswith("|")):
                return None
            cells: list[str] = []
            current: list[str] = []
            escaped = False
            for char in stripped[1:-1]:
                if char == "|" and not escaped:
                    cells.append("".join(current))
                    current = []
                    continue
                current.append(char)
                escaped = char == "\\" and not escaped
                if char != "\\":
                    escaped = False
            cells.append("".join(current))
            return cells

        def _separator(cells: list[str] | None) -> bool:
            return bool(cells) and all(re.fullmatch(r"\s*:?-+:?\s*", c) for c in cells)

        for i, raw_line in enumerate(lines):
            line = raw_line.rstrip("\r\n")
            if re.match(r"^\s*(```+|~~~+)", line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            sep_cells = _row_cells(line)
            if not _separator(sep_cells) or i == 0:
                continue
            header_cells = _row_cells(lines[i - 1].rstrip("\r\n"))
            if not header_cells or len(header_cells) == len(sep_cells or []):
                continue
            newline = "\r\n" if raw_line.endswith("\r\n") else "\n" if raw_line.endswith("\n") else ""
            styles = list(sep_cells or [])
            styles = (styles + ["---"] * len(header_cells))[: len(header_cells)]
            fixed = "|" + "|".join(c.strip() or "---" for c in styles) + "|" + newline
            changed_lines.append((i, fixed))

        if not changed_lines:
            return RepairOutcome(before=markdown, after=markdown, description="无表格分隔行列数问题，无需修复。")
        after = lines.copy()
        for i, fixed in changed_lines:
            after[i] = fixed
        return RepairOutcome(
            before=markdown,
            after="".join(after),
            description=f"修复 {len(changed_lines)} 个表格分隔行（列数对齐）。",
            parameters={"operation": "align_table_separator", "line_indices": [i for i, _ in changed_lines]},
            evidence_refs=[EvidenceRef(object_type="document", object_id="markdown", field_path="table_separator")],
        )
