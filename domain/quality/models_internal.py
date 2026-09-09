"""质量层内部不可变模型（规则之间传递用，不进入公共契约）。

规则只产出 ``RuleResult``（observations/candidates/proposals），
不得直接修改文档、写文件或指定最终 Gate 状态（唯一 Gate evaluator 决策，
见 gates/evaluator.py）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from document_parser.domain.model.contracts import (
    CanonicalSourceLocator,
    IssueSeverity,
    IssueStatus,
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

    ``value_sha256`` 用于检测 LLM/缓存引用的证据是否已变化（LLM 层使用）。
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
    rule_id: str = ""
    status: IssueStatus = IssueStatus.UNFIXED
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
    row_path: list[str] = field(default_factory=list)
    row_cell_ids: list[str] = field(default_factory=list)
    column_cell_ids: list[str] = field(default_factory=list)
    value_cell_id: str | None = None
    cell_key: str = ""
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RepairProposal:
    """白名单修复提案（规则提出，repairs 层校验后应用）。"""

    rule_id: str
    description: str
    affected_block_ids: list[str] = field(default_factory=list)
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    replayable: bool = True


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
