"""质量层内部不可变模型（规则之间传递用，不进入公共契约）。

规则只产出 ``RuleResult``（observations/candidates/proposals），
不得直接修改文档、写文件或指定最终 Gate 状态（唯一 Gate evaluator 决策，
见 gates/evaluator.py）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from quality.contracts import (
    CanonicalSourceLocator,
    IssueSeverity,
    QualityCapabilityState,
)

EvidenceObjectType = Literal[
    "document",
    "block",
    "table",
    "cell",
    "ocr_span",
    "asset",
    "native_artifact",
    "capability",
    "provenance",
]


@dataclass(frozen=True)
class EvidenceRef:
    """结构化证据引用：指向 ParsedDocument 中的真实字段。

    ``value_sha256`` 用于检测缓存或重复运行时引用的证据是否已变化。
    """

    object_type: EvidenceObjectType
    object_id: str
    field_path: str
    value_sha256: str | None = None


@dataclass(frozen=True)
class IssueDraft:
    """规则产出的质量问题草稿（最终 issue_id 由 ids.issue_id 生成）。"""

    severity: IssueSeverity
    category: str
    message: str
    # 在规则调度时填入，确保公共 issue ID 可区分规则来源。
    rule_id: str = field(default="", kw_only=True)
    affected_block_ids: list[str] = field(default_factory=list)
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RelationCandidate:
    """标题/引用关系候选（状态由产生它的规则根据证据强度给出，
    最终 status 由关系构建层映射；规则不得自行决定最终 Gate）。"""

    relation_type: str
    from_id: str
    to_id: str
    state: QualityCapabilityState = QualityCapabilityState.INFERRED
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    # Optional occurrence discriminator (e.g. citation marker offset) for stable IDs.
    marker_key: str = ""
    # Rule-specific structured evidence serialized into the canonical relation.
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BindingCandidate:
    """表格字段绑定候选。"""

    table_id: str
    block_id: str
    row_key: str
    column_path: list[str]
    value: str
    source_locator: CanonicalSourceLocator
    # D-09：单元格身份 = "r{row}c{col}" 坐标组合（朱提供 cell_id 后替换）
    cell_key: str = ""
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RepairProposal:
    """A deterministic repair candidate with an exact hash-guarded target.

    Rule code may create a proposal, but only RepairPolicy can authorize it and
    only RepairExecutor can mutate an internal working representation.
    """

    rule_id: str
    description: str
    affected_block_ids: list[str] = field(default_factory=list)
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    replayable: bool = True
    # Imported only at type-check time to avoid a models_internal <-
    # representations import cycle.  Runtime values are RepresentationTarget.
    target: "RepresentationTarget | None" = None
    expected_content_sha256: str | None = None
    expected_after_sha256: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    safety: Literal["auto_safe", "review_required", "forbidden"] = "forbidden"

    def __post_init__(self) -> None:
        hashes = (self.expected_content_sha256, self.expected_after_sha256)
        if self.target is None and any(value is not None for value in hashes):
            raise ValueError("repair proposal hash preconditions require a target")
        if self.target is not None and any(value is None for value in hashes):
            raise ValueError("exact repair target requires before and after hashes")
        for digest in hashes:
            if digest is None:
                continue
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest.lower()
            ):
                raise ValueError("repair proposal hashes must be SHA-256 digests")
        if self.safety not in {"auto_safe", "review_required", "forbidden"}:
            raise ValueError("unsupported repair proposal safety")


@dataclass(frozen=True)
class CapabilityObservation:
    """规则对某项能力观测到的状态（capability matrix 汇总用）。"""

    capability_name: str
    observed_state: QualityCapabilityState
    evidence_refs: list[EvidenceRef] = field(default_factory=list)


@dataclass(frozen=True)
class RuleResult:
    """一条规则的完整输出；空元组表示该规则无发现。"""

    issues: tuple[IssueDraft, ...] = ()
    relation_candidates: tuple[RelationCandidate, ...] = ()
    binding_candidates: tuple[BindingCandidate, ...] = ()
    repair_proposals: tuple[RepairProposal, ...] = ()
    capability_observations: tuple[CapabilityObservation, ...] = ()
