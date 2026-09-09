"""质量流水线：EvidenceContext → 规则 → 能力矩阵 → Gate → QualityPackage。

当前规则覆盖完整性、来源、标题、引用、表格网格、字段绑定、视图语义、
跨页诊断与确定性修复；解析器私有结构不会进入领域规则。
"""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from document_parser.domain.model.contracts import (
    GateSummary,
    IssueSeverity,
    IssueStatus,
    ParsedDocument,
    QualityIssue,
    QualityPackage,
    QualityReport,
    QualityState,
)

from .builders.canonical import QUALITY_PIPELINE_VERSION, build_canonical_document
from .config import QualityConfig
from .evidence.context import EvidenceContext
from .gates.capabilities import CapabilityMatrixBuilder
from .gates.evaluator import GateEvaluator
from .ids import issue_id
from .models_internal import EvidenceRef, IssueDraft, RuleResult
from .repairs.registry import (
    WHITELIST_REPAIRS,
    apply_document_repairs,
)
from .table_storage import uses_external_table_index
from .rules.base import QualityRule
from .rules.completeness import (
    QL_CONT_001_BlocksExist,
    QL_CONT_002_OrderIndex,
    QL_CONT_003_KindContent,
)
from .rules.headings import (
    QL_HDG_001_HeadingFields,
    QL_HDG_004_BuildTree,
)
from .rules.provenance import (
    QL_PROV_001_SourceTraceable,
    QL_PROV_002_AnchorValid,
    QL_PROV_003_ArtifactsValid,
    QL_PROV_004_CapabilityReasons,
)
from .rules.references import (
    QL_REF_001_ReferenceIndex,
    QL_REF_004_BindCitations,
)
from .rules.tables import (
    QL_TBL_004_ColumnPath,
    QL_TBL_006_BuildBindings,
    QL_TBL_010_TableEvidenceIntegrity,
)
from .rules.cross_page import QL_TBL_007_CrossPageContinuation, QL_TBL_008_ColumnDrift
from .rules.safety import (
    QL_ASSET_001_DataUriRemains,
    QL_ASSET_002_LocalReferenceIntegrity,
    QL_CONT_004_EmptyNormalizedContent,
    QL_FMT_001_MojibakeDetected,
    QL_TBL_003_EmptyTableStructure,
    QL_TBL_009_HtmlTableRepresentation,
)

# 注册的完整性、来源、标题、引用和表格规则集合。
QUALITY_RULES: tuple[type[QualityRule], ...] = (
    QL_CONT_001_BlocksExist,
    QL_CONT_002_OrderIndex,
    QL_CONT_003_KindContent,
    QL_CONT_004_EmptyNormalizedContent,
    QL_FMT_001_MojibakeDetected,
    QL_ASSET_001_DataUriRemains,
    QL_ASSET_002_LocalReferenceIntegrity,
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
    QL_TBL_010_TableEvidenceIntegrity,
    QL_TBL_003_EmptyTableStructure,
    QL_TBL_009_HtmlTableRepresentation,
    QL_TBL_007_CrossPageContinuation,
    QL_TBL_008_ColumnDrift,
)


def _document_key(parsed: ParsedDocument) -> str:
    return parsed.source_sha256 or str(parsed.document_id)


