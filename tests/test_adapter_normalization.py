import sys
import json
import zipfile
from pathlib import Path
from uuid import UUID


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.core.contracts import (  # noqa: E402
    BlockKind,
    DocumentBlock,
    DocumentSignals,
    EvidenceAvailability,
    ParseRequest,
    RoutingDecision,
    RoutingMode,
)
from document_parser.normalizers import (  # noqa: E402
    ParserNormalizationBundle,
    unavailable_capability,
)
from document_parser.parsers.base import BaseParserAdapter  # noqa: E402
from document_parser.parsers.docling import DoclingParser  # noqa: E402
from document_parser.parsers.mineru import MinerUParser  # noqa: E402
from document_parser.parsers.ocr import OcrParser  # noqa: E402


class MarkdownOnlyAdapter(BaseParserAdapter):
    PARSER_ID = "markdown-only"
    DISPLAY_NAME = "Markdown Only"
    NATIVE_FORMATS = {".md"}

    def normalize(self, request, signals):
        block = DocumentBlock(
            kind=BlockKind.PARAGRAPH,
            markdown=request.content.decode("utf-8"),
            text=request.content.decode("utf-8"),
        )
        return ParserNormalizationBundle.from_minimal_markdown(
            document_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            filename=request.filename,
            file_type=request.file_type,
            markdown=request.content.decode("utf-8"),
            parser_id=self.PARSER_ID,
            parser_version="1.0",
            source_size_bytes=len(request.content),
            routing_decision=RoutingDecision(
                mode=RoutingMode.AUTO,
                selected_parser_id=self.PARSER_ID,
                reason="markdown only",
                signals=signals,
            ),
            blocks=[block],
            capabilities={
                "table_cells": unavailable_capability("没有表格 JSON", granularity="table"),
                "ocr_confidence": unavailable_capability("未执行 OCR"),
            },
        )


def test_adapter_parse_can_return_markdown_only_bundle() -> None:
    adapter = MarkdownOnlyAdapter()
    request = ParseRequest(
        filename="sample.md",
        file_type="text/markdown",
        content=b"# Title\n\nBody.",
        parser_id=None,
        options={},
    )
    signals = DocumentSignals(extension=".md", size_bytes=len(request.content), has_text_layer=True)

    parsed = adapter.parse(request, signals)

    assert parsed.markdown.startswith("# Title")
    assert parsed.tables == []
    assert parsed.assets == []
    assert parsed.ocr_spans == []
    assert parsed.capabilities["table_cells"].state.value == "unavailable"
    assert parsed.capabilities["ocr_confidence"].reason == "未执行 OCR"


def test_unimplemented_adapters_return_valid_missing_evidence_bundle() -> None:
    request = ParseRequest(
        filename="notes.md",
        file_type="text/markdown",
        content=b"# Title\n\nBody.",
        parser_id=None,
        options={"language": "en"},
    )
    signals = DocumentSignals(extension=".md", size_bytes=len(request.content), has_text_layer=True)

    for adapter in (DoclingParser(), MinerUParser(), OcrParser()):
        parsed = adapter.parse(request, signals)

        assert parsed.filename == "notes.md"
        assert parsed.source_sha256 is not None
        assert parsed.markdown == "# Title\n\nBody."
        assert [block.kind for block in parsed.blocks] == [
            BlockKind.HEADING,
            BlockKind.PARAGRAPH,
        ]
        assert parsed.tables == []
        assert parsed.assets == []
        assert parsed.ocr_spans == []
        assert parsed.provenance.parser_id == adapter.PARSER_ID
        assert parsed.provenance.parameters["language"] == "en"
        assert parsed.routing_decision is not None
        assert parsed.routing_decision.selected_parser_id == adapter.PARSER_ID
        assert parsed.capabilities["text_content"].state == EvidenceAvailability.AVAILABLE
        assert parsed.capabilities["table_cells"].state == EvidenceAvailability.UNAVAILABLE
        assert parsed.capabilities["table_cells"].reason
        assert parsed.capabilities["page_bbox"].state == EvidenceAvailability.UNAVAILABLE
        assert parsed.capabilities["ocr_confidence"].state == EvidenceAvailability.UNAVAILABLE
        assert parsed.warnings


