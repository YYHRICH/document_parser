"""解析结果归一层的确定性回归。"""

from hashlib import sha256
from uuid import uuid4

from document_parser.core.contracts import (
    AssetKind,
    BlockKind,
    DocumentBlock,
    DocumentAsset,
    ParsedDocument,
    ParsedTable,
    ParseConfidence,
    ParserProvenance,
    SourceAnchor,
    TableCell,
)
from document_parser.parsers.normalization import (
    normalize_parsed_document,
    normalize_table_cells,
    parse_html_table_cells,
)


def test_mineru_html_parser_reserves_rowspan_slots():
    cells = parse_html_table_cells(
        """
        <table>
          <tr><th rowspan="2">Group</th><th colspan="2">Value</th></tr>
          <tr><th>A</th><th>B</th></tr>
          <tr><td rowspan="2">R1</td><td>1</td><td>2</td></tr>
          <tr><td>3</td><td>4</td></tr>
        </table>
        """
    )

    by_origin = {(cell.start_row, cell.start_col): cell for cell in cells}
    assert len(cells) == 9
    assert by_origin[(0, 0)].row_span == 2
    assert by_origin[(0, 1)].col_span == 2
    assert by_origin[(2, 0)].row_span == 2
    assert (1, 1) in by_origin and (1, 2) in by_origin

    result = normalize_table_cells(cells, declared_rows=4, declared_cols=3)
    assert result.num_rows == 4
    assert result.num_cols == 3
    assert result.holes == ()


def test_docling_repeated_span_cells_are_deduplicated_without_text_rewrite():
    first = TableCell(text="Merged", start_row=0, start_col=0, col_span=2)
    duplicate = first.model_copy()
    other = TableCell(text="B", start_row=1, start_col=0)

    result = normalize_table_cells(
        [first, duplicate, other], declared_rows=2, declared_cols=2
    )

    assert len(result.cells) == 2
    assert {cell.text for cell in result.cells} == {"Merged", "B"}
    assert any("重复展开" in warning for warning in result.warnings)


def test_document_normalization_preserves_markdown_and_records_provenance():
    block_late = DocumentBlock(
        id=uuid4(),
        source_block_id="late",
        order_index=8,
        kind=BlockKind.PARAGRAPH,
        text="正文 B",
        markdown="正文 B",
    )
    block_early = DocumentBlock(
        id=uuid4(),
        source_block_id="early",
        order_index=2,
        kind=BlockKind.PARAGRAPH,
        text="正文 A",
        markdown="正文 A",
    )
    table_block = DocumentBlock(
        id=uuid4(),
        source_block_id="table",
        order_index=4,
        kind=BlockKind.TABLE,
        text="| A |\n| --- |\n| 1 |",
        markdown="| A |\n| --- |\n| 1 |",
    )
    table = ParsedTable(
        table_id="table-001",
        block_id=table_block.id,
        num_rows=1,
        num_cols=1,
        cells=[TableCell(text="A", start_row=0, start_col=0)],
    )
    document = ParsedDocument(
        filename="fixture.pdf",
        file_type="application/pdf",
        markdown="正文 B\n\n正文 A\n\n| A |\n| --- |\n| 1 |",
        blocks=[block_late, block_early, table_block],
        tables=[table],
        confidence=ParseConfidence(),
        provenance=ParserProvenance(parser_id="fixture"),
        source_sha256=sha256(b"fixture").hexdigest(),
    )

    normalized = normalize_parsed_document(document, parser_label="fixture")

    assert normalized.markdown == document.markdown
    assert [block.source_block_id for block in normalized.blocks] == [
        "early",
        "table",
        "late",
    ]
    assert [block.order_index for block in normalized.blocks] == [0, 1, 2]
    assert normalized.provenance.parameters["normalization"] == {
        "version": "normalization-v1",
        "parser": "fixture",
        "table_count": 1,
        "warning_count": 0,
        "merged_fragment_count": 0,
        "reordered_page_count": 0,
        "stable_block_id_version": "uuid5-source-v1",
    }

    repeated = normalize_parsed_document(document, parser_label="fixture")
    assert [block.id for block in normalized.blocks] == [
        block.id for block in repeated.blocks
    ]
    assert normalized.tables[0].block_id == normalized.blocks[1].id


