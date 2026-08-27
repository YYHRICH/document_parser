"""数字引用绑定规则（QL-REF-*，spec §5.5.1 MVP）。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from quality.contracts import (
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

_REF_HEADING = re.compile(r"^(?:参考文献|references?|bibliography|文献)$", re.IGNORECASE)
_HEADING_NUMBER_PREFIX = re.compile(
    r"^\s*(?:(?:\d+(?:\.\d+)*)|(?:第?[一二三四五六七八九十百]+[章节部分篇]?))"
    r"\s*[、.．:：-]?\s*"
)
_EXPLANATORY = re.compile(r"引用规则|指向参考文献|分别指|指第")
_MARKER = re.compile(r"\[(\d+(?:\s*[,，]\s*\d+|\s*[-–]\s*\d+)*)\]")
_MAX_EXPAND = 50
_EXPLICIT_LABEL = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[\.、)）])\s*")
_REFERENCE_ENTRY_KINDS = (BlockKind.PARAGRAPH, BlockKind.REFERENCE, BlockKind.LIST)


def _block_text(block, *, heading: bool = False) -> str:
    value = block.text if block.text is not None else block.markdown
    value = value or ""
    if heading:
        value = re.sub(r"^\s*#{1,6}\s*", "", value)
    return value.strip()


def _text_field(block) -> str:
    return "text" if block.text is not None else "markdown"


def _is_reference_heading(block) -> bool:
    if block.kind != BlockKind.HEADING:
        return False
    text = _block_text(block, heading=True)
    if _REF_HEADING.fullmatch(text):
        return True
    return bool(_REF_HEADING.fullmatch(_HEADING_NUMBER_PREFIX.sub("", text, count=1)))


def _reference_heading_index(blocks) -> int | None:
    for i, block in enumerate(blocks):
        if _is_reference_heading(block):
            return i
    return None


@dataclass(frozen=True)
class ReferenceEntry:
    key: str
    block_id: str
    source_block_id: str
    text: str

    @property
    def number(self) -> int:
        return int(self.key)


def _entry_label(block, fallback: int) -> str:
    for metadata_key in ("reference_label", "marker"):
        metadata_label = block.metadata.get(metadata_key)
        if metadata_label is None:
            continue
        match = re.search(r"\d+", str(metadata_label))
        if match:
            return match.group(0)
    match = _EXPLICIT_LABEL.match(_block_text(block))
    if match:
        return match.group(1) or match.group(2)
    return str(fallback)


def build_reference_index(context: EvidenceContext) -> list[ReferenceEntry]:
    """恢复参考条目；显式标签优先，未标注条目保留顺序回退。"""
    blocks = context.ordered_blocks()
    ref_heading = _reference_heading_index(blocks)
    if ref_heading is None:
        return []

    entries: list[ReferenceEntry] = []
    fallback = 1
    for block in blocks[ref_heading + 1 :]:
        if block.kind == BlockKind.HEADING:
            break
        if block.kind not in _REFERENCE_ENTRY_KINDS:
            continue
        text = _block_text(block)
        if not text or _EXPLANATORY.search(text):
            continue
        key = _entry_label(block, fallback)
        fallback += 1
        entries.append(
            ReferenceEntry(
                key=key,
                block_id=str(block.id),
                source_block_id=block.source_block_id or "",
                text=text,
            )
        )
    return entries


def _expand_marker(marker: str) -> list[int] | None:
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
    return list(dict.fromkeys(numbers))


def _is_markdown_link(text: str, match: re.Match[str]) -> bool:
    """[label](url)（含图片链接）不是数字引用。"""
    if match.start() > 0 and text[match.start() - 1] == "!":
        return True
    tail = text[match.end() :]
    return bool(re.match(r"\s*\(", tail))


class QL_REF_001_ReferenceIndex(QualityRule):
    rule_id = "QL-REF-001"
    required_evidence = (
        EvidenceRequirement(kind="blocks", required_state="available"),
        EvidenceRequirement(kind="block_order", required_state="partial_allowed"),
    )

    def execute(self, context: EvidenceContext) -> RuleResult:
        entries = build_reference_index(context)
        issues = []
        if not entries and _reference_heading_index(context.ordered_blocks()) is not None:
            issues.append(
                IssueDraft(
                    severity=IssueSeverity.INFO,
                    category="reference_structure",
                    message="存在参考文献标题但未恢复出任何条目。",
                    affected_block_ids=[],
                )
            )
        return RuleResult(
            issues=tuple(issues),
            capability_observations=(CapabilityObservation(
                capability_name="reference_index_built",
                observed_state=QualityCapabilityState.VERIFIED if entries else QualityCapabilityState.UNAVAILABLE,
            ),),
        )


class QL_REF_004_BindCitations(QualityRule):
    rule_id = "QL-REF-004"
    required_evidence = (
        EvidenceRequirement(kind="blocks", required_state="available"),
        EvidenceRequirement(kind="block_order", required_state="partial_allowed"),
    )

    def execute(self, context: EvidenceContext) -> RuleResult:
        index = build_reference_index(context)
        by_key: dict[str, list[ReferenceEntry]] = {}
        for entry in index:
            by_key.setdefault(entry.key, []).append(entry)
        ref_heading = _reference_heading_index(context.ordered_blocks())
        ordered = context.ordered_blocks()
        body = ordered if ref_heading is None else ordered[:ref_heading]
        order_conflict = bool(context.duplicate_order_indices)
        issues: list[IssueDraft] = []
        candidates: list[RelationCandidate] = []
        if order_conflict:
            issues.append(IssueDraft(
                severity=IssueSeverity.WARNING,
                category="reading_order_conflict",
                message="存在重复 order_index，引用绑定顺序不确定，关系降级为人工复核。",
                affected_block_ids=[],
            ))

        for block in body:
            if block.kind not in _REFERENCE_ENTRY_KINDS:
                continue
            text = _block_text(block)
            if _EXPLANATORY.search(text):
                continue
            field = _text_field(block)
            for match in _MARKER.finditer(text):
                if _is_markdown_link(text, match):
                    continue
                marker = match.group(0)
                expanded = _expand_marker(match.group(1))
                if not expanded:
                    continue
                offset = match.start()
                missing = [str(n) for n in expanded if str(n) not in by_key]
                ambiguous = [str(n) for n in expanded if len(by_key.get(str(n), [])) > 1]
                found = [str(n) for n in expanded if len(by_key.get(str(n), [])) == 1]
                marker_evidence = {
                    "marker": marker,
                    "marker_offset": offset,
                    "normalized_labels": [str(n) for n in expanded],
                    "missing_labels": missing,
                    "ambiguous_labels": ambiguous,
                    "candidate_ids": [e.block_id for n in expanded for e in by_key.get(str(n), [])],
                }
                if missing:
                    issues.append(IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="citation_binding",
                        message=f"引用 {marker} 展开后 {len(missing)} 个编号在参考索引中缺失: {', '.join(missing)}",
                        affected_block_ids=[str(block.id)],
                        evidence_refs=[EvidenceRef(object_type="block", object_id=str(block.id), field_path=field)],
                        evidence=marker_evidence,
                    ))
                if ambiguous:
                    issues.append(IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="ambiguous_target",
                        message=f"引用 {marker} 的编号存在多个参考条目，无法唯一绑定: {', '.join(ambiguous)}",
                        affected_block_ids=[str(block.id)],
                        evidence_refs=[EvidenceRef(object_type="block", object_id=str(block.id), field_path=field)],
                        evidence=marker_evidence,
                    ))
                # 一个 marker 只在其展开的所有标签都能唯一命中时成立；
                # 部分绑定会把不完整证据误报成 verified。
                if missing or ambiguous:
                    continue
                for key in found:
                    entry = by_key[key][0]
                    if order_conflict:
                        state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                    elif not (block.source_block_id and entry.source_block_id):
                        state = QualityCapabilityState.INFERRED
                    else:
                        state = QualityCapabilityState.VERIFIED
                    candidates.append(RelationCandidate(
                        relation_type="reference_of",
                        from_id=str(block.id),
                        to_id=entry.block_id,
                        state=state,
                        marker_key=f"{offset}:{marker}",
                        evidence_refs=[
                            EvidenceRef(object_type="block", object_id=str(block.id), field_path=field),
                            EvidenceRef(object_type="block", object_id=entry.block_id, field_path="text"),
                        ],
                        evidence={**marker_evidence, "target_key": key},
                    ))

        observations: list[CapabilityObservation] = []
        if index:
            verified = sum(c.state == QualityCapabilityState.VERIFIED for c in candidates)
            observations.append(CapabilityObservation(
                capability_name="non_table_relation_reliable",
                observed_state=(QualityCapabilityState.VERIFIED if verified == len(candidates) and candidates else QualityCapabilityState.MANUAL_REVIEW_REQUIRED if candidates or issues else QualityCapabilityState.UNAVAILABLE),
            ))
        return RuleResult(issues=tuple(issues), relation_candidates=tuple(candidates), capability_observations=tuple(observations))
