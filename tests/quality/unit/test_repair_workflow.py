"""P4 tests for proposal, policy, exact executor, and verifier."""

from __future__ import annotations

from pathlib import Path

from document_parser.core.contracts import ParsedDocument

from quality import run_quality
from quality.models_internal import RepairProposal
from quality.packaging.hashing import sha256_text
from quality.repairs.executor import RepairExecutionStatus
from quality.repairs.policy import RepairPolicy, RepairPolicyAction
from quality.repairs.whitelist import QL_RPR_001_TrailingWhitespace
from quality.repairs.workflow import RepairWorkflow
from quality.representations.models import RepresentationTarget


FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "quality"
    / "fixtures"
    / "parsed_documents"
    / "sdp-004-mineru.json"
)


def _target() -> RepresentationTarget:
    return RepresentationTarget(
        object_type="document",
        object_id="workflow-test-document",
        field_path="markdown",
    )


def test_workflow_records_target_precondition_policy_and_verification():
    workflow = RepairWorkflow(rules=(QL_RPR_001_TrailingWhitespace,))

    result = workflow.run("text \n", document_key="workflow-doc", target=_target())

    assert result.content == "text\n"
    assert len(result.proposals) == len(result.applied) == 1
    repair = result.applied[0]
    assert repair.evidence["target"]["stable_key"] == _target().stable_key
    assert repair.evidence["precondition"]["content_sha256"] == sha256_text("text \n")
    assert repair.evidence["policy"]["action"] == "auto_safe"
    assert repair.evidence["verification"]["status"] == "verified"


def test_executor_rejects_a_stale_content_hash_without_mutating():
    workflow = RepairWorkflow(rules=(QL_RPR_001_TrailingWhitespace,))
    proposals = workflow.plan("text \n", target=_target())

    result = workflow.execute_plan(
        "different\n",
        proposals=proposals,
        document_key="workflow-doc",
    )

    assert result.content == "different\n"
    assert result.applied == ()
    assert result.executions[0].status == RepairExecutionStatus.REJECTED_PRECONDITION
    assert result.audit[0].verification_status == "rejected"


def test_review_required_proposal_never_runs_automatically():
    source = "text \n"
    proposal = RepairProposal(
        rule_id="QL-RPR-001",
        description="manual review test",
        target=_target(),
        expected_content_sha256=sha256_text(source),
        expected_after_sha256=sha256_text("text\n"),
        safety="review_required",
    )
    workflow = RepairWorkflow(rules=(QL_RPR_001_TrailingWhitespace,))

    decision = RepairPolicy().decide(proposal)
    result = workflow.execute_plan(source, proposals=(proposal,), document_key="workflow-doc")

    assert decision.action == RepairPolicyAction.REVIEW_REQUIRED
    assert result.content == source
    assert result.applied == ()
    assert result.executions[0].status == RepairExecutionStatus.REJECTED_POLICY


def test_pipeline_exposes_only_verified_hash_guarded_applied_repairs():
    document = ParsedDocument.model_validate_json(FIXTURE.read_text(encoding="utf-8"))

    package = run_quality(document)

    assert package.quality_report.applied_repairs
    for repair in package.quality_report.applied_repairs:
        assert repair.evidence["target"]["stable_key"]
        assert len(repair.evidence["precondition"]["content_sha256"]) == 64
        assert repair.evidence["verification"]["status"] == "verified"
    assert package.quality_report.metrics["repair_proposal_count"] >= len(
        package.quality_report.applied_repairs
    )
    assert package.quality_report.metrics["repair_audit"]


def test_pipeline_table_repair_uses_resolved_table_evidence_and_skips_spans():
    fixture = FIXTURE.with_name("sdp-001-mineru.json")
    document = ParsedDocument.model_validate_json(fixture.read_text(encoding="utf-8"))

    package = run_quality(document)
    table_repairs = [
        repair
        for repair in package.quality_report.applied_repairs
        if repair.rule_id == "QL-RPR-003"
    ]

    assert table_repairs
    table_ids = {repair.evidence["parameters"]["table_id"] for repair in table_repairs}
    assert table_ids == {"table-001", "table-002", "table-004"}
    for repair in table_repairs:
        parameters = repair.evidence["parameters"]
        source_target = parameters["source_representation_target"]
        assert source_target["object_type"] == "table"
        assert source_target["field_path"] == "html"
        assert repair.evidence["target"]["field_path"] == "markdown"
        assert repair.evidence["verification"]["status"] == "verified"
    assert any(
        entry["table_id"] == "table-003" and entry["status"] == "not_proposed"
        for entry in package.quality_report.metrics["table_repair_audit"]
    )
