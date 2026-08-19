from uuid import uuid4

from document_parser.core.contracts import BlockKind, DocumentBlock, ParsedDocument, ParseConfidence, ParserProvenance, SourceAnchor
from document_parser.parsers.normalization import (
    FORMULA_PLACEHOLDER,
    normalize_formula_evidence,
    recover_missing_math_tokens,
)


def test_recover_missing_math_tokens_is_generic_and_strict():
    recovered, inserted = recover_missing_math_tokens(
        "threshold 0.25",
        "threshold ≤ 0.25",
    )

    assert recovered == "threshold ≤ 0.25"
    assert inserted == ["≤"]

    assert recover_missing_math_tokens("threshold 0.25", "threshold 0.30") == (None, [])


def test_docling_formula_marker_becomes_structured_placeholder():
    block = DocumentBlock(
        id=uuid4(),
        source_block_id="formula-1",
        order_index=0,
        kind=BlockKind.PARAGRAPH,
        text="<!-- formula-not-decoded -->",
        markdown="<!-- formula-not-decoded -->",
    )
    result = normalize_formula_evidence(
        [block],
        "before\n\n<!-- formula-not-decoded -->\n\nafter",
        parser_label="docling-local",
    )

    assert FORMULA_PLACEHOLDER in result.markdown
    assert result.blocks[0].markdown == FORMULA_PLACEHOLDER
    assert result.blocks[0].metadata["formula_status"] == "incomplete"
    assert result.incomplete_count == 1