def test_unimplemented_adapter_does_not_fabricate_binary_outputs() -> None:
    adapter = DoclingParser()
    request = ParseRequest(
        filename="paper.pdf",
        file_type="application/pdf",
        content=b"%PDF-1.7\nnot actually parsed",
        parser_id="docling",
        options={},
    )
    signals = DocumentSignals(extension=".pdf", size_bytes=len(request.content), has_text_layer=None)

    first = adapter.parse(request, signals)
    second = adapter.parse(request, signals)

    assert first.document_id == second.document_id
    assert first.markdown == ""
    assert first.blocks == []
    assert first.tables == []
    assert first.assets == []
    assert first.ocr_spans == []
    assert first.confidence.overall == 0.0
    assert first.routing_decision is not None
    assert first.routing_decision.mode == RoutingMode.MANUAL
    assert first.routing_decision.allow_automatic_fallback is False
    assert first.capabilities["text_content"].state == EvidenceAvailability.UNAVAILABLE
    assert first.capabilities["native_artifacts"].reason


def test_adapter_consumes_real_native_sidecars_without_fabricating_missing_fields() -> None:
    adapter = MinerUParser()
    request = ParseRequest(
        filename="paper.pdf",
        file_type="application/pdf",
        content=b"%PDF-1.7\nfixture",
        parser_id="mineru",
        options={
            "native_markdown": "# Native Title\n\nBody",
            "native_payload": {
                "blocks": [
                    {
                        "id": "native-title",
                        "type": "title",
                        "text": "Native Title",
                        "page_number": 1,
                        "bbox": [10, 20, 100, 40],
                    }
                ],
                "tables": [
                    {
                        "id": "table-001",
                        "html": "<table><tr><td>A</td></tr></table>",
                        "cells": [
                            {
                                "text": "A",
                                "row": 0,
                                "col": 0,
                                "column_header": True,
                            }
                        ],
                    }
                ],
                "ocr_spans": [
                    {
                        "level": "line",
                        "text": "OCR line",
                        "bbox": [1, 2, 3, 4],
                        "confidence": 0.91,
                        "page_number": 1,
                    }
                ],
            },
            "native_files": {"debug.log": "ok"},
        },
    )
    signals = DocumentSignals(extension=".pdf", size_bytes=len(request.content), has_text_layer=True)

    bundle = adapter.normalize(request, signals)
    parsed = bundle.to_parsed_document()

    assert parsed.blocks[0].source_block_id == "native-title"
    assert parsed.blocks[0].anchor.bbox == (10.0, 20.0, 100.0, 40.0)
    assert parsed.tables[0].table_id == "table-001"
    assert parsed.tables[0].cells[0].text == "A"
    assert parsed.ocr_spans[0].confidence == 0.91
    assert parsed.capabilities["page_bbox"].state == EvidenceAvailability.AVAILABLE
    assert parsed.capabilities["table_cells"].state == EvidenceAvailability.PARTIAL
    assert parsed.capabilities["table_cells"].reason
    assert parsed.capabilities["ocr_confidence"].state == EvidenceAvailability.AVAILABLE
    assert parsed.capabilities["native_artifacts"].state == EvidenceAvailability.AVAILABLE
    assert "native/result.json" in bundle.native_files
    assert "native/debug.log" in bundle.native_files


