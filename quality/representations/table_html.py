"""Parser-neutral HTML table parsing and conservative Markdown projection."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import re
from typing import Any


@dataclass(frozen=True)
class HtmlTableCell:
    """One origin cell from an HTML table."""

    text: str
    row_span: int
    col_span: int


@dataclass(frozen=True)
class HtmlTableStructure:
    """Parsed HTML table structure, retaining spans and the rectangular grid."""

    rows: tuple[tuple[HtmlTableCell, ...], ...]
    grid: tuple[tuple[str, ...], ...]
    complete: bool
    has_spans: bool

    @property
    def shape(self) -> tuple[int, int]:
        return (len(self.grid), len(self.grid[0]) if self.grid else 0)


class _TableParser(HTMLParser):
    """Parse one HTML table with only the structure a Markdown view needs."""

    _INLINE_MARKERS = {
        "b": "**",
        "strong": "**",
        "i": "*",
        "em": "*",
        "code": "`",
        "del": "~~",
        "s": "~~",
        "strike": "~~",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[HtmlTableCell]] = []
        self._table_depth = 0
        self._current_row: list[HtmlTableCell] | None = None
        self._current_cell: dict[str, Any] | None = None
        self._invalid = False

    @staticmethod
    def _span(attrs: dict[str, str | None], name: str) -> int | None:
        value = attrs.get(name, "1")
        try:
            parsed = int(value or "1")
        except ValueError:
            return None
        return parsed if parsed > 0 else None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            if self._table_depth:
                # Nested tables cannot be represented faithfully in one pipe
                # table, so reject the fragment rather than flattening it.
                self._invalid = True
            self._table_depth += 1
            return
        if self._table_depth != 1:
            return
        if tag == "tr":
            if self._current_cell is not None or self._current_row is not None:
                self._invalid = True
            self._current_row = []
            return
        if tag in {"td", "th"}:
            if self._current_row is None or self._current_cell is not None:
                self._invalid = True
                return
            attr_map = {name.lower(): value for name, value in attrs}
            row_span = self._span(attr_map, "rowspan")
            col_span = self._span(attr_map, "colspan")
            if row_span is None or col_span is None:
                self._invalid = True
                return
            self._current_cell = {
                "parts": [],
                "row_span": row_span,
                "col_span": col_span,
            }
            return
        if self._current_cell is not None:
            marker = self._INLINE_MARKERS.get(tag)
            if marker is not None:
                self._current_cell["parts"].append(marker)
            elif tag == "a":
                href = dict(attrs).get("href")
                if href:
                    self._current_cell["parts"].append("[")
                    self._current_cell.setdefault("links", []).append(href)
            elif tag == "img":
                attr_map = dict(attrs)
                src = attr_map.get("src")
                alt = attr_map.get("alt") or ""
                self._current_cell["parts"].append(
                    f"![{alt}]({src})" if src else alt
                )
            elif tag == "br":
                self._current_cell["parts"].append("\n")
            elif tag in {"p", "div", "li"} and self._current_cell["parts"]:
                self._current_cell["parts"].append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "table":
            if self._table_depth == 1 and (
                self._current_cell is not None or self._current_row is not None
            ):
                self._invalid = True
            self._table_depth = max(0, self._table_depth - 1)
            return
        if self._table_depth != 1:
            return
        if tag in {"td", "th"}:
            if self._current_cell is None or self._current_row is None:
                self._invalid = True
                return
            self._current_row.append(
                HtmlTableCell(
                    text="".join(self._current_cell["parts"]),
                    row_span=self._current_cell["row_span"],
                    col_span=self._current_cell["col_span"],
                )
            )
            self._current_cell = None
            return
        if tag == "tr":
            if self._current_cell is not None or self._current_row is None:
                self._invalid = True
                return
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None
            return
        if self._current_cell is not None:
            marker = self._INLINE_MARKERS.get(tag)
            if marker is not None:
                self._current_cell["parts"].append(marker)
            elif tag == "a":
                links = self._current_cell.get("links", [])
                if links:
                    self._current_cell["parts"].append(f"]({links.pop()})")
            elif tag in {"p", "div", "li"}:
                self._current_cell["parts"].append("\n")

    def handle_data(self, data: str) -> None:
        if self._table_depth == 1 and self._current_cell is not None:
            self._current_cell["parts"].append(data)

    @property
    def valid(self) -> bool:
        return (
            not self._invalid
            and self._table_depth == 0
            and self._current_row is None
            and self._current_cell is None
            and bool(self.rows)
        )


def _normalise_cell_text(value: str) -> str:
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in value.splitlines()]
    return "<br>".join(line for line in lines if line)


def _escape_markdown_cell(value: str) -> str:
    return _normalise_cell_text(value).replace("\\", "\\\\").replace("|", "\\|")


def _grid_from_rows(rows: list[list[HtmlTableCell]]) -> tuple[tuple[tuple[str, ...], ...], bool] | None:
    occupied: set[tuple[int, int]] = set()
    origins: dict[tuple[int, int], str] = {}
    max_row = -1
    max_col = -1

    for row_index, cells in enumerate(rows):
        column = 0
        for cell in cells:
            while (row_index, column) in occupied:
                column += 1
            for span_row in range(row_index, row_index + cell.row_span):
                for span_col in range(column, column + cell.col_span):
                    position = (span_row, span_col)
                    if position in occupied:
                        return None
                    occupied.add(position)
                    max_row = max(max_row, span_row)
                    max_col = max(max_col, span_col)
            origins[(row_index, column)] = cell.text
            column += cell.col_span

    if max_row < 0 or max_col < 0:
        return None
    height = max_row + 1
    width = max_col + 1
    grid = [["" for _ in range(width)] for _ in range(height)]
    for (row, column), text in origins.items():
        grid[row][column] = text
    complete = len(occupied) == height * width
    return tuple(tuple(row) for row in grid), complete


def parse_html_table(html: str) -> HtmlTableStructure | None:
    """Return a structural representation for one complete HTML table."""
    parser = _TableParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return None
    if not parser.valid:
        return None
    grid_result = _grid_from_rows(parser.rows)
    if grid_result is None:
        return None
    grid, complete = grid_result
    rows = tuple(tuple(row) for row in parser.rows)
    return HtmlTableStructure(
        rows=rows,
        grid=grid,
        complete=complete,
        has_spans=any(
            cell.row_span > 1 or cell.col_span > 1
            for row in rows
            for cell in row
        ),
    )


def _markdown_from_grid(grid: tuple[tuple[str, ...], ...]) -> str | None:
    if not grid or not grid[0]:
        return None
    width = len(grid[0])
    if any(len(row) != width for row in grid):
        return None

    def line(values: tuple[str, ...]) -> str:
        return "| " + " | ".join(_escape_markdown_cell(value) for value in values) + " |"

    return "\n".join(
        [line(grid[0]), "| " + " | ".join(["---"] * width) + " |", *[line(row) for row in grid[1:]]]
    )


def html_table_to_markdown(html: str, *, allow_lossy: bool = True) -> str | None:
    """Project one complete HTML table to pipe Markdown.

    ``allow_lossy=False`` rejects rowspan/colspan tables because pipe Markdown
    has no native span representation.  The default keeps the historical
    projection function available for review-only candidates.
    """
    structure = parse_html_table(html)
    if structure is None or not structure.complete:
        return None
    if structure.has_spans and not allow_lossy:
        return None
    return _markdown_from_grid(structure.grid)


_TABLE_TAG = re.compile(r"</?table(?:\s[^>]*)?>", re.IGNORECASE)
_TABLE_START = re.compile(r"<table(?:\s[^>]*)?>", re.IGNORECASE)


def _table_end(markdown: str, start: int) -> int | None:
    depth = 0
    for match in _TABLE_TAG.finditer(markdown, start):
        token = match.group(0).lstrip().lower()
        if token.startswith("</"):
            depth -= 1
            if depth == 0:
                return match.end()
        else:
            depth += 1
    return None


def _inside_fenced_code(markdown: str, position: int) -> bool:
    active_fence: str | None = None
    for line in markdown[:position].splitlines():
        match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if match is None:
            continue
        marker = match.group(1)
        if active_fence is None:
            active_fence = marker
        elif marker[0] == active_fence[0] and len(marker) >= len(active_fence):
            active_fence = None
    return active_fence is not None


def convert_html_tables(markdown: str, *, allow_lossy: bool = False) -> tuple[str, int]:
    """Replace only complete, safe HTML table fragments with pipe Markdown."""
    output: list[str] = []
    cursor = 0
    converted = 0
    while True:
        start_match = _TABLE_START.search(markdown, cursor)
        if start_match is None:
            output.append(markdown[cursor:])
            break
        if _inside_fenced_code(markdown, start_match.start()):
            output.append(markdown[cursor:start_match.end()])
            cursor = start_match.end()
            continue
        output.append(markdown[cursor:start_match.start()])
        end = _table_end(markdown, start_match.start())
        if end is None:
            output.append(markdown[start_match.start():])
            break
        fragment = markdown[start_match.start():end]
        replacement = html_table_to_markdown(fragment, allow_lossy=allow_lossy)
        if replacement is None:
            output.append(fragment)
        else:
            output.append(replacement)
            converted += 1
        cursor = end
    return "".join(output), converted