def _execute_rules(context: EvidenceContext, rules: tuple[type[QualityRule], ...]):
    """在给定最终 EvidenceContext 上执行规则并统一处理证据阻断。"""
    issue_drafts: list[IssueDraft] = []
    observations = []
    relation_candidates = []
    binding_candidates = []
    for rule_type in rules:
        rule = rule_type()
        blocked_requirements = [
            check
            for check in context.check_requirements(rule.required_evidence)
            if check.blocked
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
                    rule_id=rule.rule_id,
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
    return issue_drafts, observations, relation_candidates, binding_candidates


def _issue_fingerprint(draft: IssueDraft) -> tuple[str, str, str]:
    """用于修复前后对账的稳定问题指纹。"""

    return draft.rule_id, draft.category, draft.message


def _deduplicate_issue_drafts(drafts: list[IssueDraft]) -> list[IssueDraft]:
    """同一规则事实只交付一次，避免多个表格分析入口重复计数。"""

    unique: dict[tuple, IssueDraft] = {}
    for draft in drafts:
        key = (
            draft.rule_id,
            draft.category,
            draft.status,
            draft.severity,
            draft.message,
            tuple(sorted(draft.affected_block_ids)),
        )
        unique.setdefault(key, draft)
    return list(unique.values())


def _repair_block_ids(parsed_document: ParsedDocument) -> dict[str, list[str]]:
    """确定哪些真实 block 会被某个白名单修复改变。"""
    affected: dict[str, list[str]] = {}
    for rule_type in WHITELIST_REPAIRS:
        rule = rule_type()
        affected[rule.rule_id] = [
            str(block.id)
            for block in parsed_document.blocks
            if rule.apply(block.markdown).applied
        ]
    return affected


def _apply_repairs_to_blocks(parsed_document: ParsedDocument) -> list:
    """将同一白名单变换投影到 block markdown，供 canonical/重跑规则使用。"""
    repaired = []
    for block in parsed_document.blocks:
        markdown = block.markdown
        for rule_type in WHITELIST_REPAIRS:
            markdown = rule_type().apply(markdown).after
        repaired.append(block.model_copy(update={"markdown": markdown}))
    return repaired


def run_pipeline(
    parsed_document: ParsedDocument,
    *,
    config: QualityConfig | None = None,
    rules: tuple[type[QualityRule], ...] = QUALITY_RULES,
) -> QualityPackage:
    """执行质量流水线，返回优化 Markdown 和结构化质量结果。"""
    config = config or QualityConfig()
    context = EvidenceContext(parsed_document)
    doc_key = _document_key(parsed_document)

    # 1. 先诊断原始证据，再应用结构化安全修复。
    initial_context = EvidenceContext(parsed_document)
    initial_issue_drafts, _, _, _ = _execute_rules(initial_context, rules)
    initial_issue_drafts = _deduplicate_issue_drafts(initial_issue_drafts)
    repair_result = apply_document_repairs(
        parsed_document,
        document_key=doc_key,
        affected_block_ids_by_rule=_repair_block_ids(parsed_document),
    )
    repaired_document = repair_result.document
    context = EvidenceContext(repaired_document)
    issue_drafts, observations, relation_candidates, binding_candidates = _execute_rules(
        context, rules
    )
    for rejected in repair_result.rejected:
        issue_drafts.append(
            IssueDraft(
                severity=IssueSeverity.WARNING,
                category="repair_rejected",
                rule_id=str(rejected.get("rule_id") or "QL-RPR-003"),
                message=(
                    f"{rejected.get('rule_id', 'repair')} 未应用于 "
                    f"{rejected.get('table_id', 'document')}: {rejected.get('reason', '未知原因')}"
                ),
                evidence={"rejected_repair": rejected},
            )
        )
    issue_drafts = _deduplicate_issue_drafts(issue_drafts)

    # 2. 能力矩阵
    matrix_builder = CapabilityMatrixBuilder(config)
    verdicts = matrix_builder.build(observations, context)

    # 3. canonical document（含关系与表格绑定）
    canonical = build_canonical_document(
        context,
        relation_candidates=tuple(relation_candidates),
        binding_candidates=tuple(binding_candidates),
    )

    # 4. Gate 决策；无合法重解析建议时不伪造 recommendation。
    # 契约要求 reparse_required 必须带 recommendation；无合法建议时
    # evaluator 将结果安全降级为 rejected。
    evaluator = GateEvaluator(config.gate)
    decision = evaluator.decide(issue_drafts, verdicts)

    # 5. 组装最终未解决 issues，并保留修复前后消失的 resolved issues。
    final_fingerprints = {_issue_fingerprint(draft) for draft in issue_drafts}
    issues = [
        QualityIssue(
            issue_id=issue_id(
                doc_key,
                draft.rule_id,
                draft.affected_block_ids,
                f"{draft.status.value}:{draft.message[:32]}",
            ),
            rule_id=draft.rule_id,
            severity=draft.severity,
            category=draft.category,
            status=draft.status,
            message=draft.message,
            affected_block_ids=list(draft.affected_block_ids),
            evidence={
                **draft.evidence,
                "evidence_refs": [
                    {
                        "object_type": ref.object_type,
                        "object_id": ref.object_id,
                        "field_path": ref.field_path,
                    }
                    for ref in draft.evidence_refs
                ],
            },
        )
        for draft in issue_drafts
    ]
    resolved_issues = [
        QualityIssue(
            issue_id=issue_id(
                doc_key,
                draft.rule_id,
                draft.affected_block_ids,
                f"repaired:{draft.message[:32]}",
            ),
            rule_id=draft.rule_id,
            severity=draft.severity,
            category=draft.category,
            status=IssueStatus.REPAIRED,
            message=f"已通过安全修复消除：{draft.message}",
            affected_block_ids=list(draft.affected_block_ids),
            evidence={
                **draft.evidence,
                "resolved_by_repair_ids": [repair.repair_id for repair in repair_result.applied],
            },
        )
        for draft in initial_issue_drafts
        if _issue_fingerprint(draft) not in final_fingerprints
    ]

    # 6. optimized markdown 已在规则重跑前生成；canonical/report 使用同一最终输入。
    optimized_markdown = repaired_document.markdown
    report = QualityReport(
        contract_version="1.0",
        document_id=parsed_document.document_id,
        state=decision.state,
        issues=issues,
        resolved_issues=resolved_issues,
        applied_repairs=list(repair_result.applied),
        rejected_repairs=list(repair_result.rejected),
        capability_matrix=matrix_builder.to_public_assessments(verdicts),
        gate_summary=decision.summary,
        metrics={
            "quality_pipeline_version": QUALITY_PIPELINE_VERSION,
            "source_block_count": len(parsed_document.blocks),
            "canonical_block_count": len(canonical.blocks),
            "table_count": len(parsed_document.tables),
            "canonical_table_count": len(canonical.tables),
            "table_cell_count": sum(len(table.cells) for table in parsed_document.tables),
            "merged_cell_anchor_count": sum(
                1
                for table in parsed_document.tables
                for cell in table.cells
                if cell.row_span > 1 or cell.col_span > 1
            ),
            "table_with_explicit_grid_count": sum(
                1 for table in parsed_document.tables if table.grid
            ),
            "table_with_known_view_scope_count": sum(
                1
                for table in parsed_document.tables
                if table.view_scope.value != "unknown"
            ),
            "visible_rows_table_count": sum(
                1
                for table in parsed_document.tables
                if table.view_scope.value == "visible_rows"
            ),
            "nested_table_count": sum(
                1 for table in parsed_document.tables if table.parent_table_id is not None
            ),
            "binding_count": len(canonical.table_bindings),
            "indexed_table_count": sum(
                uses_external_table_index(table) for table in parsed_document.tables
            ),
            "binding_storage": (
                "sqlite"
                if any(
                    uses_external_table_index(table)
                    for table in parsed_document.tables
                )
                else "inline_json"
            ),
            "relation_count": len(canonical.relations),
            "repair_count": len(repair_result.applied),
            "issue_count": len(issues),
            "initial_issue_count": len(initial_issue_drafts),
            "unfixed_issue_count": sum(
                issue.status == IssueStatus.UNFIXED for issue in issues
            ),
            "manual_review_required_issue_count": sum(
                issue.status == IssueStatus.MANUAL_REVIEW_REQUIRED for issue in issues
            ),
            "reparse_required_issue_count": sum(
                issue.status == IssueStatus.REPARSE_REQUIRED for issue in issues
            ),
            "rejected_issue_count": sum(
                issue.status == IssueStatus.REJECTED for issue in issues
            ),
            "resolved_issue_count": len(resolved_issues),
            "rejected_repair_count": len(repair_result.rejected),
            "repaired_table_count": sum(
                1
                for repair in repair_result.applied
                if repair.rule_id in {"QL-RPR-003", "QL-RPR-004"}
            ),
        },
        reparse_recommendation=None,
    )
    return QualityPackage(
        schema_name="QualityPackage",
        document_id=parsed_document.document_id,
        optimized_markdown=optimized_markdown,
        canonical_document=canonical,
        quality_report=report,
    )
