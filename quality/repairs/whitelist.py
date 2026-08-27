"""MVP 白名单修复实现（spec §6.2 低风险子集）。

- QL-RPR-001 行尾空白规范化：仅清理非语义行尾空白，保留 Markdown 硬换行和围栏代码内容；
- QL-RPR-002 表格分隔行修复：分隔行列数与表头列数不一致时对齐，
  不改变任何单元格文字；
- QL-RPR-003 MinerU HTML 表格规范化：完整 `<table>` 转管道 Markdown，
  合并单元格只保留起始格文本，原始 HTML 仍保留为来源证据。

禁止（spec §6.3）：猜测 OCR 字符、改写句子、补数字/公式/表头/标题、
推算缺失值、伪造 bbox、按外部建议改变事实、为唯一性追加序号。
"""

from __future__ import annotations

import re

from quality.models_internal import EvidenceRef
from quality.repairs.base import RepairOutcome, RepairRule
from quality.repairs.html_tables import convert_html_tables


class QL_RPR_001_TrailingWhitespace(RepairRule):
    """清理非语义行尾空白，保留 Markdown 硬换行和围栏代码内容。"""

    rule_id = "QL-RPR-001"
    _FENCE = re.compile(r"^[ \t]*(?:\x60{3,}|~{3,})")

    @staticmethod
    def _split_line_ending(line: str) -> tuple[str, str]:
        if line.endswith("\r\n"):
            return line[:-2], "\r\n"
        if line.endswith("\n") or line.endswith("\r"):
            return line[:-1], line[-1]
        return line, ""

    def apply(self, markdown: str) -> RepairOutcome:
        lines = markdown.splitlines(keepends=True)
        cleaned: list[str] = []
        in_fence: str | None = None
        blank_line_count = 0
        single_space_count = 0

        for raw_line in lines:
            body, ending = self._split_line_ending(raw_line)
            fence_match = self._FENCE.match(body)
            if fence_match:
                marker = fence_match.group(0).lstrip(" \t")
                if in_fence is None:
                    in_fence = marker
                elif marker[0] == in_fence[0] and len(marker) >= len(in_fence):
                    in_fence = None
                cleaned.append(raw_line)
                continue

            if in_fence is not None:
                cleaned.append(raw_line)
                continue

            if not body.strip(" \t"):
                normalized = ending
                if normalized != raw_line:
                    blank_line_count += 1
                cleaned.append(normalized)
                continue

            # 两个及以上空格是 Markdown 硬换行；制表符的 Markdown 语义
            # 也不够确定。只删除紧跟非空白字符的一个普通空格。
            if body.endswith(" ") and len(body) >= 2 and body[-2] not in " \t":
                cleaned.append(body[:-1] + ending)
                single_space_count += 1
                continue

            cleaned.append(raw_line)

        after = "".join(cleaned)
        fixed_count = blank_line_count + single_space_count
        if fixed_count == 0:
            return RepairOutcome(
                before=markdown,
                after=markdown,
                description="无可安全清理的非语义行尾空白。",
            )
        return RepairOutcome(
            before=markdown,
            after=after,
            description=(
                f"清理 {fixed_count} 行非语义行尾空白"
                "（保留 Markdown 硬换行与围栏代码内容）。"
            ),
            parameters={
                "operation": "remove_nonsemantic_trailing_whitespace",
                "line_count": fixed_count,
                "blank_line_count": blank_line_count,
                "single_space_line_count": single_space_count,
                "preserved_markdown_hard_breaks": True,
                "preserved_fenced_code": True,
            },
            evidence_refs=[
                EvidenceRef(
                    object_type="document",
                    object_id="markdown",
                    field_path="lines",
                )
            ],
        )


class QL_RPR_003_HtmlTableToMarkdown(RepairRule):
    """Convert only complete span-free HTML tables to Markdown."""

    rule_id = "QL-RPR-003"

    def apply(self, markdown: str) -> RepairOutcome:
        after, converted = convert_html_tables(markdown)
        if converted == 0:
            return RepairOutcome(
                before=markdown,
                after=markdown,
                description="No complete HTML tables required conversion.",
            )
        return RepairOutcome(
            before=markdown,
            after=after,
            description=f"Converted {converted} HTML table(s) to Markdown.",
            parameters={
                "operation": "html_table_to_markdown",
                "table_count": converted,
                "span_policy": "reject_lossy_span_tables",
            },
            evidence_refs=[
                EvidenceRef(
                    object_type="document",
                    object_id="markdown",
                    field_path="html_tables",
                )
            ],
        )

    def replay(self, markdown: str, parameters: dict | None = None) -> RepairOutcome:
        parameters = parameters or {}
        if parameters.get("operation") != "table_html_to_markdown_target":
            return self.apply(markdown)
        source = parameters.get("source_html")
        replacement = parameters.get("replacement_markdown")
        table_id = parameters.get("table_id")
        if not isinstance(source, str) or not isinstance(replacement, str):
            raise ValueError("targeted table repair requires source and replacement text")
        if markdown.count(source) != 1:
            return RepairOutcome(
                before=markdown,
                after=markdown,
                description="Targeted table HTML source is absent or ambiguous.",
            )
        return RepairOutcome(
            before=markdown,
            after=markdown.replace(source, replacement, 1),
            description=f"Converted table {table_id or 'unknown'} HTML to Markdown.",
            parameters=dict(parameters),
            evidence_refs=[
                EvidenceRef(
                    object_type="document",
                    object_id="markdown",
                    field_path="html_tables",
                )
            ],
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
