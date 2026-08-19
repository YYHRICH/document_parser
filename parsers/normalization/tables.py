"""解析器无关的表格网格归一化。"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

from document_parser.core.contracts import TableCell


@dataclass(frozen=True)
class TableGridNormalization:
    cells: tuple[TableCell, ...]
    num_rows: int
    num_cols: int
    warnings: tuple[str, ...] = ()
    holes: tuple[tuple[int, int], ...] = ()


def normalize_table_cells(
    cells: list[TableCell],
    *,
    declared_rows: int | None = None,
    declared_cols: int | None = None,
) -> TableGridNormalization:
    """去重并验证逻辑 cell 的占位关系，不修改 cell 正文。"""

    warnings: list[str] = []
    by_origin: dict[tuple[int, int], TableCell] = {}
    duplicate_count = 0
    for cell in sorted(cells, key=lambda value: (value.start_row, value.start_col)):
        origin = (cell.start_row, cell.start_col)
        previous = by_origin.get(origin)
        if previous is None:
            by_origin[origin] = cell
            continue
        duplicate_count += 1
        if previous.model_dump(exclude_none=True) != cell.model_dump(exclude_none=True):
            warnings.append(f"同一逻辑坐标存在冲突 cell: {origin}，保留首个证据。")
    if duplicate_count:
        warnings.append(f"去除 {duplicate_count} 个重复展开 cell。")

    logical_cells = tuple(by_origin.values())
    max_rows = max(
        (cell.start_row + cell.row_span for cell in logical_cells),
        default=0,
    )
    max_cols = max(
        (cell.start_col + cell.col_span for cell in logical_cells),
        default=0,
    )
    num_rows = max(max_rows, declared_rows or 0)
    num_cols = max(max_cols, declared_cols or 0)
    if declared_rows is not None and max_rows > declared_rows:
        warnings.append("cell 行跨度超出解析器声明尺寸，已扩展网格。")
    if declared_cols is not None and max_cols > declared_cols:
        warnings.append("cell 列跨度超出解析器声明尺寸，已扩展网格。")

    occupancy: dict[tuple[int, int], TableCell] = {}
    for cell in logical_cells:
        for row in range(cell.start_row, cell.start_row + cell.row_span):
            for col in range(cell.start_col, cell.start_col + cell.col_span):
                slot = (row, col)
                previous = occupancy.get(slot)
                if previous is not None and previous is not cell:
                    warnings.append(f"网格占位冲突: {slot}。")
                else:
                    occupancy[slot] = cell

    holes = tuple(
        (row, col)
        for row in range(num_rows)
        for col in range(num_cols)
        if (row, col) not in occupancy
    )
    if holes:
        warnings.append(f"数据网格存在 {len(holes)} 个未占位槽位。")
    return TableGridNormalization(
        cells=tuple(sorted(logical_cells, key=lambda value: (value.start_row, value.start_col))),
        num_rows=num_rows,
        num_cols=num_cols,
        warnings=tuple(dict.fromkeys(warnings)),
        holes=holes,
    )


class _HTMLTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict[str, object]]] = []
        self.current_row: list[dict[str, object]] | None = None
        self.current_cell: dict[str, object] | None = None
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_map = dict(attrs)
        if tag == "tr":
            self.current_row = []
        elif tag in {"td", "th"}:
            self.current_cell = {
                "rowspan": max(1, int(attrs_map.get("rowspan", "1") or "1")),
                "colspan": max(1, int(attrs_map.get("colspan", "1") or "1")),
                "header": tag == "th",
            }
            self.text_parts = []

    def handle_data(self, data: str) -> None:
        if self.current_cell is not None:
            self.text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.current_cell is not None:
            self.current_cell["text"] = "".join(self.text_parts).strip()
            if self.current_row is not None:
                self.current_row.append(self.current_cell)
            self.current_cell = None
        elif tag == "tr" and self.current_row:
            self.rows.append(self.current_row)
            self.current_row = None


def parse_html_table_cells(html: str) -> list[TableCell]:
    """把带 rowspan/colspan 的 HTML 表格放入真实 occupancy 网格。"""

    parser = _HTMLTableParser()
    try:
        parser.feed(html or "")
    except (TypeError, ValueError):
        return []

    occupied: set[tuple[int, int]] = set()
    cells: list[TableCell] = []
    for row_index, row in enumerate(parser.rows):
        col_index = 0
        for raw in row:
            while (row_index, col_index) in occupied:
                col_index += 1
            row_span = int(raw["rowspan"])
            col_span = int(raw["colspan"])
            cell = TableCell(
                text=str(raw.get("text", "")),
                start_row=row_index,
                start_col=col_index,
                row_span=row_span,
                col_span=col_span,
                column_header=bool(raw.get("header")) or row_index == 0,
            )
            cells.append(cell)
            for row_offset in range(row_span):
                for col_offset in range(col_span):
                    occupied.add((row_index + row_offset, col_index + col_offset))
            col_index += col_span
    return list(normalize_table_cells(cells).cells)


def cells_to_markdown(cells: list[TableCell] | tuple[TableCell, ...]) -> str:
    """以左上 cell 为事实来源生成兼容 Markdown 表格。"""

    if not cells:
        return ""
    rows = max(cell.start_row + cell.row_span for cell in cells)
    cols = max(cell.start_col + cell.col_span for cell in cells)
    grid = [["" for _ in range(cols)] for _ in range(rows)]
    for cell in cells:
        grid[cell.start_row][cell.start_col] = cell.text
    lines = ["| " + " | ".join(value or " " for value in grid[0]) + " |"]
    lines.append("| " + " | ".join("---" for _ in range(cols)) + " |")
    lines.extend("| " + " | ".join(value or " " for value in row) + " |" for row in grid[1:])
    return "\n".join(lines)
