"""把解析器输出的 Markdown 转换为统一文档块和可证实的管道表格。

本文件不是解析器，不声明 ``ParserCapability``，也不会被网关注册。MarkItDown
输出 Markdown 后调用这里获得标题、段落与章节路径。

维护边界：这里只处理两个解析器共同需要的基础切块。它不是完整 CommonMark
实现；如果以后需要代码块、嵌套列表或原生表格语义，应扩展统一块构建能力，
不要把内部工具注册为独立解析器。
"""

import re

from ...domain.model.contracts import (
    BlockKind,
    DocumentBlock,
    ParsedTable,
    SourceAnchor,
    TableCell,
    TableGridSlot,
    TableSlotKind,
)


_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")


def _split_pipe_row(line: str) -> list[str]:
    """拆分 Markdown 管道行；只把未转义的竖线当作列边界。"""

    value = line.strip()
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|") and not value.endswith(r"\|"):
        value = value[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in value:
        if escaped:
            if char in {"|", "\\"}:
                current.append(char)
            else:
                current.extend(["\\", char])
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def _is_separator_row(line: str) -> bool:
    cells = _split_pipe_row(line)
    return bool(cells) and all(_SEPARATOR_CELL.fullmatch(cell.replace(" ", "")) for cell in cells)


def _pipe_table_end(lines: list[str], start: int) -> int | None:
    if start + 1 >= len(lines):
        return None
    if not lines[start].strip().startswith("|") or not _is_separator_row(lines[start + 1]):
        return None
    end = start + 2
    while end < len(lines) and lines[end].strip().startswith("|"):
        end += 1
    return end


def blocks_and_tables_from_markdown(text: str) -> tuple[list[DocumentBlock], list[ParsedTable]]:
    """识别标题、段落和标准管道表格，并保留 Markdown 派生网格。

    这里只声明解析器输出中可直接观察到的行列关系。Markdown 无法表达合并
    单元格、源文件坐标或筛选视图，因此这些能力不会被伪造。
    """

    lines = text.splitlines()
    blocks: list[DocumentBlock] = []
    tables: list[ParsedTable] = []
    section_path: list[str] = []
    paragraph_lines: list[str] = []

    def append_block(block: DocumentBlock) -> None:
        blocks.append(block.model_copy(update={"order_index": len(blocks)}))

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        paragraph = "\n".join(paragraph_lines).strip()
        append_block(
            DocumentBlock(
                kind=BlockKind.PARAGRAPH,
                markdown=paragraph,
                anchor=SourceAnchor(
                    section_path=section_path.copy(),
                    original_text=paragraph,
                ),
            )
        )
        paragraph_lines.clear()

    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()
        table_end = _pipe_table_end(lines, index)
        if table_end is not None:
            flush_paragraph()
            table_index = len(tables)
            table_id = f"markitdown-table-{table_index:04d}"
            table_lines = [item.strip() for item in lines[index:table_end]]
            markdown = "\n".join(table_lines)
            block = DocumentBlock(
                kind=BlockKind.TABLE,
                markdown=markdown,
                source_block_id=table_id,
                anchor=SourceAnchor(
                    section_path=section_path.copy(),
                    container="markdown_table",
                    original_text=markdown,
                ),
                metadata={"table_id": table_id},
            )
            append_block(block)

            rows = [_split_pipe_row(table_lines[0])]
            rows.extend(_split_pipe_row(item) for item in table_lines[2:])
            width = max((len(row) for row in rows), default=0)
            rows = [row + [""] * (width - len(row)) for row in rows]
            explicit_header_row = 0
            header_inferred = False
            if rows and not any(value.strip() for value in rows[0]):
                first_nonempty = next(
                    (row for row, values in enumerate(rows[1:], start=1) if any(v.strip() for v in values)),
                    0,
                )
                explicit_header_row = first_nonempty
                header_inferred = first_nonempty != 0
            cells: list[TableCell] = []
            grid: list[list[TableGridSlot]] = []
            for row_index, row in enumerate(rows):
                slots: list[TableGridSlot] = []
                for col_index, value in enumerate(row):
                    cell_id = f"{table_id}:r{row_index}c{col_index}"
                    cells.append(
                        TableCell(
                            cell_id=cell_id,
                            text=value,
                            display_value=value,
                            normalized_value=value.strip(),
                            value_type="string",
                            start_row=row_index,
                            start_col=col_index,
                            # Some MarkItDown DOCX tables start with an empty row before
                            # the real header. Keep that leading row inside the header
                            # region so it remains contiguous; the quality layer ignores
                            # empty path segments and marks this recovery as inferred.
                            column_header=row_index <= explicit_header_row,
                            source_anchor=SourceAnchor(
                                container="markdown_table",
                                table_cell=f"r{row_index}c{col_index}",
                                original_text=value,
                            ),
                        )
                    )
                    slots.append(TableGridSlot(kind=TableSlotKind.ORIGIN, cell_id=cell_id))
                grid.append(slots)
            tables.append(
                ParsedTable(
                    table_id=table_id,
                    block_id=block.id,
                    markdown=markdown,
                    num_rows=len(rows),
                    num_cols=width,
                    cells=cells,
                    grid=grid,
                    source_container="markdown_table",
                    metadata={
                        "structure_source": "markdown_pipe_table",
                        "header_inferred_from_first_nonempty_row": header_inferred,
                        "markdown_rendering": "pipe",
                    },
                )
            )
            index = table_end
            continue

        if not line:
            flush_paragraph()
        elif line.startswith("#"):
            flush_paragraph()
            level = len(line) - len(line.lstrip("#"))
            title = line[level:].strip()
            section_path[:] = section_path[: max(0, level - 1)]
            section_path.append(title)
            append_block(
                DocumentBlock(
                    kind=BlockKind.HEADING,
                    markdown=line,
                    heading_level=level,
                    anchor=SourceAnchor(
                        section_path=section_path.copy(),
                        original_text=title,
                    ),
                )
            )
        else:
            paragraph_lines.append(line)
        index += 1
    flush_paragraph()
    return blocks, tables


def blocks_from_markdown(text: str) -> list[DocumentBlock]:
    """把 Markdown 标题和段落切分为统一块，供 MarkItDown 解析器复用。

    切分规则刻意保持简单且稳定：
    - 空行结束当前段落；
    - 以 ``#`` 开头的非空行生成标题块；
    - 其余连续行合并成一个段落，保留内部换行；
    - 标题层级写入 ``section_path``，供检索结果回溯章节。
    """

    # 最终输出顺序必须与原文顺序一致，下游阅读顺序依赖这一不变量。
    blocks: list[DocumentBlock] = []
    # 当前标题栈，例如 ["第一章", "1.1 范围"]；新标题会按级别截断旧分支。
    section_path: list[str] = []
    # 暂存连续的非标题行，遇到空行、标题或 EOF 时一次性写入段落块。
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        """把当前累计的连续文本写入一个段落块。"""

        if not paragraph_lines:
            return
        # 先计算一次，避免 markdown 与 original_text 因未来修改出现差异。
        paragraph = "\n".join(paragraph_lines).strip()
        blocks.append(
            DocumentBlock(
                kind=BlockKind.PARAGRAPH,
                markdown=paragraph,
                anchor=SourceAnchor(
                    section_path=section_path.copy(),
                    original_text=paragraph,
                ),
            )
        )
        # clear() 保留列表对象，供闭包后续继续累计下一段。
        paragraph_lines.clear()

    for raw_line in text.splitlines():
        # 当前基线忽略行首/尾空白；若未来要保留代码块缩进，不能直接修改这里，
        # 应先引入真正的 Markdown 语法解析器。
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        if line.startswith("#"):
            flush_paragraph()
            # 连续 # 数量决定标题级别；section_path 仅保存层级，不保存 #。
            level = len(line) - len(line.lstrip("#"))
            title = line[level:].strip()
            # 同级标题替换当前层，低级标题保留父级，高级标题截断子级。
            section_path[:] = section_path[: max(0, level - 1)]
            section_path.append(title)
            blocks.append(
                DocumentBlock(
                    kind=BlockKind.HEADING,
                    markdown=line,
                    anchor=SourceAnchor(
                        section_path=section_path.copy(),
                        original_text=title,
                    ),
                )
            )
        else:
            paragraph_lines.append(line)
    # 文件末尾通常没有空行，必须显式提交最后一个段落。
    flush_paragraph()

    return blocks
