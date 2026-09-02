"""将 HTML table 安全地渲染成 Markdown，并保留可验证的网格信息。

该模块只使用 Python 标准库 HTMLParser，不联网、不执行脚本，也不通过正则
表达式解析完整 HTML。rowspan/colspan 会展开为物理网格；Markdown 无法表达
合并单元格时，覆盖位置保留为空，结构损失由调用方记录。
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import re
from typing import Any

from document_parser.domain.model.contracts import TableCell


class HtmlTableParseError(ValueError):
    """HTML 不是可安全转换的 table 片段。"""


@dataclass(frozen=True)
class RenderedTable:
    """HTML table 的确定性 Markdown 表示和网格证据。"""

    markdown: str
    cells: tuple[TableCell, ...]
    num_rows: int
    num_cols: int
    nonempty_cell_count: int
    markdown_representation_loss: bool


@dataclass
class _RawCell:
    text: list[str]
    row_span: int
    col_span: int
    header: bool


class _TableParser(HTMLParser):
    """只收集 table/tr/td/th，忽略脚本、样式和外部资源。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[_RawCell]] = []
        self._current_row: list[_RawCell] | None = None
        self._current_cell: _RawCell | None = None
        self._in_table = False
        self._table_depth = 0
        self._ignored_depth = 0

    @staticmethod
    def _positive_int(attrs: dict[str, str], key: str) -> int:
        raw = attrs.get(key, "1")
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return 1
        return value if value > 0 else 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        if tag == "table":
            if self._in_table:
                self._table_depth += 1
                return
            self._in_table = True
            self._table_depth = 1
            return
        if not self._in_table:
            return
        if tag in {"script", "style", "template", "svg"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "tr":
            if self._current_cell is not None:
                self.handle_endtag("td")
            if self._current_row is not None:
                self.rows.append(self._current_row)
            self._current_row = []
            return
        if tag in {"td", "th"}:
            if self._current_row is None:
                self._current_row = []
            if self._current_cell is not None:
                self.handle_endtag("td")
            self._current_cell = _RawCell(
                text=[],
                row_span=self._positive_int(attr_map, "rowspan"),
                col_span=self._positive_int(attr_map, "colspan"),
                header=tag == "th",
            )

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "template", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if not self._in_table or self._ignored_depth:
            return
        if tag in {"td", "th"} and self._current_cell is not None:
            assert self._current_row is not None
            self._current_row.append(self._current_cell)
            self._current_cell = None
        elif tag == "tr":
            if self._current_cell is not None:
                self.handle_endtag("td")
            if self._current_row is not None:
                self.rows.append(self._current_row)
                self._current_row = None
        elif tag == "table":
            if self._table_depth > 1:
                self._table_depth -= 1
            else:
                if self._current_cell is not None:
                    self.handle_endtag("td")
                if self._current_row is not None:
                    self.rows.append(self._current_row)
                self._current_row = None
                self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None and not self._ignored_depth:
            self._current_cell.text.append(data)


def _normalize_cell_text(parts: list[str]) -> str:
    value = "".join(parts).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def _escape_markdown(value: str) -> str:
    return value.replace("|", r"\|").replace("\r", "").replace("\n", "<br>")


def _grid_from_rows(rows: list[list[_RawCell]]) -> tuple[list[TableCell], list[list[int | None]], int, int, bool]:
    if not rows:
        raise HtmlTableParseError("table 没有任何 tr/td 单元格。")
    grid: list[list[int | None]] = []
    cells: list[TableCell] = []
    has_span = False
    for row_index, raw_row in enumerate(rows):
        while len(grid) <= row_index:
            grid.append([])
        col_cursor = 0
        for raw_cell in raw_row:
            while col_cursor < len(grid[row_index]) and grid[row_index][col_cursor] is not None:
                col_cursor += 1
            while len(grid[row_index]) < col_cursor:
                grid[row_index].append(None)
            while any(
                len(grid) <= row or len(grid[row]) <= col
                for row in range(row_index, row_index + raw_cell.row_span)
                for col in range(col_cursor, col_cursor + raw_cell.col_span)
            ):
                for row in range(row_index, row_index + raw_cell.row_span):
                    while len(grid) <= row:
                        grid.append([])
                    while len(grid[row]) < col_cursor + raw_cell.col_span:
                        grid[row].append(None)
                break
            for row in range(row_index, row_index + raw_cell.row_span):
                while len(grid) <= row:
                    grid.append([])
                while len(grid[row]) < col_cursor + raw_cell.col_span:
                    grid[row].append(None)
                for col in range(col_cursor, col_cursor + raw_cell.col_span):
                    if grid[row][col] is not None:
                        raise HtmlTableParseError(
                            f"table 单元格 span 重叠: r{row_index}c{col_cursor}。"
                        )
                    grid[row][col] = len(cells)
            has_span = has_span or raw_cell.row_span > 1 or raw_cell.col_span > 1
            cells.append(
                TableCell(
                    text=_normalize_cell_text(raw_cell.text),
                    start_row=row_index,
                    start_col=col_cursor,
                    row_span=raw_cell.row_span,
                    col_span=raw_cell.col_span,
                    column_header=raw_cell.header or row_index == 0,
                )
            )
            col_cursor += raw_cell.col_span
    num_rows = max(len(grid), len(rows))
    num_cols = max((len(row) for row in grid), default=0)
    if num_cols == 0 or not cells:
        raise HtmlTableParseError("table 没有有效单元格。")
    return cells, grid, num_rows, num_cols, has_span


def render_html_table(html: str) -> RenderedTable:
    """解析第一个 table 片段并生成标准 pipe Markdown。"""

    parser = _TableParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as error:  # HTMLParser should not leak parser-specific errors
        raise HtmlTableParseError(f"HTML table 解析失败: {type(error).__name__}") from error
    if parser._in_table:
        parser.handle_endtag("table")
    cells, grid, num_rows, num_cols, has_span = _grid_from_rows(parser.rows)
    lines: list[str] = []
    for row_index in range(num_rows):
        values: list[str] = []
        row = grid[row_index] if row_index < len(grid) else []
        for col_index in range(num_cols):
            cell_index = row[col_index] if col_index < len(row) else None
            values.append(
                _escape_markdown(cells[cell_index].text)
                if cell_index is not None and cells[cell_index].start_row == row_index and cells[cell_index].start_col == col_index
                else ""
            )
        lines.append("| " + " | ".join(values) + " |")
        if row_index == 0:
            lines.append("| " + " | ".join("---" for _ in range(num_cols)) + " |")
    return RenderedTable(
        markdown="\n".join(lines),
        cells=tuple(cells),
        num_rows=num_rows,
        num_cols=num_cols,
        nonempty_cell_count=sum(bool(cell.text.strip()) for cell in cells),
        markdown_representation_loss=has_span,
    )
