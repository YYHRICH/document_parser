"""质量层：证据驱动的质量检查、安全修复、关系绑定、质量准入与四件套。

入口：``run_quality(parsed_document) -> QualityPackage``（M1 实现）。
内部结构：rules（检查规则）、repairs（白名单修复）、gates（状态判定）、
builders（canonical/输出构建）、packaging（落盘）、llm（可选顾问）。
"""

from quality.api import QualityPipelineNotImplemented, run_quality, write_quality_package
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
    "QualityPipelineNotImplemented",
    "run_quality",
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
