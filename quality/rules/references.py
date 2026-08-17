"""数字引用绑定规则（QL-REF-*，spec §5.5.1 MVP）。

参考索引恢复：参考文献标题之后的连续段落按顺序编号（第 k 条 = [k]）。
正文 marker 支持 [1]、[12]、[1, 3, 5]、[2-4]/[2–4]、[1][2]；
范围展开只在参考索引确实存在所有编号时成立。
目标不唯一、编号缺失 → 绝不 verified。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from document_parser.core.contracts import (
    BlockKind,
    IssueSeverity,
    QualityCapabilityState,
)

from quality.evidence.context import EvidenceContext
from quality.evidence.requirements import EvidenceRequirement
from quality.models_internal import (
    CapabilityObservation,
    EvidenceRef,
    IssueDraft,
    RelationCandidate,
    RuleResult,
)
from quality.rules.base import QualityRule

# 参考文献标题模式
_REF_HEADING = re.compile(r"^(?:参考文献|references?|bibliography|文献)$", re.IGNORECASE)

# 说明性文字过滤（合成文档的"引用规则"说明行）
_EXPLANATORY = re.compile(r"引用规则|指向参考文献|分别指|指第")

# marker：([1]、[12]、[1, 3, 5]、[2-4]、[2–4]）
_MARKER = re.compile(r"\[(\d+(?:\s*[,，]\s*\d+|\s*[-–]\s*\d+)*)\]")

# 范围展开上限（防误报）
_MAX_EXPAND = 50


@dataclass(frozen=True)
class ReferenceEntry:
    """参考索引条目：按顺序编号的第 k 条（k 从 1 开始）。"""

    key: str
    block_id: str
    source_block_id: str
    text: str

    @property
    def number(self) -> int:
        return int(self.key)


def build_reference_index(context: EvidenceContext) -> list[ReferenceEntry]:
    """在参考文献标题之后按顺序恢复编号的参考条目（有位置+顺序证据）。

    过滤空段落与说明性文字（如"引用规则：..."）。
    """
    blocks = context.ordered_blocks()
    ref_start: int | None = None
    for i, block in enumerate(blocks):
        if block.kind == BlockKind.HEADING and _REF_HEADING.match((block.text or "").strip()):
            ref_start = i + 1
            break
    if ref_start is None:
        return []

    entries: list[ReferenceEntry] = []
    for block in blocks[ref_start:]:
        text = (block.text or "").strip()
        if not text:
            continue
        if _EXPLANATORY.search(text):
            continue
        entries.append(
            ReferenceEntry(
                key=str(len(entries) + 1),
                block_id=str(block.id),
                source_block_id=block.source_block_id or "",
                text=text,
            )
        )
    return entries


def _expand_marker(marker: str) -> list[int] | None:
    """展开 marker 内部编号：'1' -> [1]；'1, 3, 5' -> [1,3,5]；'2-4' -> [2,3,4]。

    返回 None 表示解析失败（非法格式），空列表表示无编号。
    """
    numbers: list[int] = []
    for part in marker.split(","):
        part = part.strip()
        if not part:
            return None
        if re.fullmatch(r"\d+", part):
            numbers.append(int(part))
            continue
        match = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", part)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if start > end or end - start > _MAX_EXPAND:
                return None
            numbers.extend(range(start, end + 1))
            continue
        return None
    return numbers


class QL_REF_001_ReferenceIndex(QualityRule):
    """参考索引构建（有标题+顺序证据，输出观测供 004 使用）。"""

    rule_id = "QL-REF-001"
    required_evidence = (
        EvidenceRequirement(kind="blocks", required_state="available"),
        EvidenceRequirement(kind="block_order", required_state="partial_allowed"),
    )

    def execute(self, context: EvidenceContext) -> RuleResult:
        entries = build_reference_index(context)
        observations = []
        issues = []
        if not entries:
            has_ref_heading = any(
                b.kind == BlockKind.HEADING
                and _REF_HEADING.match((b.text or "").strip())
                for b in context.parsed.blocks
            )
            if has_ref_heading:
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.INFO,
                        category="reference_structure",
                        message="存在参考文献标题但未恢复出任何条目。",
                        affected_block_ids=[],
                    )
                )
        observations.append(
            CapabilityObservation(
                capability_name="reference_index_built",
                observed_state=(
                    QualityCapabilityState.VERIFIED
                    if entries
                    else QualityCapabilityState.UNAVAILABLE
                ),
            )
        )
        return RuleResult(
            issues=tuple(issues),
            capability_observations=tuple(observations),
        )


class QL_REF_004_BindCitations(QualityRule):
    """正文数字引用 → reference_of 绑定（唯一性判定）。"""

    rule_id = "QL-REF-004"
    required_evidence = (
        EvidenceRequirement(kind="blocks", required_state="available"),
        EvidenceRequirement(kind="block_order", required_state="partial_allowed"),
    )

    def execute(self, context: EvidenceContext) -> RuleResult:
        index = build_reference_index(context)
        by_key = {entry.key: entry for entry in index}

        issues: list[IssueDraft] = []
        candidates: list[RelationCandidate] = []
        bound_markers: set[str] = set()

        for block in context.ordered_blocks():
            if block.kind not in (BlockKind.PARAGRAPH, BlockKind.REFERENCE):
                continue
            text = block.text or ""
            if _EXPLANATORY.search(text):
                continue  # 说明性文字不算引用
            for match in _MARKER.finditer(text):
                marker = match.group(0)
                if marker in bound_markers:
                    continue
                expanded = _expand_marker(match.group(1))
                if expanded is None or not expanded:
                    continue
                bound_markers.add(marker)
                offset = match.start()
                # 目标唯一性：逐个编号查索引
                missing = [str(n) for n in expanded if str(n) not in by_key]
                found = [str(n) for n in expanded if str(n) in by_key]

                if missing:
                    issues.append(
                        IssueDraft(
                            severity=IssueSeverity.WARNING,
                            category="citation_binding",
                            message=f"引用 {marker} 展开后 {len(missing)} 个编号在参考索引中缺失: "
                            f"{', '.join(missing)}",
                            affected_block_ids=[str(block.id)],
                            evidence_refs=[
                                EvidenceRef(
                                    object_type="block",
                                    object_id=str(block.id),
                                    field_path="text",
                                )
                            ],
                        )
                    )
                for key in found:
                    entry = by_key[key]
                    candidates.append(
                        RelationCandidate(
                            relation_type="reference_of",
                            from_id=str(block.id),
                            to_id=entry.block_id,
                            state=QualityCapabilityState.VERIFIED,
                            evidence_refs=[
                                EvidenceRef(
                                    object_type="block",
                                    object_id=str(block.id),
                                    field_path="text",
                                ),
                                EvidenceRef(
                                    object_type="block",
                                    object_id=entry.block_id,
                                    field_path="text",
                                ),
                            ],
                        )
                    )

        observations: list[CapabilityObservation] = []
        if index:
            verified = sum(
                1 for c in candidates if c.state == QualityCapabilityState.VERIFIED
            )
            observations.append(
                CapabilityObservation(
                    capability_name="non_table_relation_reliable",
                    observed_state=(
                        QualityCapabilityState.VERIFIED
                        if verified == len(candidates) and candidates
                        else QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                        if candidates
                        else QualityCapabilityState.UNAVAILABLE
                    ),
                )
            )
        return RuleResult(
            issues=tuple(issues),
            relation_candidates=tuple(candidates),
            capability_observations=tuple(observations),
        )
