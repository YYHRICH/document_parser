"""质量流水线：证据上下文 → 质量规则 → 能力矩阵 → 质量门 → QualityPackage。

当前规则集合覆盖完整性、来源、标题、引用和表格结构；能力矩阵会根据文档证据区分
已验证、不适用、需要人工复核和证据不足等状态。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from document_parser.core.contracts import (
    GateSummary,
    IssueSeverity,
    IssueStatus,
    PackageManifest,
    ParsedDocument,
    QualityIssue,
    QualityCapabilityState,
    QualityPackage,
    QualityReport,
    QualityState,
)

from quality.builders.canonical import QUALITY_PIPELINE_VERSION, build_canonical_document
from quality.config import QualityConfig
from quality.evidence.context import EvidenceContext
from quality.gates.capabilities import CapabilityMatrixBuilder
from quality.gates.evaluator import GateEvaluator
from quality.ids import issue_id
from quality.models_internal import EvidenceRef, IssueDraft, RelationCandidate, RuleResult
from quality.packaging.hashing import (
    markdown_bytes,
    sha256_bytes,
    sha256_text,
    stable_json_bytes,
)
from quality.repairs.registry import WHITELIST_REPAIRS, apply_repairs
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

# 注册的规则集合（证据、完整性与质量门 完整性/来源 + 标题层级与引用绑定 标题/引用 + 表格网格与字段绑定 表格）
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
        issue_drafts.extend(result.issues)
        observations.extend(result.capability_observations)
        relation_candidates.extend(result.relation_candidates)
        binding_candidates.extend(result.binding_candidates)
    return issue_drafts, observations, relation_candidates, binding_candidates


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


def _apply_relation_overrides(candidates: list, overrides: tuple[Any, ...]) -> list:
    """把已验证的 Agent 关系 Patch 覆盖到规则关系候选上。"""

    result = list(candidates)
    for patch in overrides:
        key = (patch.relation_type, patch.from_id, patch.to_id, patch.marker_key)
        result = [
            candidate
            for candidate in result
            if (
                candidate.relation_type,
                candidate.from_id,
                candidate.to_id,
                candidate.marker_key,
            )
            != key
        ]
        if patch.action == "upsert":
            result.append(
                RelationCandidate(
                    relation_type=patch.relation_type,
                    from_id=patch.from_id,
                    to_id=patch.to_id,
                    state=QualityCapabilityState.INFERRED,
                    marker_key=patch.marker_key,
                    evidence={"source": "agent_relation_patch"},
                )
            )
    return result


def run_pipeline(
    parsed_document: ParsedDocument,
    *,
    config: QualityConfig | None = None,
    rules: tuple[type[QualityRule], ...] = QUALITY_RULES,
    additional_metrics: Mapping[str, Any] | None = None,
    relation_overrides: tuple[Any, ...] | None = None,
) -> QualityPackage:
    """执行质量流水线，返回完整 QualityPackage（含内存哈希绑定）。"""
    config = config or QualityConfig()
    context = EvidenceContext(parsed_document)
    doc_key = _document_key(parsed_document)

    # 1. 先应用白名单修复，再以最终证据重跑规则。
    repair_result = apply_repairs(
        parsed_document.markdown,
        document_key=doc_key,
        affected_block_ids_by_rule=_repair_block_ids(parsed_document),
    )
    repaired_document = parsed_document.model_copy(
        update={
            "markdown": repair_result.markdown,
            "blocks": _apply_repairs_to_blocks(parsed_document),
        }
    )
    context = EvidenceContext(repaired_document)
    issue_drafts, observations, relation_candidates, binding_candidates = _execute_rules(
        context, rules
    )

    # 2. 能力矩阵
    matrix_builder = CapabilityMatrixBuilder(config)
    verdicts = matrix_builder.build(observations, context)

    # 3. canonical document（含关系与表格绑定）
    relation_candidates = _apply_relation_overrides(
        relation_candidates, relation_overrides or ()
    )
    canonical = build_canonical_document(
        context,
        relation_candidates=tuple(relation_candidates),
        binding_candidates=tuple(binding_candidates),
    )

    # 4. Gate 决策（证据、完整性与质量门 无 reparse 来源，无 recommendation）
    # 契约要求 reparse_required 必须带 recommendation；无合法建议时
    # evaluator 将 reparse 降级为 manual_review_required。
    evaluator = GateEvaluator(config.gate)
    decision = evaluator.decide(issue_drafts, verdicts)

    # 5. 组装 issues（稳定 ID）
    issues = [
        QualityIssue(
            issue_id=issue_id(
                doc_key,
                "draft",
                draft.affected_block_ids,
                draft.message[:32],
            ),
            severity=draft.severity,
            category=draft.category,
            status=IssueStatus.UNFIXED,
            message=draft.message,
            affected_block_ids=list(draft.affected_block_ids),
            evidence={
                **draft.evidence,
                "evidence_refs": [
                    {
                        "object_type": ref.object_type,
                        "object_id": ref.object_id,
                        "field_path": ref.field_path,
                        **({"value_sha256": ref.value_sha256} if ref.value_sha256 else {}),
                    }
                    for ref in draft.evidence_refs
                ],
            },
        )
        for draft in issue_drafts
    ]

    # 6. optimized markdown 已在规则重跑前生成；canonical/report 使用同一最终输入。
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
            "issue_count": len(issues),
            **dict(additional_metrics or {}),
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
