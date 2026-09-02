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
from document_parser.domain.quality.evidence.context import EvidenceContext
from document_parser.domain.quality.rules.safety import (
    QL_ASSET_001_DataUriRemains,
    QL_ASSET_002_LocalReferenceIntegrity,
    QL_CONT_004_EmptyNormalizedContent,
    QL_FMT_001_MojibakeDetected,
    QL_TBL_003_EmptyTableStructure,
    QL_TBL_009_HtmlTableRepresentation,
)


def _document(markdown: str, *, tables: list[ParsedTable] | None = None) -> ParsedDocument:
    block = DocumentBlock(
        id=uuid4(),
        kind=BlockKind.PARAGRAPH,
        markdown=markdown,
    )
    return ParsedDocument(
        filename="sample.md",
        file_type="text/markdown",
        markdown=markdown,
        blocks=[block],
        tables=tables or [],
        confidence=ParseConfidence(),
        provenance=ParserProvenance(parser_id="test", version="test"),
        source_sha256="b" * 64,
    )


def test_empty_and_mojibake_are_hard_detected():
    empty = _document("").model_copy(
        update={
            "blocks": [
                DocumentBlock(id=uuid4(), kind=BlockKind.PARAGRAPH, markdown=" ")
            ]
        }
    )
    assert QL_CONT_004_EmptyNormalizedContent().execute(EvidenceContext(empty)).issues
    malformed = _document("正文��乱码��")
    result = QL_FMT_001_MojibakeDetected().execute(EvidenceContext(malformed))
    assert result.issues[0].category == "content_readability"
    assert result.issues[0].severity.value == "critical"


def test_data_uri_and_missing_asset_reference_are_reported():
    document = _document("![图](data:image/png;base64,AAAA)\n![缺失](images/missing.png)")
    assert QL_ASSET_001_DataUriRemains().execute(EvidenceContext(document)).issues
    result = QL_ASSET_002_LocalReferenceIntegrity().execute(EvidenceContext(document))
    assert result.issues[0].evidence["missing_paths"] == ["images/missing.png"]


def test_empty_table_and_html_representation_are_reported():
    block_id = uuid4()
    table = ParsedTable(
        table_id="empty",
        block_id=block_id,
        html="<table><tr><td></td></tr></table>",
        markdown="",
        cells=[],
    )
    block = DocumentBlock(id=block_id, kind=BlockKind.TABLE, markdown=table.html or "")
    document = _document(table.html or "", tables=[table]).model_copy(update={"blocks": [block]})
    context = EvidenceContext(document)
    assert QL_TBL_003_EmptyTableStructure().execute(context).issues
    result = QL_TBL_009_HtmlTableRepresentation().execute(context)
    assert result.issues
    assert result.repair_proposals[0].rule_id == "QL-RPR-003"
