import json
from pathlib import Path

import pytest

from document_parser import QualityPackage, WikiHandoff
from quality import build_wiki_handoff, write_wiki_handoff


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "contracts" / "quality_package.json"


def _package() -> QualityPackage:
    return QualityPackage.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))


def test_wiki_handoff_projects_final_quality_package_with_citations():
    package = _package()

    handoff = build_wiki_handoff(package)

    assert handoff.document_id == package.document_id
    assert handoff.quality_state == package.quality_report.state
    assert handoff.optimized_markdown == package.optimized_markdown
    assert len(handoff.chunks) == len(package.canonical_document.blocks)
    assert len(handoff.citations) >= len(handoff.chunks)
    assert all(
        set(chunk.citation_ids) <= {citation.citation_id for citation in handoff.citations}
        for chunk in handoff.chunks
    )
    assert any(citation.table_id for citation in handoff.citations)


def test_wiki_handoff_writer_emits_replayable_files(tmp_path):
    handoff = build_wiki_handoff(_package())

    output_dir = write_wiki_handoff(handoff, tmp_path / "wiki")

    restored = WikiHandoff.model_validate_json(
        (output_dir / "wiki_document.json").read_text(encoding="utf-8")
    )
    assert restored == handoff
    assert json.loads((output_dir / "wiki_chunks.json").read_text(encoding="utf-8"))
    assert json.loads((output_dir / "wiki_citations.json").read_text(encoding="utf-8"))
    with pytest.raises(FileExistsError):
        write_wiki_handoff(handoff, output_dir)
