"""标题树规则（QL-HDG-*，spec §5.4）。

核心：按 (order_index, block_id) 确定性排序 + heading stack；
层级证据不足时用编号模式（"1.1 背景"）恢复候选层级，但只允许 inferred，
绝不强行 verified；禁止创建无来源的虚拟标题节点。
"""

from __future__ import annotations

import re

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
    RelationCandidate,
    RuleResult,
)
from .base import QualityRule

# 编号模式："1"、"1.1"、"1.1.2"、"一、"、"第一章" 等
_NUMBERED_HEADING = re.compile(
    r"^\s*(?:第?[一二三四五六七八九十百]+[章节部分篇]?|(\d+(?:\.\d+)*))\s*[、.\s]?(.*)$"
)




def _heading_text(block) -> str:
    """Return heading text with markdown heading syntax removed as a fallback."""
    value = block.text if block.text is not None else block.markdown
    return re.sub(r"^\s*#{1,6}\s*", "", value or "").strip()


def _numbered_level(text: str) -> int | None:
    """从编号模式推断层级："1.1" -> 2，"1" -> 1；无编号返回 None。

    只作为候选证据（inferred），不取代解析器 heading_level。
    """
    if not text:
        return None
    match = re.match(r"^\s*(\d+(?:\.\d+)*)\s*[、.\s]*(.*)$", text)
    if match:
        parts = match.group(1).split(".")
        return len(parts)
    # 中文序号：一级
    if re.match(r"^\s*[一二三四五六七八九十百]+[、.．]", text) or re.match(
        r"^\s*第[一二三四五六七八九十百]+[章节部分篇]", text
    ):
        return 1
    return None


def _strip_numbering(text: str) -> str:
    """去除编号前缀，用于关系 evidence。"""
    return re.sub(r"^\s*(?:\d+(?:\.\d+)*|[一二三四五六七八九十百]+)[、.．\s]+", "", text or "").strip()


class QL_HDG_001_HeadingFields(QualityRule):
    """标题字段完整性：heading 缺 level 且无编号 → 无法确定层级。"""

    rule_id = "QL-HDG-001"
    required_evidence = (
        EvidenceRequirement(kind="blocks", required_state="available"),
        EvidenceRequirement(kind="heading_level", required_state="partial_allowed"),
    )

    def execute(self, context: EvidenceContext) -> RuleResult:
        headings = context.blocks_by_kind(BlockKind.HEADING)
        undetermined = [
            b
            for b in headings
            if b.heading_level is None and _numbered_level(_heading_text(b)) is None
        ]
        issues: list[IssueDraft] = []
        if undetermined:
            issues.append(
                IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="heading_structure",
                    message=f"{len(undetermined)} 个标题既无 heading_level 也无编号模式，"
                    "层级无法确定。",
                    affected_block_ids=[str(b.id) for b in undetermined],
                )
            )
        state = (
            QualityCapabilityState.MANUAL_REVIEW_REQUIRED
            if issues
            else QualityCapabilityState.VERIFIED
        )
        return RuleResult(
            issues=tuple(issues),
            capability_observations=(
                CapabilityObservation(
                    capability_name="heading_structure_evidence",
                    observed_state=state,
                ),
            ),
        )


