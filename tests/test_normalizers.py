import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.domain.normalization import (  # noqa: E402
    ParserNormalizationBundle,
    make_stable_block_id,
    make_stable_document_id,
    make_stable_table_id,
    stable_uuid,
)
from document_parser.domain.model.contracts import (  # noqa: E402
    BlockKind,
    DocumentBlock,
    EvidenceAvailability,
    EvidenceCapability,
    ParseRequest,
    ParseConfidence,
    ParserNativeResult,
    ParserProvenance,
    RoutingMode,
    RoutingDecision,
    DocumentSignals,
)
from document_parser.infra.parsers.docling import DoclingParser  # noqa: E402


def test_stable_uuid_is_deterministic() -> None:
    first = stable_uuid("document", "abc", "docling")
    second = stable_uuid("document", "abc", "docling")
    third = stable_uuid("document", "abc", "mineru")

    assert first == second
    assert first != third


def test_bundle_to_parsed_document_preserves_common_fields() -> None:
    document_id = make_stable_document_id(
        source_sha256="a" * 64,
        parser_id="mineru",
        parser_version="3.4.4",
    )
    block_id = make_stable_block_id(
        document_id=document_id,
        source_block_id="mineru-content-0001",
        order_index=0,
        kind="heading",
        text="标题",
    )
    block = DocumentBlock(
        id=block_id,
        source_block_id="mineru-content-0001",
        order_index=0,
        kind=BlockKind.HEADING,
        native_type="heading",
        text="标题",
        heading_level=1,
        markdown="# 标题",
    )
    bundle = ParserNormalizationBundle(
        document_id=document_id,
        filename="paper.pdf",
        file_type="application/pdf",
        source_size_bytes=1024,
        source_sha256="a" * 64,
        routing_decision=RoutingDecision(
            mode=RoutingMode.AUTO,
            selected_parser_id="mineru",
            reason="test",
            signals=DocumentSignals(extension=".pdf", size_bytes=1024),
        ),
        markdown="# 标题",
        blocks=[block],
        confidence=ParseConfidence(),
        provenance=ParserProvenance(parser_id="mineru", version="3.4.4"),
        capabilities={
            "page_bbox": EvidenceCapability(
                state=EvidenceAvailability.AVAILABLE,
                granularity="block",
                evidence={"page_count": 1},
            ),
            "table_cells": EvidenceCapability(
                state=EvidenceAvailability.UNAVAILABLE,
                reason="无表格",
            ),
        },
    )

    parsed_document = bundle.to_parsed_document()

    assert parsed_document.document_id == document_id
    assert parsed_document.blocks[0].id == block_id
    assert parsed_document.capabilities["table_cells"].state.value == "unavailable"
    assert parsed_document.capabilities["table_cells"].reason == "无表格"


def test_bundle_can_be_recreated_from_parsed_document() -> None:
    document_id = make_stable_document_id(
        source_sha256="b" * 64,
        parser_id="docling",
        parser_version="docling",
    )
    bundle = ParserNormalizationBundle.from_minimal_markdown(
        document_id=document_id,
        filename="note.md",
        file_type="text/markdown",
        markdown="# 标题",
        parser_id="docling",
        parser_version="docling",
        source_sha256="b" * 64,
    )
    parsed_document = bundle.to_parsed_document()

    recreated = ParserNormalizationBundle.from_parsed_document(parsed_document)

    assert recreated.document_id == bundle.document_id
    assert recreated.filename == bundle.filename
    assert recreated.markdown == bundle.markdown
    assert recreated.provenance.parser_id == "docling"


def test_native_result_normalizes_into_bundle_without_fabrication() -> None:
    adapter = DoclingParser()
    document_id = make_stable_document_id(
        source_sha256="c" * 64,
        parser_id="docling",
        parser_version="docling",
    )
    native_result = ParserNativeResult(
        document_id=document_id,
        parser_id="docling",
        parser_version="docling",
        filename="note.md",
        file_type="text/markdown",
        source_size_bytes=14,
        source_sha256="c" * 64,
        markdown="# 标题\n\n正文。",
        payload={"raw_source": "markdown"},
    )
    request = ParseRequest(
        filename="note.md",
        file_type="text/markdown",
        content=b"# \xe6\xa0\x87\xe9\xa2\x98\n\n\xe6\xad\xa3\xe6\x96\x87\xe3\x80\x82",
        parser_id=None,
        options={},
    )
    signals = DocumentSignals(extension=".md", size_bytes=len(request.content), has_text_layer=True)

    bundle = adapter.normalize_native_result(native_result, request, signals)

    assert bundle.document_id == document_id
    assert bundle.markdown == "# 标题\n\n正文。"
    assert [block.kind for block in bundle.blocks] == [
        BlockKind.HEADING,
        BlockKind.PARAGRAPH,
    ]
    assert bundle.native_artifacts == []
    assert bundle.capabilities["page_bbox"].state == EvidenceAvailability.UNAVAILABLE
    assert bundle.capabilities["native_artifacts"].state == EvidenceAvailability.UNAVAILABLE
    assert bundle.provenance.parameters == {}


def test_table_id_prefers_source_identifier() -> None:
    document_id = make_stable_document_id(
        source_sha256="a" * 64,
        parser_id="docling",
        parser_version="1.0",
    )
    block_id = make_stable_block_id(
        document_id=document_id,
        source_block_id="docling-table-1",
        order_index=3,
        kind="table",
        text="A|B",
    )

    assert make_stable_table_id(
        document_id=document_id,
        source_table_id="table-001",
        block_id=block_id,
    ) == "table-001"
    assert make_stable_table_id(
        document_id=document_id,
        source_table_id=None,
        block_id=block_id,
    ) != ""
