from __future__ import annotations

from uuid import uuid4

from document_parser.domain.model.contracts import (
    BlockKind,
    DocumentBlock,
    ParsedDocument,
    ParsedTable,
    ParseConfidence,
    ParserProvenance,
)
from document_parser.domain.quality.renderers.table_markdown import render_html_table
from document_parser.domain.quality.repairs.registry import (
    apply_document_repairs,
    replay_repair,
)


def _document(html: str) -> ParsedDocument:
    block = DocumentBlock(id=uuid4(), kind=BlockKind.TABLE, markdown=html)
    table = ParsedTable(table_id="table-1", block_id=block.id, html=html, markdown=html)
    return ParsedDocument(
        filename="sample.html",
        file_type="text/html",
        markdown=html,
        blocks=[block],
        tables=[table],
        confidence=ParseConfidence(),
        provenance=ParserProvenance(parser_id="test", version="test"),
        source_sha256="a" * 64,
    )


def test_render_html_table_decodes_entities_and_expands_spans():
    result = render_html_table(
        "<table><tr><th>A</th><th colspan='2'>B &amp; C</th></tr>"
        "<tr><td rowspan='2'>x</td><td>y|1</td><td>z</td></tr>"
        "<tr><td>q</td><td>r</td></tr></table>"
    )
    assert "B & C" in result.markdown
    assert r"y\|1" in result.markdown
    assert result.num_rows == 3
    assert result.num_cols == 3
    assert result.markdown_representation_loss is True
    assert any(cell.row_span == 2 for cell in result.cells)


def test_document_repair_synchronizes_document_block_and_table():
    html = "<table><tr><td>A</td><td>B</td></tr><tr><td>1</td><td>2</td></tr></table>"
    document = _document(html)
    result = apply_document_repairs(document, document_key="doc")
    assert result.rejected == ()
    assert [repair.rule_id for repair in result.applied] == ["QL-RPR-003"]
    assert "<table" not in result.document.markdown
    assert result.document.blocks[0].markdown == result.document.tables[0].markdown
    repair = result.applied[0]
    assert replay_repair(repair.evidence["before"], repair) == repair.evidence["after"]


def test_document_repair_rejects_missing_table_block_without_overwrite():
    html = "<table><tr><td>A</td></tr></table>"
    document = _document(html).model_copy(update={"blocks": []})
    result = apply_document_repairs(document, document_key="doc")
    assert not result.applied
    assert result.rejected
    assert result.document.markdown == html
    assert result.document.tables[0].html == html
