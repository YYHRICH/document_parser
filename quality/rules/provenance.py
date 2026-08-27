"""来源与可追溯性规则（QL-PROV-*，spec §5.2）。

- QL-PROV-001：source_block_id 可回溯；
- QL-PROV-002：page/bbox 合法且粒度真实（禁止伪造 locator）；
- QL-PROV-003：assets/native_artifacts 引用与哈希结构合法；
- QL-PROV-004：capabilities 非 available 状态必须带 reason（契约层已强制，规则层验证观测）。
"""

from __future__ import annotations

from quality.contracts import (
    BlockKind,
    EvidenceAvailability,
    IssueSeverity,
    QualityCapabilityState,
)

from quality.evidence.context import EvidenceContext
from quality.evidence.requirements import EvidenceRequirement
from quality.models_internal import (
    CapabilityObservation,
    EvidenceRef,
    IssueDraft,
    RuleResult,
)
from quality.rules.base import QualityRule


def _valid_sha256(value: object) -> bool:
    """校验 SHA-256 是否为 64 位十六进制字符串。"""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _coordinate_system(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"bottomleft", "bottom_left", "bottomleft_absolute", "bottom_left_absolute"}:
        return "bottom_left_absolute"
    return normalized


def _valid_bbox(bbox, coordinate_system: str | None = None) -> bool:
    """bbox 必须为 4 元组，并按其坐标系检查垂直方向。"""
    if not isinstance(bbox, (tuple, list)) or len(bbox) != 4:
        return False
    l, top_or_upper, r, bottom_or_lower = bbox
    try:
        if _coordinate_system(coordinate_system) == "bottom_left_absolute":
            return bool(r > l and top_or_upper > bottom_or_lower)
        return bool(r > l and bottom_or_lower > top_or_upper)
    except TypeError:
        return False


def _bbox_requirement(coordinate_system: str | None) -> str:
    if _coordinate_system(coordinate_system) == "bottom_left_absolute":
        return "r>l 且 upper_y>lower_y"
    return "r>l 且 bottom>top"


class QL_PROV_001_SourceTraceable(QualityRule):
    """source_block_id 可回溯（缺失时 provenance capability 降级）。"""

    rule_id = "QL-PROV-001"
    required_evidence = (
        EvidenceRequirement(kind="blocks", required_state="available"),
        EvidenceRequirement(kind="provenance", required_state="available"),
    )

    def execute(self, context: EvidenceContext) -> RuleResult:
        missing = [
            b for b in context.parsed.blocks if not b.source_block_id
        ]
        issues: list[IssueDraft] = []
        if missing:
            issues.append(
                IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="provenance",
                    message=f"{len(missing)} 个 block 缺少 source_block_id，无法回溯到解析器原始对象。",
                    affected_block_ids=[str(b.id) for b in missing],
                )
            )
        # 重复 source_block_id 也属于回溯模糊
        duplicated_sources = set(context.duplicate_source_block_ids)
        if duplicated_sources:
            issues.append(
                IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="provenance",
                    message=f"{len(duplicated_sources)} 个 source_block_id 被多个 block 引用。",
                    affected_block_ids=[
                        str(b.id)
                        for b in context.parsed.blocks
                        if b.source_block_id in duplicated_sources
                    ],
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
                    capability_name="provenance_reliable",
                    observed_state=state,
                    evidence_refs=(
                        EvidenceRef(
                            object_type="document",
                            object_id=str(context.parsed.document_id),
                            field_path="blocks[].source_block_id",
                        ),
                    ),
                ),
            ),
        )


