"""QualityConfig.enforce_stable_ids protects generated public identifiers."""

from __future__ import annotations

from pathlib import Path

import pytest

import quality.pipeline as pipeline
from document_parser.core.contracts import IssueSeverity, ParsedDocument
from quality import run_quality
from quality.config import QualityConfig
from quality.models_internal import IssueDraft
from quality.pipeline import _deduplicate_issue_drafts

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "quality"
    / "fixtures"
    / "parsed_documents"
    / "sdp-004-mineru.json"
)


def _document(sample: str = "sdp-004-mineru") -> ParsedDocument:
    path = FIXTURE.with_name(f"{sample}.json")
    return ParsedDocument.model_validate_json(path.read_text(encoding="utf-8"))


def _corrupt_builder(original_builder):
    def corrupt_builder(*args, **kwargs):
        canonical = original_builder(*args, **kwargs)
        corrupted = canonical.blocks[0].model_copy(update={"block_id": "not-a-stable-id"})
        return canonical.model_copy(update={"blocks": [corrupted, *canonical.blocks[1:]]})

    return corrupt_builder


def test_stable_id_validation_rejects_corrupt_canonical_block(monkeypatch) -> None:
    monkeypatch.setattr(
        pipeline,
        "build_canonical_document",
        _corrupt_builder(pipeline.build_canonical_document),
    )

    with pytest.raises(ValueError, match="canonical block IDs"):
        run_quality(_document(), config=QualityConfig(enforce_stable_ids=True))


def test_issue_ids_are_unique_for_multi_rule_cross_page_fixture() -> None:
    package = run_quality(_document("sdp-005-mineru"))
    issue_ids = [issue.issue_id for issue in package.quality_report.issues]

    assert issue_ids
    assert len(issue_ids) == len(set(issue_ids))
    assert all(issue.evidence["rule_id"] for issue in package.quality_report.issues)
    assert all(issue.evidence["stable_evidence_sha256"] for issue in package.quality_report.issues)


def test_issue_dedup_merges_shared_business_root_cause() -> None:
    drafts = [
        IssueDraft(
            severity=IssueSeverity.WARNING,
            category="reading_order_conflict",
            message="标题阅读顺序不确定。",
            rule_id="QL-HDG-004",
            affected_block_ids=["heading-a"],
        ),
        IssueDraft(
            severity=IssueSeverity.WARNING,
            category="reading_order_conflict",
            message="引用绑定顺序不确定。",
            rule_id="QL-REF-004",
            affected_block_ids=["citation-b"],
        ),
    ]
    merged = _deduplicate_issue_drafts(drafts)
    assert len(merged) == 1
    assert merged[0].affected_block_ids == ["heading-a", "citation-b"]
    assert merged[0].evidence["deduplicated_occurrences"] == 2
    assert merged[0].evidence["source_rule_ids"] == ["QL-HDG-004", "QL-REF-004"]


def test_stable_id_validation_can_be_disabled_for_focused_experiments(monkeypatch) -> None:
    monkeypatch.setattr(
        pipeline,
        "build_canonical_document",
        _corrupt_builder(pipeline.build_canonical_document),
    )

    package = run_quality(_document(), config=QualityConfig(enforce_stable_ids=False))

    assert package.canonical_document.blocks[0].block_id == "not-a-stable-id"