def test_mineru_adapter_consumes_native_output_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "mineru-output"
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True)
    (output_dir / "full.md").write_text(
        "# MinerU Title\n\n<table><tr><th>A</th><td>B</td></tr></table>",
        encoding="utf-8",
    )
    (image_dir / "table.png").write_bytes(b"fake-png-bytes")
    (output_dir / "content_list.json").write_text(
        json.dumps(
            [
                {
                    "type": "title",
                    "text": "MinerU Title",
                    "text_level": 1,
                    "page_idx": 0,
                    "bbox": [10, 20, 200, 40],
                },
                {
                    "type": "table",
                    "table_body": "<table><tr><th>A</th><td>B</td></tr></table>",
                    "table_caption": ["Demo table"],
                    "table_img_path": "images/table.png",
                    "page_idx": 0,
                    "bbox": [20, 60, 260, 120],
                },
            ]
        ),
        encoding="utf-8",
    )
    adapter = MinerUParser()
    request = ParseRequest(
        filename="paper.pdf",
        file_type="application/pdf",
        content=b"%PDF-1.7\nfixture",
        parser_id="mineru",
        options={"native_output_dir": str(output_dir)},
    )
    signals = DocumentSignals(extension=".pdf", size_bytes=len(request.content), has_text_layer=True)

    bundle = adapter.normalize(request, signals)
    parsed = bundle.to_parsed_document()

    assert parsed.markdown.startswith("# MinerU Title")
    assert parsed.blocks[0].source_block_id == "mineru-0000"
    assert parsed.blocks[0].anchor.page_number == 1
    assert parsed.tables[0].caption == "Demo table"
    assert [cell.text for cell in parsed.tables[0].cells] == ["A", "B"]
    assert parsed.capabilities["table_cells"].state == EvidenceAvailability.PARTIAL
    assert parsed.assets[0].path == "mineru/images/table.png"
    assert "native/content_list.json" in bundle.native_files
    assert "native/mineru_result.json" in bundle.native_files


def test_mineru_adapter_uses_cloud_task_output(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MINERU_API_TOKEN", "test-token")

    adapter = MinerUParser()
    request = ParseRequest(
        filename="paper.pdf",
        file_type="application/pdf",
        content=b"%PDF-1.7\nfixture",
        parser_id="mineru",
        options={"api_mode": "precise"},
    )
    signals = DocumentSignals(extension=".pdf", size_bytes=len(request.content), has_text_layer=True)

    def fake_submit(*, base_url, source_path, form_data, headers, httpx):
        assert base_url == "https://mineru.net/api/v4"
        assert source_path.exists()
        assert form_data["backend"] == "pipeline"
        assert headers["Authorization"] == "Bearer test-token"
        return {
            "task_id": "task-1",
            "status_url": "https://mineru.example/tasks/task-1",
            "result_url": "https://mineru.example/tasks/task-1/result",
        }

    def fake_wait(*, httpx, task_info, headers, timeout_seconds):
        assert task_info["task_id"] == "task-1"
        assert headers["Authorization"] == "Bearer test-token"
        assert timeout_seconds > 0

    def fake_download(*, httpx, task_info, headers, timeout_seconds):
        assert task_info["task_id"] == "task-1"
        assert headers["Authorization"] == "Bearer test-token"
        zip_path = tmp_path / "mineru-cloud-result.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(
                "content_list.json",
                json.dumps(
                    [
                        {
                            "id": "cloud-title",
                            "type": "title",
                            "text": "Cloud Title",
                            "page_idx": 0,
                            "bbox": [10, 20, 200, 40],
                        },
                        {
                            "id": "cloud-table",
                            "type": "table",
                            "table_body": "<table><tr><th>A</th><td>B</td></tr></table>",
                            "table_caption": ["Cloud table"],
                            "table_img_path": "images/table.png",
                            "page_idx": 0,
                            "bbox": [20, 60, 260, 120],
                        },
                    ]
                ),
            )
            archive.writestr("full.md", "# Cloud Title\n\nCloud body.")
            archive.writestr("images/table.png", b"fake-png-bytes")
        return zip_path

    monkeypatch.setattr(adapter, "_submit_mineru_task", fake_submit)
    monkeypatch.setattr(adapter, "_wait_for_mineru_task", fake_wait)
    monkeypatch.setattr(adapter, "_download_mineru_result", fake_download)

    bundle = adapter.normalize(request, signals)
    parsed = bundle.to_parsed_document()

    assert parsed.markdown.startswith("# Cloud Title")
    assert parsed.blocks[0].source_block_id == "cloud-title"
    assert parsed.tables[0].caption == "Cloud table"
    assert parsed.assets[0].path == "mineru/images/table.png"
    assert "mineru_api_token" not in parsed.provenance.parameters
    assert "mineru_api_token" not in parsed.routing_decision.parser_options
