"""质量流水线：EvidenceContext → 规则 → 能力矩阵 → Gate → QualityPackage。

M1 覆盖：完整性规则 + 来源规则 + 能力矩阵 + Gate + 最小 canonical。
表格/标题/引用能力在本里程碑如实标注"规则未实现"且不阻塞（对应能力
在 M2/M3 落地后接入）。
"""

from __future__ import annotations

from uuid import uuid4

from document_parser.core.contracts import (
    GateSummary,
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
from quality.gates.capabilities import CapabilityMatrixBuilder
from quality.gates.evaluator import GateEvaluator
from quality.ids import issue_id
from quality.models_internal import IssueDraft, RuleResult
from quality.packaging.hashing import (
    markdown_bytes,
    sha256_bytes,
    sha256_text,
    stable_json_bytes,
)
from quality.rules.base import QualityRule
from quality.rules.completeness import (
    QL_CONT_001_BlocksExist,
    QL_CONT_002_OrderIndex,
    QL_CONT_003_KindContent,
)
from quality.rules.provenance import (
    QL_PROV_001_SourceTraceable,
    QL_PROV_002_AnchorValid,
    QL_PROV_003_ArtifactsValid,
    QL_PROV_004_CapabilityReasons,
)

# M1 注册的规则集合
M1_RULES: tuple[type[QualityRule], ...] = (
    QL_CONT_001_BlocksExist,
    QL_CONT_002_OrderIndex,
    QL_CONT_003_KindContent,
    QL_PROV_001_SourceTraceable,
    QL_PROV_002_AnchorValid,
    QL_PROV_003_ArtifactsValid,
    QL_PROV_004_CapabilityReasons,
)


def _document_key(parsed: ParsedDocument) -> str:
    return parsed.source_sha256 or str(parsed.document_id)


def run_pipeline(
    parsed_document: ParsedDocument,
    *,
    config: QualityConfig | None = None,
    rules: tuple[type[QualityRule], ...] = M1_RULES,
) -> QualityPackage:
    """执行质量流水线，返回完整 QualityPackage（含内存哈希绑定）。"""
    config = config or QualityConfig()
    context = EvidenceContext(parsed_document)
    doc_key = _document_key(parsed_document)

    # 1. 执行规则（证据不足时规则自行降级或跳过）
    issue_drafts: list[IssueDraft] = []
    observations = []
    for rule_type in rules:
        rule = rule_type()
        result: RuleResult = rule.execute(context)
        issue_drafts.extend(result.issues)
        observations.extend(result.capability_observations)

    # 2. 能力矩阵
    matrix_builder = CapabilityMatrixBuilder(config)
    verdicts = matrix_builder.build(observations, context)

    # 3. canonical document
    canonical = build_canonical_document(context)

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
                ref.object_type: f"{ref.object_id}:{ref.field_path}"
                for ref in draft.evidence_refs
            },
        )
        for draft in issue_drafts
    ]

    # 6. 哈希绑定（顺序：optimized → canonical → report → manifest）
    optimized_markdown = parsed_document.markdown  # M1 无修复，no-op 合法（D-07）
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
        applied_repairs=[],
        capability_matrix=matrix_builder.to_public_assessments(verdicts),
        gate_summary=decision.summary,
        metrics={
            "quality_pipeline_version": QUALITY_PIPELINE_VERSION,
            "source_block_count": len(parsed_document.blocks),
            "canonical_block_count": len(canonical.blocks),
            "table_count": len(parsed_document.tables),
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
