"""质量流水线：EvidenceContext → 规则 → 能力矩阵 → Gate → QualityPackage。

M1 覆盖：完整性规则 + 来源规则 + 能力矩阵 + Gate + 最小 canonical。
表格/标题/引用能力在本里程碑如实标注"规则未实现"且不阻塞（对应能力
在 M2/M3 落地后接入）。
"""

from __future__ import annotations

from uuid import uuid4

from document_parser.domain.model.contracts import (
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

from .builders.canonical import QUALITY_PIPELINE_VERSION, build_canonical_document
from .config import QualityConfig
from .evidence.context import EvidenceContext
from .gates.capabilities import CapabilityMatrixBuilder
from .gates.evaluator import GateEvaluator
from .ids import issue_id
from .models_internal import EvidenceRef, IssueDraft, RuleResult
from .hashing import (
    markdown_bytes,
    sha256_bytes,
    sha256_text,
    stable_json_bytes,
)
from .repairs.registry import WHITELIST_REPAIRS, apply_repairs
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
)
from .rules.cross_page import QL_TBL_007_CrossPageContinuation, QL_TBL_008_ColumnDrift

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


def run_pipeline(
    parsed_document: ParsedDocument,
    *,
    config: QualityConfig | None = None,
    rules: tuple[type[QualityRule], ...] = QUALITY_RULES,
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
    canonical = build_canonical_document(
        context,
        relation_candidates=tuple(relation_candidates),
        binding_candidates=tuple(binding_candidates),
    )

    # 4. Gate 决策（M1 无 reparse 来源，无 recommendation）
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
