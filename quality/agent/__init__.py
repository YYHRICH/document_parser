"""单文档质量修复 Agent。"""

from quality.agent.agno_adapter import (
    QualityRepairAgent,
    build_quality_repair_agent,
)
from quality.agent.fake import FakeRepairAgent
from quality.agent.index import DocumentIndex, PageIndexEntry
from quality.agent.deepseek import (
    DeepSeekConfig,
    LLMConfigurationError,
    build_deepseek_model,
    load_deepseek_config,
)
from quality.agent.prompts import DEFAULT_REPAIR_INSTRUCTIONS, PROMPT_VERSION, render_repair_prompt
from quality.agent.models import (
    CandidateEvidenceRef,
    CandidateValidation,
    RepairOperation,
    RelationPatch,
    RepairedDocumentCandidate,
    TableCellPatch,
)
from quality.agent.revision import DocumentRevision, InMemoryRevisionStore
from quality.agent.skills import DEFAULT_SKILL_IDS, available_skill_ids, load_skill, render_skills
from quality.agent.tools import DocumentReadTools
from quality.agent.tools import QualityToolbox
from quality.agent.runtime import (
    QualityAgentNotConfigured,
    RepairAgentConfig,
    RepairProgressEvent,
    RepairAgentFactory,
    RepairExecution,
    run_repair,
)
from quality.agent.validator import CandidateValidator, content_fingerprint

__all__ = [
    "QualityAgentNotConfigured",
    "build_quality_repair_agent",
    "QualityRepairAgent",
    "QualityToolbox",
    "CandidateEvidenceRef",
    "CandidateValidation",
    "CandidateValidator",
    "RepairOperation",
    "RelationPatch",
    "TableCellPatch",
    "DocumentReadTools",
    "DEFAULT_SKILL_IDS",
    "available_skill_ids",
    "load_skill",
    "render_skills",
    "DocumentIndex",
    "PageIndexEntry",
    "DEFAULT_REPAIR_INSTRUCTIONS",
    "PROMPT_VERSION",
    "render_repair_prompt",
    "DocumentRevision",
    "FakeRepairAgent",
    "InMemoryRevisionStore",
    "RepairAgentConfig",
    "RepairProgressEvent",
    "RepairAgentFactory",
    "RepairExecution",
    "RepairedDocumentCandidate",
    "content_fingerprint",
    "DeepSeekConfig",
    "LLMConfigurationError",
    "build_deepseek_model",
    "load_deepseek_config",
    "run_repair",
]
