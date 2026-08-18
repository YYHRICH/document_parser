"""质量层：证据驱动的质量检查、安全修复、关系绑定、质量准入与四件套。

正式入口：``run_quality_repair(parsed_document, agent_factory=...) -> QualityPackage``。
入口层为每个文档创建唯一 toolbox；直接传 ``agent`` 仅用于测试或已组装的适配场景。
``run_quality`` 只用于显式确定性维护/测试；rules、repairs、gates、builders
和packaging 通过 Agent toolbox 提供安全服务。
"""

from quality.agent.runtime import QualityAgentNotConfigured
from quality.api import (
    run_quality,
    run_quality_repair,
    write_quality_package,
)
from quality.config import GateConfig, QualityConfig
from quality.ids import binding_id, block_id, issue_id, relation_id, stable_id
from quality.models_internal import (
    BindingCandidate,
    CapabilityObservation,
    EvidenceRef,
    IssueDraft,
    RelationCandidate,
    RepairProposal,
    RuleResult,
)

__all__ = [
    "QualityAgentNotConfigured",
    "run_quality",
    "run_quality_repair",
    "write_quality_package",
    "GateConfig",
    "QualityConfig",
    "stable_id",
    "binding_id",
    "block_id",
    "issue_id",
    "relation_id",
    "BindingCandidate",
    "CapabilityObservation",
    "EvidenceRef",
    "IssueDraft",
    "RelationCandidate",
    "RepairProposal",
    "RuleResult",
]
