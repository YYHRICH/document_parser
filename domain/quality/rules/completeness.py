"""内容完整性规则（QL-CONT-*，spec §5.2）。

规则只产出 observations/issues，不得指定最终 Gate（唯一 Gate evaluator 决策）。
"""

from __future__ import annotations

from document_parser.domain.model.contracts import (
    BlockKind,
    IssueSeverity,
    QualityCapabilityState,
)

from ..evidence.context import EvidenceContext
from ..evidence.requirements import EvidenceRequirement
from ..models_internal import (
    CapabilityObservation,
    EvidenceRef,
    IssueDraft,
    RuleResult,
)
from .base import QualityRule


class QL_CONT_001_BlocksExist(QualityRule):
    """blocks 是否存在、ID 是否唯一（严重冲突进入 rejected/manual）。"""

    rule_id = "QL-CONT-001"
    required_evidence = (EvidenceRequirement(kind="blocks", required_state="available"),)

    def execute(self, context: EvidenceContext) -> RuleResult:
        issues: list[IssueDraft] = []
        if not context.parsed.blocks:
            issues.append(
                IssueDraft(
                    severity=IssueSeverity.CRITICAL,
                    category="content_completeness",
                    message="ParsedDocument 没有任何 blocks，输入不可信。",
                    affected_block_ids=[],
                    evidence_refs=[
                        EvidenceRef(
                            object_type="document",
                            object_id=str(context.parsed.document_id),
                            field_path="blocks",
                        )
                    ],
                )
            )
            return RuleResult(
                issues=tuple(issues),
                capability_observations=(
                    CapabilityObservation(
                        capability_name="content_complete",
                        observed_state=QualityCapabilityState.REJECTED,
                    ),
                ),
            )

        for block_id in context.duplicate_block_ids:
            issues.append(
                IssueDraft(
                    severity=IssueSeverity.CRITICAL,
                    category="content_completeness",
                    message=f"block ID 重复: {block_id}，来源定位不可信。",
                    affected_block_ids=[block_id],
                    evidence_refs=[
                        EvidenceRef(
                            object_type="block",
                            object_id=block_id,
                            field_path="id",
                        )
                    ],
                )
            )

        state = (
            QualityCapabilityState.REJECTED
            if issues
            else QualityCapabilityState.VERIFIED
        )
        return RuleResult(
            issues=tuple(issues),
            capability_observations=(
                CapabilityObservation(
                    capability_name="content_complete",
                    observed_state=state,
                    evidence_refs=(
                        EvidenceRef(
                            object_type="document",
                            object_id=str(context.parsed.document_id),
                            field_path="blocks",
                        ),
                    ),
                ),
            ),
        )


class QL_CONT_002_OrderIndex(QualityRule):
    """order_index 是否唯一、可确定排序（冲突部分禁止 verified 关系）。"""

    rule_id = "QL-CONT-002"
    required_evidence = (
        EvidenceRequirement(kind="blocks", required_state="available"),
        EvidenceRequirement(kind="block_order", required_state="partial_allowed"),
    )

    def execute(self, context: EvidenceContext) -> RuleResult:
        issues: list[IssueDraft] = []

        missing = [
            b for b in context.parsed.blocks if b.order_index is None
        ]
        if missing:
            issues.append(
                IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="reading_order",
                    message=f"{len(missing)} 个 block 缺少 order_index，阅读顺序不可完全确定。",
                    affected_block_ids=[str(b.id) for b in missing],
                )
            )

        for index in context.duplicate_order_indices:
            blocks = [
                b
                for b in context.parsed.blocks
                if b.order_index == index
            ]
            issues.append(
                IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="reading_order",
                    message=f"order_index={index} 被 {len(blocks)} 个 block 共用，顺序冲突。",
                    affected_block_ids=[str(b.id) for b in blocks],
                )
            )

        state = QualityCapabilityState.VERIFIED
        if issues:
            state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED
        return RuleResult(
            issues=tuple(issues),
            capability_observations=(
                CapabilityObservation(
                    capability_name="reading_order_reliable",
                    observed_state=state,
                ),
            ),
        )


class QL_CONT_003_KindContent(QualityRule):
    """block kind 与内容最低一致性（warning/manual，不自动改 kind）。"""

    rule_id = "QL-CONT-003"
    required_evidence = (EvidenceRequirement(kind="blocks", required_state="available"),)

    def execute(self, context: EvidenceContext) -> RuleResult:
        issues: list[IssueDraft] = []

        # heading 缺层级
        headings_without_level = [
            b
            for b in context.parsed.blocks
            if b.kind == BlockKind.HEADING and b.heading_level is None
        ]
        if headings_without_level:
            issues.append(
                IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="heading_structure",
                    message=f"{len(headings_without_level)} 个 heading 缺少 heading_level，"
                    "标题树只能保留 inferred 状态。",
                    affected_block_ids=[str(b.id) for b in headings_without_level],
                )
            )

        # 表格块没有对应 ParsedTable
        table_blocks_without_table = [
            b
            for b in context.parsed.blocks
            if b.kind == BlockKind.TABLE
            and context.table_for_block(str(b.id)) is None
        ]
        if table_blocks_without_table:
            issues.append(
                IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="table_structure",
                    message=f"{len(table_blocks_without_table)} 个 table block 没有对应 ParsedTable，"
                    "无法恢复网格。",
                    affected_block_ids=[str(b.id) for b in table_blocks_without_table],
                )
            )

        # 空内容 block（标题/段落无文本）
        empty_blocks = [
            b
            for b in context.parsed.blocks
            if b.kind in (BlockKind.PARAGRAPH, BlockKind.HEADING)
            and not (b.text or b.markdown or "").strip()
        ]
        if empty_blocks:
            issues.append(
                IssueDraft(
                    severity=IssueSeverity.INFO,
                    category="content_completeness",
                    message=f"{len(empty_blocks)} 个 block 内容为空。",
                    affected_block_ids=[str(b.id) for b in empty_blocks],
                )
            )

        state = QualityCapabilityState.VERIFIED
        if any(i.severity == IssueSeverity.WARNING for i in issues):
            state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED
        elif issues:
            state = QualityCapabilityState.INFERRED
        return RuleResult(
            issues=tuple(issues),
            capability_observations=(
                CapabilityObservation(
                    capability_name="kind_content_consistent",
                    observed_state=state,
                ),
            ),
        )
