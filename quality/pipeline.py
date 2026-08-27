"""质量流水线：EvidenceContext → 规则 → 能力矩阵 → Gate → QualityPackage。

M1 覆盖：完整性规则 + 来源规则 + 能力矩阵 + Gate + 最小 canonical。
表格/标题/引用能力在本里程碑如实标注"规则未实现"且不阻塞（对应能力
在 M2/M3 落地后接入）。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import uuid4

from quality.contracts import (
    GateSummary,
    IssueSeverity,
    IssueStatus,
    PackageManifest,
    ParsedDocument,
    QualityIssue,
    QualityPackage,
    QualityReport,
    QualityState,
)

from quality.builders.canonical import QUALITY_PIPELINE_VERSION, build_canonical_document
from quality.config import QualityConfig
from quality.evidence.context import EvidenceContext
from quality.evidence.requirements import QualityEvidenceRequirements
from quality.gates.capabilities import CapabilityMatrixBuilder
from quality.gates.evaluator import GateEvaluator
from quality.ids import binding_id, block_id, is_stable_id, issue_id, relation_id, stable_id
from quality.models_internal import EvidenceRef, IssueDraft, RuleResult
from quality.packaging.hashing import (
    markdown_bytes,
    sha256_bytes,
    sha256_text,
    stable_json_bytes,
)
from quality.repairs.table_proposals import plan_table_html_repairs
from quality.repairs.workflow import REGISTERED_REPAIRS, RepairWorkflow
from quality.representations import RepresentationKind
from quality.rules.base import QualityRule
from quality.rules.completeness import (
    QL_CONT_001_BlocksExist,
    QL_CONT_002_OrderIndex,
    QL_CONT_003_KindContent,
)
from quality.rules.headings import (
    QL_HDG_001_HeadingFields,
    QL_HDG_004_BuildTree,
)
from quality.rules.provenance import (
    QL_PROV_001_SourceTraceable,
    QL_PROV_002_AnchorValid,
    QL_PROV_003_ArtifactsValid,
    QL_PROV_004_CapabilityReasons,
)
from quality.rules.references import (
    QL_REF_001_ReferenceIndex,
    QL_REF_004_BindCitations,
)
from quality.rules.tables import (
    QL_TBL_004_ColumnPath,
    QL_TBL_006_BuildBindings,
)
from quality.rules.cross_page import QL_TBL_007_CrossPageContinuation, QL_TBL_008_ColumnDrift

# 注册的规则集合（M1 完整性/来源 + M2 标题/引用 + M3 表格）
QUALITY_RULES: tuple[type[QualityRule], ...] = (
    QL_CONT_001_BlocksExist,
    QL_CONT_002_OrderIndex,
    QL_CONT_003_KindContent,
    QL_PROV_001_SourceTraceable,
    QL_PROV_002_AnchorValid,
    QL_PROV_003_ArtifactsValid,
    QL_PROV_004_CapabilityReasons,
    QL_HDG_001_HeadingFields,
    QL_HDG_004_BuildTree,
    QL_REF_001_ReferenceIndex,
    QL_REF_004_BindCitations,
    QL_TBL_004_ColumnPath,
    QL_TBL_006_BuildBindings,
    QL_TBL_007_CrossPageContinuation,
    QL_TBL_008_ColumnDrift,
)

# The quality-owned contract is generated from rule declarations once at import
# time.  It contains no parser IDs or parser implementation objects.
QUALITY_EVIDENCE_REQUIREMENTS = QualityEvidenceRequirements.from_rules(QUALITY_RULES)


def _document_key(parsed: ParsedDocument) -> str:
    return parsed.source_sha256 or str(parsed.document_id)


def _execute_rules(
    context: EvidenceContext,
    rules: tuple[type[QualityRule], ...],
    evidence_requirements: QualityEvidenceRequirements,
):
    """Execute rules after explicit evidence/capability negotiation."""
    issue_drafts: list[IssueDraft] = []
    observations = []
    relation_candidates = []
    binding_candidates = []
    repair_proposals = []
    evidence_negotiations = []
    for rule_type in rules:
        rule = rule_type()
        requirements = evidence_requirements.for_rule(rule.rule_id)
        negotiation = context.negotiate_rule(rule.rule_id, requirements)
        evidence_negotiations.append(negotiation)
        blocked_requirements = [
            check for check in negotiation.checks if check.blocked
        ]
        if blocked_requirements:
            reasons = "; ".join(
                f"{check.requirement.kind}: {check.reason or check.state.value}"
                for check in blocked_requirements
            )
            issue_drafts.append(
                IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="evidence_availability",
                    message=f"{rule.rule_id} 因所需证据不可用而跳过：{reasons}。",
                    evidence_refs=[
                        EvidenceRef(
                            object_type="capability",
                            object_id=check.requirement.kind,
                            field_path="state",
                        )
                        for check in blocked_requirements
                    ],
                )
            )
            continue
        result: RuleResult = rule.execute(context)
        issue_drafts.extend(
            replace(draft, rule_id=draft.rule_id or rule.rule_id)
            for draft in result.issues
        )
        observations.extend(result.capability_observations)
        relation_candidates.extend(result.relation_candidates)
        binding_candidates.extend(result.binding_candidates)
        repair_proposals.extend(result.repair_proposals)
    return (
        issue_drafts,
        observations,
        relation_candidates,
        binding_candidates,
        repair_proposals,
        tuple(evidence_negotiations),
    )


@dataclass(frozen=True)
class _RepairDocumentResult:
    """One internal working document built from exact-target repair results."""

    markdown: str
    blocks: tuple
    applied: tuple
    audit: tuple[dict[str, str], ...]
    proposal_count: int
    table_audit: tuple[dict[str, str], ...]


def _run_repair_workflow(
    parsed_document: ParsedDocument,
    context: EvidenceContext,
    *,
    document_key: str,
) -> _RepairDocumentResult:
    """Build the P5 working document from exact Markdown and table proposals."""
    inventory = context.representations
    document_descriptor = inventory.require(
        RepresentationKind.DOCUMENT_MARKDOWN,
        object_id=str(parsed_document.document_id),
        field_path="markdown",
    )
    block_descriptors = inventory.for_kind(RepresentationKind.BLOCK_MARKDOWN)
    if len(block_descriptors) != len(parsed_document.blocks):
        raise ValueError("representation inventory does not cover every block markdown")

    base_rules = tuple(
        rule_type
        for rule_type in REGISTERED_REPAIRS
        if rule_type.rule_id != "QL-RPR-003"
    )
    table_rules = tuple(
        rule_type
        for rule_type in REGISTERED_REPAIRS
        if rule_type.rule_id == "QL-RPR-003"
    )
    base_workflow = RepairWorkflow(rules=base_rules)
    table_workflow = RepairWorkflow(rules=table_rules)

    block_plans: list[tuple[object, object, tuple]] = []
    affected_block_ids_by_rule: dict[str, list[str]] = {}
    for block, descriptor in zip(parsed_document.blocks, block_descriptors):
        block_id_value = str(block.id)
        per_rule = {
            rule_type.rule_id: [block_id_value]
            for rule_type in base_workflow.rules
        }
        plan = base_workflow.plan(
            block.markdown,
            target=descriptor.target,
            affected_block_ids_by_rule=per_rule,
        )
        block_plans.append((block, descriptor, plan))
        for proposal in plan:
            affected_block_ids_by_rule.setdefault(proposal.rule_id, []).append(
                block_id_value
            )

    document_base = base_workflow.run(
        parsed_document.markdown,
        document_key=document_key,
        target=document_descriptor.target,
        affected_block_ids_by_rule=affected_block_ids_by_rule,
    )
    block_base_results = []
    for block, descriptor, plan in block_plans:
        result = base_workflow.execute_plan(
            block.markdown,
            proposals=plan,
            document_key=document_key,
        )
        block_base_results.append((block, descriptor, result))

    document_table_plan = plan_table_html_repairs(
        document_base.content,
        target=document_descriptor.target,
        inventory=inventory,
        tables=parsed_document.tables,
    )
    document_table = table_workflow.execute_plan(
        document_base.content,
        proposals=document_table_plan.proposals,
        document_key=document_key,
    )

    repaired_blocks = []
    block_table_results = []
    for block, descriptor, base_result in block_base_results:
        block_tables = [
            table
            for table in parsed_document.tables
            if str(table.block_id) == str(block.id)
        ]
        table_plan = plan_table_html_repairs(
            base_result.content,
            target=descriptor.target,
            inventory=inventory,
            tables=block_tables,
        )
        table_result = table_workflow.execute_plan(
            base_result.content,
            proposals=table_plan.proposals,
            document_key=document_key,
        )
        block_table_results.append((table_plan, table_result))
        repaired_blocks.append(
            block.model_copy(update={"markdown": table_result.content})
        )

    applied = tuple(
        [
            *document_base.applied,
            *document_table.applied,
            *(repair for _, _, result in block_base_results for repair in result.applied),
            *(repair for _, result in block_table_results for repair in result.applied),
        ]
    )
    audit = tuple(
        [
            *(entry.as_dict() for entry in document_base.audit),
            *(entry.as_dict() for entry in document_table.audit),
            *(entry.as_dict() for _, _, result in block_base_results for entry in result.audit),
            *(entry.as_dict() for _, result in block_table_results for entry in result.audit),
        ]
    )
    table_audit = tuple(
        [
            *document_table_plan.audit,
            *(entry for plan, _ in block_table_results for entry in plan.audit),
        ]
    )
    proposal_count = (
        len(document_base.proposals)
        + len(document_table.proposals)
        + sum(len(result.proposals) for _, _, result in block_base_results)
        + sum(len(result.proposals) for _, result in block_table_results)
    )
    return _RepairDocumentResult(
        markdown=document_table.content,
        blocks=tuple(repaired_blocks),
        applied=applied,
        audit=audit,
        proposal_count=proposal_count,
        table_audit=table_audit,
    )

_ISSUE_SEVERITY_RANK = {
    IssueSeverity.INFO: 0,
    IssueSeverity.WARNING: 1,
    IssueSeverity.CRITICAL: 2,
}


def _issue_dedup_key(draft: IssueDraft) -> tuple:
    """Return a business-level key, independent of rule wording/occurrence.

    Several rules observe the same root cause (notably reading order), and a
    citation marker can be repeated in explanatory text. The public report
    should show one actionable finding with merged evidence, not one card per
    rule invocation.
    """
    category = draft.category
    if category in {"reading_order_conflict", "heading_level_granularity_suspect"}:
        return (category,)
    if category == "citation_binding":
        missing = tuple(sorted(str(value) for value in draft.evidence.get("missing_labels", ())))
        return (category, missing)
    if category in {"cross_page_table", "column_drift"}:
        table_ids = tuple(sorted(str(value) for value in draft.evidence.get("table_ids", ())))
        return (category, table_ids)
    return (
        category,
        draft.message,
        tuple(sorted(str(value) for value in draft.affected_block_ids)),
    )


def _deduplicate_issue_drafts(drafts: list[IssueDraft]) -> list[IssueDraft]:
    merged: dict[tuple, IssueDraft] = {}
    counts: dict[tuple, int] = {}
    source_rules: dict[tuple, set[str]] = {}
    for draft in drafts:
        key = _issue_dedup_key(draft)
        previous = merged.get(key)
        if previous is None:
            merged[key] = draft
            counts[key] = 1
            source_rules[key] = {draft.rule_id}
            continue
        counts[key] += 1
        source_rules[key].add(draft.rule_id)
        severity = max((previous.severity, draft.severity), key=lambda value: _ISSUE_SEVERITY_RANK[value])
        affected = list(dict.fromkeys([*previous.affected_block_ids, *draft.affected_block_ids]))
        evidence_refs = list(previous.evidence_refs)
        ref_keys = {(ref.object_type, ref.object_id, ref.field_path, ref.value_sha256) for ref in evidence_refs}
        for ref in draft.evidence_refs:
            ref_key = (ref.object_type, ref.object_id, ref.field_path, ref.value_sha256)
            if ref_key not in ref_keys:
                evidence_refs.append(ref)
                ref_keys.add(ref_key)
        evidence = dict(previous.evidence)
        evidence["deduplicated_occurrences"] = counts[key]
        evidence["source_rule_ids"] = sorted(source_rules[key])
        merged[key] = IssueDraft(
            severity=severity,
            category=previous.category,
            message=previous.message,
            rule_id=previous.rule_id,
            affected_block_ids=affected,
            evidence_refs=evidence_refs,
            evidence=evidence,
        )
    return list(merged.values())


def _issue_evidence_key(
    message: str,
    evidence: dict,
    evidence_refs: list[dict],
) -> str:
    """Create an auditable stable key for one rule finding."""
    return sha256_bytes(
        stable_json_bytes(
            {
                "message": message,
                "evidence": evidence,
                "evidence_refs": evidence_refs,
            }
        )
    )


def _to_quality_issue(document_key: str, draft: IssueDraft) -> QualityIssue:
    evidence_refs = [
        {
            "object_type": ref.object_type,
            "object_id": ref.object_id,
            "field_path": ref.field_path,
            **({"value_sha256": ref.value_sha256} if ref.value_sha256 else {}),
        }
        for ref in draft.evidence_refs
    ]
    evidence_key = _issue_evidence_key(
        draft.message,
        draft.evidence,
        evidence_refs,
    )
    rule_id = draft.rule_id or "draft"
    return QualityIssue(
        issue_id=issue_id(
            document_key,
            rule_id,
            draft.affected_block_ids,
            evidence_key,
        ),
        severity=draft.severity,
        category=draft.category,
        status=IssueStatus.UNFIXED,
        message=draft.message,
        affected_block_ids=list(draft.affected_block_ids),
        evidence={
            **draft.evidence,
            "rule_id": rule_id,
            "stable_evidence_sha256": evidence_key,
            "evidence_refs": evidence_refs,
        },
    )


def _validate_stable_id_collection(label: str, values: list[str]) -> None:
    invalid = [value for value in values if not is_stable_id(value)]
    if invalid:
        raise ValueError(f"{label} contains non-UUIDv5 IDs: {invalid}")
    duplicate_count = len(values) - len(set(values))
    if duplicate_count:
        raise ValueError(f"{label} contains {duplicate_count} duplicate stable IDs")


def _validate_stable_output_ids(
    parsed_document: ParsedDocument,
    document_key: str,
    canonical,
    issues: list[QualityIssue],
    repairs,
) -> None:
    """Validate every generated public ID before exposing a QualityPackage.

    The check is deliberately post-build: it protects the public boundary from
    future rule or builder changes while retaining an escape hatch for focused
    internal experiments through ``QualityConfig(enforce_stable_ids=False)``.
    """
    block_ids = [block.block_id for block in canonical.blocks]
    _validate_stable_id_collection("canonical block IDs", block_ids)
    expected_block_ids = {
        block_id(
            document_key,
            block.source_block_id or str(block.id),
            block.order_index or 0,
            block_uuid=str(block.id),
        )
        for block in parsed_document.blocks
    }
    if set(block_ids) != expected_block_ids:
        raise ValueError("canonical block IDs do not match the ParsedDocument identity")

    relation_ids = [relation.relation_id for relation in canonical.relations]
    _validate_stable_id_collection("canonical relation IDs", relation_ids)
    for relation in canonical.relations:
        marker = relation.evidence.get("marker")
        offset = relation.evidence.get("marker_offset")
        if isinstance(marker, str) and isinstance(offset, int):
            expected = relation_id(
                document_key,
                relation.relation_type,
                relation.from_id,
                relation.to_id,
                f"{offset}:{marker}",
            )
            if relation.relation_id != expected:
                raise ValueError("canonical relation ID does not match its citation evidence")

    binding_ids = [binding.binding_id for binding in canonical.table_bindings]
    _validate_stable_id_collection("table binding IDs", binding_ids)
    for binding in canonical.table_bindings:
        value_cell = binding.evidence.get("value_cell")
        cell_id = value_cell.get("cell_id") if isinstance(value_cell, dict) else None
        prefix = f"{binding.table_id}:"
        if isinstance(cell_id, str) and cell_id.startswith(prefix):
            expected = binding_id(
                document_key,
                binding.table_id,
                cell_id.removeprefix(prefix),
                binding.row_key,
                binding.column_path,
            )
            if binding.binding_id != expected:
                raise ValueError("table binding ID does not match its cell evidence")

    issue_ids = [issue.issue_id for issue in issues]
    _validate_stable_id_collection("quality issue IDs", issue_ids)
    for issue in issues:
        rule_id = issue.evidence.get("rule_id")
        evidence_key = issue.evidence.get("stable_evidence_sha256")
        evidence_refs = issue.evidence.get("evidence_refs")
        if not isinstance(rule_id, str) or not isinstance(evidence_key, str) or not isinstance(evidence_refs, list):
            raise ValueError("quality issue is missing its stable ID evidence")
        source_evidence = {
            key: value
            for key, value in issue.evidence.items()
            if key not in {"rule_id", "stable_evidence_sha256", "evidence_refs"}
        }
        if evidence_key != _issue_evidence_key(issue.message, source_evidence, evidence_refs):
            raise ValueError("quality issue stable evidence digest does not match its content")
        expected = issue_id(
            document_key,
            rule_id,
            issue.affected_block_ids,
            evidence_key,
        )
        if issue.issue_id != expected:
            raise ValueError("quality issue ID does not match its stable input key")

    repair_ids = [repair.repair_id for repair in repairs]
    _validate_stable_id_collection("applied repair IDs", repair_ids)
    for repair in repairs:
        before = repair.evidence.get("before")
        target = repair.evidence.get("target")
        target_key = target.get("stable_key") if isinstance(target, dict) else None
        if isinstance(before, str):
            identity = (
                f"repair|{document_key}|{repair.rule_id}|{target_key}|{sha256_text(before)}"
                if isinstance(target_key, str)
                else f"repair|{document_key}|{repair.rule_id}|{sha256_text(before)}"
            )
            expected = stable_id(identity)
            if repair.repair_id != expected:
                raise ValueError("applied repair ID does not match its stable input key")


def run_pipeline(
    parsed_document: ParsedDocument,
    *,
    config: QualityConfig | None = None,
    rules: tuple[type[QualityRule], ...] = QUALITY_RULES,
) -> QualityPackage:
    """执行质量流水线，返回完整 QualityPackage（含内存哈希绑定）。"""
    config = config or QualityConfig()
    evidence_requirements = (
        QUALITY_EVIDENCE_REQUIREMENTS
        if rules == QUALITY_RULES
        else QualityEvidenceRequirements.from_rules(rules)
    )
    context = EvidenceContext(parsed_document)
    doc_key = _document_key(parsed_document)

    # 1. Build one repaired working document through the P4 workflow, then
    # rerun rules against that exact working state.
    repair_result = _run_repair_workflow(
        parsed_document,
        context,
        document_key=doc_key,
    )
    repaired_document = parsed_document.model_copy(
        update={
            "markdown": repair_result.markdown,
            "blocks": list(repair_result.blocks),
        }
    )
    context = EvidenceContext(repaired_document)
    (
        issue_drafts,
        observations,
        relation_candidates,
        binding_candidates,
        rule_repair_proposals,
        evidence_negotiations,
    ) = _execute_rules(context, rules, evidence_requirements)

    # 2. 业务问题聚合：规则仍独立运行，但公共报告按根因去重。
    issue_drafts = _deduplicate_issue_drafts(issue_drafts)

    # 3. 能力矩阵
    matrix_builder = CapabilityMatrixBuilder(config)
    verdicts = matrix_builder.build(observations, context)

    # 4. canonical document（含关系与表格绑定）
    canonical = build_canonical_document(
        context,
        relation_candidates=tuple(relation_candidates),
        binding_candidates=tuple(binding_candidates),
    )

    # 5. Gate 决策（M1 无 reparse 来源，无 recommendation）
    # 契约要求 reparse_required 必须带 recommendation；无合法建议时
    # evaluator 将 reparse 降级为 manual_review_required。
    evaluator = GateEvaluator(config.gate)
    decision = evaluator.decide(issue_drafts, verdicts)

    # 6. 组装 issues（规则来源 + 证据摘要参与稳定 ID）
    issues = [_to_quality_issue(doc_key, draft) for draft in issue_drafts]

    if config.enforce_stable_ids:
        _validate_stable_output_ids(
            repaired_document,
            doc_key,
            canonical,
            issues,
            repair_result.applied,
        )

    # 7. optimized markdown 已在规则重跑前生成；canonical/report 使用同一最终输入。
    optimized_markdown = repair_result.markdown
    optimized_sha = sha256_text(optimized_markdown)
    canonical_sha = sha256_bytes(stable_json_bytes(canonical))

    report = QualityReport(
        contract_version="1.0",
        document_id=parsed_document.document_id,
        state=decision.state,
        artifacts={
            "input_parsed_document.json": parsed_document.source_sha256
            or sha256_text(str(parsed_document.document_id)),
            "optimized.md": optimized_sha,
            "canonical_document.json": canonical_sha,
        },
        issues=issues,
        applied_repairs=list(repair_result.applied),
        capability_matrix=matrix_builder.to_public_assessments(verdicts),
        gate_summary=decision.summary,
        metrics={
            "quality_pipeline_version": QUALITY_PIPELINE_VERSION,
            "source_block_count": len(parsed_document.blocks),
            "canonical_block_count": len(canonical.blocks),
            "table_count": len(parsed_document.tables),
            "binding_count": len(canonical.table_bindings),
            "relation_count": len(canonical.relations),
            "repair_count": len(repair_result.applied),
            "repair_proposal_count": repair_result.proposal_count,
            "rule_repair_proposal_count": len(rule_repair_proposals),
            "repair_audit": list(repair_result.audit),
            "table_repair_audit": list(repair_result.table_audit),
            "evidence_requirements": evidence_requirements.as_dict(),
            "evidence_negotiation": [
                negotiation.as_dict() for negotiation in evidence_negotiations
            ],
            "issue_count": len(issues),
        },
        reparse_recommendation=None,
    )
    report_sha = sha256_bytes(stable_json_bytes(report))

    manifest = PackageManifest(
        artifacts={
            "optimized.md": optimized_sha,
            "canonical_document.json": canonical_sha,
            "quality_report.json": report_sha,
        }
    )

    return QualityPackage(
        schema_name="QualityPackage",
        schema_version="1.0",
        document_id=parsed_document.document_id,
        optimized_markdown=optimized_markdown,
        canonical_document=canonical,
        quality_report=report,
        package_manifest=manifest,
    )