def test_asset_block_references_follow_stable_block_ids():
    block = DocumentBlock(
        id=uuid4(),
        source_block_id="figure-1",
        order_index=0,
        kind=BlockKind.IMAGE,
        text="figure",
        markdown="figure",
    )
    document = ParsedDocument(
        filename="asset.pdf",
        file_type="application/pdf",
        markdown="figure",
        blocks=[block],
        assets=[
            DocumentAsset(
                kind=AssetKind.IMAGE,
                path="figure.png",
                file_type="image/png",
                content=b"png",
                referenced_by_block_ids=[str(block.id)],
            )
        ],
        confidence=ParseConfidence(),
        provenance=ParserProvenance(parser_id="fixture"),
        source_sha256=sha256(b"asset").hexdigest(),
    )

    normalized = normalize_parsed_document(document, parser_label="fixture")

    assert normalized.assets[0].referenced_by_block_ids == [
        str(normalized.blocks[0].id)
    ]


def test_cross_page_table_is_merged_only_when_root_markdown_can_be_projected():
    first_block = DocumentBlock(
        id=uuid4(),
        source_block_id="table-page-1",
        order_index=0,
        kind=BlockKind.TABLE,
        text="| A | B |\n| --- | --- |\n| x | 1 |",
        markdown="| A | B |\n| --- | --- |\n| x | 1 |",
        anchor=SourceAnchor(
            page_number=1,
            bbox=(0, 600, 500, 760),
            page_width=500,
            page_height=800,
        ),
    )
    second_block = DocumentBlock(
        id=uuid4(),
        source_block_id="table-page-2",
        order_index=1,
        kind=BlockKind.TABLE,
        text="| A | B |\n| --- | --- |\n| y | 2 |",
        markdown="| A | B |\n| --- | --- |\n| y | 2 |",
        anchor=SourceAnchor(
            page_number=2,
            bbox=(0, 30, 500, 180),
            page_width=500,
            page_height=800,
        ),
    )
    first_table = ParsedTable(
        table_id="table-001",
        block_id=first_block.id,
        page_number=1,
        num_rows=2,
        num_cols=2,
        cells=[
            TableCell(text="A", start_row=0, start_col=0, column_header=True),
            TableCell(text="B", start_row=0, start_col=1, column_header=True),
            TableCell(text="x", start_row=1, start_col=0),
            TableCell(text="1", start_row=1, start_col=1),
        ],
    )
    second_table = ParsedTable(
        table_id="table-002",
        block_id=second_block.id,
        page_number=2,
        num_rows=2,
        num_cols=2,
        cells=[
            TableCell(text="A", start_row=0, start_col=0, column_header=True),
            TableCell(text="B", start_row=0, start_col=1, column_header=True),
            TableCell(text="y", start_row=1, start_col=0),
            TableCell(text="2", start_row=1, start_col=1),
        ],
    )
    root_markdown = first_block.markdown + "\n\n" + second_block.markdown
    document = ParsedDocument(
        filename="continuation.pdf",
        file_type="application/pdf",
        markdown=root_markdown,
        blocks=[first_block, second_block],
        tables=[first_table, second_table],
        confidence=ParseConfidence(),
        provenance=ParserProvenance(parser_id="fixture"),
    )

    normalized = normalize_parsed_document(document, parser_label="fixture")

    assert len(normalized.tables) == 1
    assert len(normalized.blocks) == 1
    assert normalized.tables[0].num_rows == 3
    assert "| y | 2 |" in normalized.markdown
    assert normalized.tables[0].metadata["merged_fragments"] == [
        "table-001",
        "table-002",
    ]


def test_two_column_reordering_requires_full_bbox_evidence():
    def make_block(name: str, order: int, x: float, y: float) -> DocumentBlock:
        return DocumentBlock(
            id=uuid4(),
            source_block_id=name,
            order_index=order,
            kind=BlockKind.PARAGRAPH,
            text=name,
            markdown=name,
            anchor=SourceAnchor(
                page_number=1,
                bbox=(x, y, x + 150, y + 40),
                page_width=700,
                page_height=900,
            ),
        )

    document = ParsedDocument(
        filename="columns.pdf",
        file_type="application/pdf",
        markdown="L1\nL2\nR1\nR2",
        blocks=[
            make_block("L1", 0, 40, 100),
            make_block("R1", 1, 400, 100),
            make_block("L2", 2, 40, 180),
            make_block("R2", 3, 400, 180),
        ],
        confidence=ParseConfidence(),
        provenance=ParserProvenance(parser_id="fixture"),
    )

    normalized = normalize_parsed_document(document, parser_label="fixture")

    assert [block.source_block_id for block in normalized.blocks] == [
        "L1",
        "L2",
        "R1",
        "R2",
    ]
    assert normalized.provenance.parameters["normalization"]["reordered_page_count"] == 1
