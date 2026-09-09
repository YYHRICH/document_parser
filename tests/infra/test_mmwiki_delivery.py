import hashlib
import sys
from pathlib import Path
from uuid import uuid4

from document_parser.domain.model.contracts import (
    AssetKind,
    BlockKind,
    DocumentAsset,
    DocumentBlock,
    ParseConfidence,
    ParsedDocument,
    ParsedTable,
    ParserProvenance,
    SourceAnchor,
    TableCell,
)
from document_parser.infra.delivery import MmwikiLifecycleDeliveryAdapter, MmwikiPackageAdapter


def _document() -> ParsedDocument:
    table_block = DocumentBlock(
        id=uuid4(),
        source_block_id="item-table-1",
        order_index=0,
        kind=BlockKind.TABLE,
        text="季度 销售额",
        markdown="|季度|销售额|\n|---|---|\n|第一季度|120|",
        anchor=SourceAnchor(
            page_number=1,
            bbox=(100, 200, 800, 700),
            coordinate_system="normalized_1000",
            origin="top_left",
        ),
    )
    image_block = DocumentBlock(
        id=uuid4(),
        source_block_id="item-image-1",
        order_index=1,
        kind=BlockKind.IMAGE,
        markdown="![图](images/a.png)",
        anchor=SourceAnchor(page_number=2),
        metadata={"visual_type": "chart"},
    )
    content = b"image"
    return ParsedDocument(
        filename="季度 报告.pdf",
        file_type="application/pdf",
        source_sha256="1" * 64,
        markdown=f"{table_block.markdown}\n\n{image_block.markdown}",
        blocks=[table_block, image_block],
        assets=[
            DocumentAsset(
                asset_id="asset-a",
                path="images/a.png",
                kind=AssetKind.IMAGE,
                file_type="image/png",
                content=content,
                sha256=hashlib.sha256(content).hexdigest(),
                referenced_by_block_ids=[str(image_block.id)],
            )
        ],
        tables=[
            ParsedTable(
                table_id="table-1",
                block_id=table_block.id,
                html='<table><tr><td colspan="2">季度</td></tr></table>',
                num_rows=2,
                num_cols=2,
                cells=[
                    TableCell(text="季度", start_row=0, start_col=0, col_span=2),
                    TableCell(text="第一季度", start_row=1, start_col=0),
                    TableCell(text="120", start_row=1, start_col=1),
                ],
            )
        ],
        confidence=ParseConfidence(),
        provenance=ParserProvenance(parser_id="mineru", version="1.0"),
    )


def test_parsed_document_is_accepted_by_real_mmwiki_loader(tmp_path: Path):
    target = tmp_path / "package"
    result = MmwikiPackageAdapter().publish(_document(), target)
    assert result["manifest"]["parser"]["source_schema"] == "ParsedDocument"

    downstream = Path(__file__).resolve().parents[3] / "multimodal-llm-wiki"
    if not downstream.is_dir():
        return
    sys.path.insert(0, str(downstream))
    try:
        from mmwiki.contracts import load_package

        package = load_package(target)
    finally:
        sys.path.remove(str(downstream))

    assert package.source_filename == "季度 报告.pdf"
    assert package.items[0].table == {
        "rows": [["季度", ""], ["第一季度", "120"]],
        "html": '<table><tr><td colspan="2">季度</td></tr></table>',
    }
    assert package.items[1].asset_ids == ["asset-a"]
    assert package.items[0].bbox["coordinate_system"] == "normalized_1000"


def test_lifecycle_delivery_publishes_relocates_and_withdraws(tmp_path: Path):
    adapter = MmwikiLifecycleDeliveryAdapter(tmp_path / "mmwiki")
    result = adapter.publish(
        source_id="src_example1", parse_id="parse-1", document=_document()
    )
    package_manifest = Path(result["package_path"]) / "manifest.json"
    assert package_manifest.is_file()
    assert adapter.status()["ready_count"] == 1

    adapter.relocate("src_example1", filename="新季度报告.pdf")
    payload = __import__("json").loads(package_manifest.read_text(encoding="utf-8"))
    assert payload["document"]["source"]["filename"] == "新季度报告.pdf"

    adapter.withdraw("src_example1")
    assert adapter.status()["withdrawn_count"] == 1