class QL_HDG_004_BuildTree(QualityRule):
    """parent_child 构建：stack 算法 + 编号辅助（spec §5.4）。"""

    rule_id = "QL-HDG-004"
    required_evidence = (
        EvidenceRequirement(kind="blocks", required_state="available"),
        EvidenceRequirement(kind="block_order", required_state="partial_allowed"),
    )

    def execute(self, context: EvidenceContext) -> RuleResult:
        headings = [
            b for b in context.ordered_blocks() if b.kind == BlockKind.HEADING
        ]
        issues: list[IssueDraft] = []
        candidates: list[RelationCandidate] = []
        observations: list[CapabilityObservation] = []

        order_conflict = bool(context.duplicate_order_indices)
        if order_conflict:
            issues.append(
                IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="reading_order_conflict",
            message=("标题存在重复 order_index，阅读顺序不确定，关系降级为 inferred。"),
                    affected_block_ids=[str(h.id) for h in headings],
                )
            )

        # 层级粒度检测：同一 parser level 下出现多个编号层级，或全部标题同 level
        # （真实解析器常见缺陷：文档标题与章节全部标为 level 2）→ 编号重建（inferred）
        level_groups: dict[int, set[int | None]] = {}
        for heading in headings:
            if heading.heading_level is not None:
                level_groups.setdefault(heading.heading_level, set()).add(
                    _numbered_level(_heading_text(heading))
                )
        granularity_suspect = any(
            len({v for v in values if v is not None}) > 1
            for values in level_groups.values()
        )
        all_levels = {
            h.heading_level for h in headings if h.heading_level is not None
        }
        uniform_level = len(all_levels) == 1 and len(headings) > 1
        rebuild_by_numbering = granularity_suspect or uniform_level
        if rebuild_by_numbering:
            issues.append(
                IssueDraft(
                    severity=IssueSeverity.INFO,
                    category="heading_level_granularity_suspect",
                    message="解析器标题层级粒度可疑（同层级含多级编号），改用编号模式恢复层级。",
                    affected_block_ids=[str(h.id) for h in headings],
                )
            )

        # stack: [(heading, effective_level)]
        stack: list[tuple] = []
        root_seen = False
        for heading in headings:
            level = heading.heading_level
            numbered = _numbered_level(_heading_text(heading))
            if rebuild_by_numbering:
                # 粒度可疑：编号优先；无编号但有解析器层级时保留该证据。
                effective_level = numbered
                source = "numbering"
                if effective_level is None and level is not None:
                    effective_level = level
                    source = "parser_level_fallback"
                if effective_level is None and not root_seen:
                    effective_level = 1  # 文档标题作为树根
                    source = "document_root"
            else:
                effective_level = level if level is not None else numbered
                source = "parser_level" if level is not None else "numbering"

            if effective_level is None:
                # 无法确定层级：不创建关系（不强行恢复）
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="heading_level_missing",
                        message=f"标题层级无法确定: {_heading_text(heading)[:30]!r}",
                        affected_block_ids=[str(heading.id)],
                    )
                )
                continue

            # 弹出 level >= 当前的所有标题
            while stack and stack[-1][1] >= effective_level:
                stack.pop()
            if not stack:
                # 只有 H1（或编号恢复的一级标题）可作为无父根。
                # 开头直接 H2/H3 没有可验证父节点，保留 inferred；不创建虚拟 H1。
                if not root_seen:
                    root_seen = True
                    if effective_level > 1:
                        issues.append(
                            IssueDraft(
                                severity=IssueSeverity.WARNING,
                                category="heading_parent_missing",
                                message=f"标题 {_heading_text(heading)[:30]!r} 无父节点（level={effective_level}）。",
                                affected_block_ids=[str(heading.id)],
                            )
                        )
                    stack.append((heading, effective_level))
                    continue
                if effective_level > 1:
                    issues.append(
                        IssueDraft(
                            severity=IssueSeverity.WARNING,
                            category="heading_parent_missing",
                            message=f"标题 {_heading_text(heading)[:30]!r} 无父节点（level={effective_level}）。",
                            affected_block_ids=[str(heading.id)],
                        )
                    )
                stack.append((heading, effective_level))
                continue

            parent, parent_level = stack[-1]
            # 层级跳跃：parent_level+1 < effective_level → 跳级
            jump = effective_level > parent_level + 1
            state = QualityCapabilityState.VERIFIED
            if jump:
                state = QualityCapabilityState.INFERRED
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.INFO,
                        category="heading_level_jump",
                        message=f"标题层级跳跃 {parent_level} → {effective_level}: "
                        f"{_heading_text(heading)[:30]!r}",
                        affected_block_ids=[str(parent.id), str(heading.id)],
                    )
                )
            elif source in ("numbering", "document_root", "parser_level_fallback"):
                # 编号/文档根恢复的层级：inferred
                # （spec：只有层级、顺序和来源证据一致才 verified）
                state = QualityCapabilityState.INFERRED

            # 阅读顺序冲突或孤儿根会污染整棵树，禁止输出 verified。
            if order_conflict or any(i.category == "heading_parent_missing" for i in issues):
                state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED
            elif not (
                parent.order_index is not None
                and heading.order_index is not None
                and parent.source_block_id
                and heading.source_block_id
            ):
                state = min(
                    state,
                    QualityCapabilityState.INFERRED,
                    key=lambda value: {
                        QualityCapabilityState.UNAVAILABLE: 0,
                        QualityCapabilityState.MANUAL_REVIEW_REQUIRED: 1,
                        QualityCapabilityState.INFERRED: 2,
                        QualityCapabilityState.VERIFIED: 3,
                    }[value],
                )

            candidates.append(
                RelationCandidate(
                    relation_type="parent_child",
                    from_id=str(parent.id),
                    to_id=str(heading.id),
                    state=state,
                    evidence_refs=[
                        EvidenceRef(object_type="block", object_id=str(parent.id), field_path="heading_level"),
                        EvidenceRef(object_type="block", object_id=str(heading.id), field_path="heading_level"),
                        EvidenceRef(object_type="block", object_id=str(parent.id), field_path="order_index"),
                        EvidenceRef(object_type="block", object_id=str(heading.id), field_path="order_index"),
                        EvidenceRef(object_type="block", object_id=str(parent.id), field_path="source_block_id"),
                        EvidenceRef(object_type="block", object_id=str(heading.id), field_path="source_block_id"),
                    ],
                )
            )
            stack.append((heading, effective_level))

        # 能力观测：存在孤立标题（层级证据冲突）→ 整树 inferred。
        has_orphan = any(i.category == "heading_parent_missing" for i in issues)
        if candidates or has_orphan or order_conflict:
            verified_count = sum(
                1 for c in candidates if c.state == QualityCapabilityState.VERIFIED
            )
            if has_orphan or order_conflict:
                state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED
            elif not candidates:
                state = QualityCapabilityState.UNAVAILABLE
            elif verified_count == len(candidates):
                state = QualityCapabilityState.VERIFIED
            elif any(
                c.state == QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                for c in candidates
            ):
                state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED
            else:
                state = QualityCapabilityState.INFERRED
            observations.append(
                CapabilityObservation(
                    capability_name="heading_tree_reliable",
                    observed_state=state,
                    evidence_refs=[c.evidence_refs[0] for c in candidates if c.evidence_refs],
                )
            )
        return RuleResult(
            issues=tuple(issues),
            relation_candidates=tuple(candidates),
            capability_observations=tuple(observations),
        )