class QL_PROV_002_AnchorValid(QualityRule):
    """page/bbox 合法且粒度真实（禁止伪造 locator）。"""

    rule_id = "QL-PROV-002"
    required_evidence = (
        EvidenceRequirement(kind="blocks", required_state="available"),
        EvidenceRequirement(kind="block_anchor", required_state="partial_allowed"),
    )

    def execute(self, context: EvidenceContext) -> RuleResult:
        issues: list[IssueDraft] = []
        for block in context.parsed.blocks:
            anchor = block.anchor
            if anchor.bbox is not None and not _valid_bbox(anchor.bbox, anchor.coordinate_system):
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="provenance",
                        message=f"block bbox 非法: {anchor.bbox!r}（要求 {_bbox_requirement(anchor.coordinate_system)}）。",
                        affected_block_ids=[str(block.id)],
                    )
                )
            if anchor.bbox is None and anchor.bbox_granularity:
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="provenance",
                        message=f"声明了 bbox_granularity={anchor.bbox_granularity!r} 但没有 bbox，"
                        "locator 声明与内容不一致。",
                        affected_block_ids=[str(block.id)],
                    )
                )

        # 表格：有 cell bbox 但表格只声明了表级 bbox 的场景由表格规则处理；
        # 这里检查表级 bbox 合法性
        for table in context.parsed.tables:
            if table.bbox is not None and not _valid_bbox(table.bbox):
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="provenance",
                        message=f"table {table.table_id} bbox 非法: {table.bbox!r}",
                        affected_block_ids=[str(table.block_id)],
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
                    capability_name="provenance_reliable",
                    observed_state=state,
                ),
            ),
        )


class QL_PROV_003_ArtifactsValid(QualityRule):
    """assets/native_artifacts 引用与哈希结构合法（按 required_for_quality 判定 blocker）。"""

    rule_id = "QL-PROV-003"
    required_evidence = (
        EvidenceRequirement(kind="assets", required_state="partial_allowed"),
        EvidenceRequirement(kind="native_artifacts", required_state="partial_allowed"),
    )

    def execute(self, context: EvidenceContext) -> RuleResult:
        issues: list[IssueDraft] = []
        for asset in context.parsed.assets:
            if not _valid_sha256(asset.sha256):
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="provenance",
                        message=f"asset {asset.path} 缺少合法 sha256。",
                        affected_block_ids=[],
                    )
                )
        for artifact in context.parsed.native_artifacts:
            if not _valid_sha256(artifact.sha256):
                severity = (
                    IssueSeverity.CRITICAL
                    if artifact.required_for_quality
                    else IssueSeverity.WARNING
                )
                issues.append(
                    IssueDraft(
                        severity=severity,
                        category="provenance",
                        message=f"native artifact {artifact.artifact_id} 缺少合法 sha256"
                        + ("（required_for_quality）。" if artifact.required_for_quality else "。"),
                        affected_block_ids=[],
                    )
                )
        state = (
            QualityCapabilityState.MANUAL_REVIEW_REQUIRED
            if any(i.severity == IssueSeverity.WARNING for i in issues)
            else QualityCapabilityState.VERIFIED
        )
        if any(i.severity == IssueSeverity.CRITICAL for i in issues):
            state = QualityCapabilityState.REJECTED
        return RuleResult(
            issues=tuple(issues),
            capability_observations=(
                CapabilityObservation(
                    capability_name="provenance_reliable",
                    observed_state=state,
                ),
            ),
        )


class QL_PROV_004_CapabilityReasons(QualityRule):
    """capabilities 非 available 状态必须有 reason（契约层已强制，规则层验证观测）。"""

    rule_id = "QL-PROV-004"
    required_evidence = (
        EvidenceRequirement(kind="capabilities", required_state="available"),
    )

    def execute(self, context: EvidenceContext) -> RuleResult:
        issues: list[IssueDraft] = []
        for name, capability in context.parsed.capabilities.items():
            if capability.state in {
                EvidenceAvailability.PARTIAL,
                EvidenceAvailability.UNAVAILABLE,
                EvidenceAvailability.FAILED,
            } and not capability.reason:
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.CRITICAL,
                        category="provenance",
                        message=f"capability {name} 状态为 {capability.state} 但缺少 reason。",
                        affected_block_ids=[],
                    )
                )
        state = (
            QualityCapabilityState.VERIFIED
            if not issues
            else QualityCapabilityState.REJECTED
        )
        return RuleResult(
            issues=tuple(issues),
            capability_observations=(
                CapabilityObservation(
                    capability_name="capability_declaration_valid",
                    observed_state=state,
                ),
            ),
        )
