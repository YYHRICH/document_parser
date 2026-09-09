"""质量子域：证据驱动的质量检查、安全修复、关系绑定与质量准入。

入口：``run_pipeline(parsed_document) -> QualityPackage``。
结构：rules（检查规则）、repairs（白名单修复）、gates（状态判定）、
builders（canonical 构建）、hashing（摘要）。
落盘（packaging）属于 infra 层。
"""

from .config import GateConfig, QualityConfig
from .ids import binding_id, block_id, issue_id, relation_id, stable_id
from .models_internal import (
    BindingCandidate,
    CapabilityObservation,
    EvidenceRef,
    IssueDraft,
    RelationCandidate,
    RepairProposal,
    RuleResult,
)
from .pipeline import run_pipeline

__all__ = [
    "run_pipeline",
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
