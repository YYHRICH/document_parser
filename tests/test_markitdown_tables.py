import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.domain.model.contracts import BlockKind  # noqa: E402
from document_parser.domain.quality.rules.tables import analyze_grid  # noqa: E402
from document_parser.infra.parsers.markdown_normalization import (  # noqa: E402
    blocks_and_tables_from_markdown,
)


def test_markdown_pipe_table_becomes_structured_table() -> None:
    markdown = """# 标题

| 字段 | 类型 |
| --- | --- |
| id | INT |
"""

    blocks, tables = blocks_and_tables_from_markdown(markdown)

    assert [block.kind for block in blocks] == [BlockKind.HEADING, BlockKind.TABLE]
    assert len(tables) == 1
    assert (tables[0].num_rows, tables[0].num_cols) == (2, 2)
    assert [cell.text for cell in tables[0].cells] == ["字段", "类型", "id", "INT"]
    analysis = analyze_grid(tables[0])
    assert analysis.valid is True
    assert analysis.header_rows == [0]
    assert analysis.header_inferred is True


def test_markitdown_blank_header_keeps_contiguous_inferred_header_region() -> None:
    markdown = """|  |  |
| --- | --- |
| 字段 | 类型 |
| id | INT |
"""

    _, tables = blocks_and_tables_from_markdown(markdown)

    analysis = analyze_grid(tables[0])
    assert analysis.valid is True
    assert analysis.header_rows == [0, 1]
    assert analysis.header_inferred is True
    assert not any(
        issue.category == "table_header_structure" for issue in analysis.issues
    )
