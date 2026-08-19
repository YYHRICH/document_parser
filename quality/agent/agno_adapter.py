"""Agno 运行时适配器；不把 Agno 类型泄漏到质量层内部契约。"""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from quality.agent.tools import QualityToolbox

from quality.agent.context import DocumentAgentContext
from quality.agent.models import CandidateValidation, RepairedDocumentCandidate
from quality.agent.prompts import DEFAULT_REPAIR_INSTRUCTIONS
from quality.agent.skills import DEFAULT_SKILL_IDS, render_skills


class CandidateSchemaError(RuntimeError):
    """Agno 返回了无法转换为候选 Schema 的内容。

    异常只携带长度和哈希，不把可能包含文档正文的模型输出带入公共日志。
    """

    def __init__(self, content: str) -> None:
        encoded = content.encode("utf-8", errors="replace")
        self.content_length = len(content)
        self.content_sha256 = sha256(encoded).hexdigest()
        super().__init__(
            "Agno 未返回结构化候选"
            f"（length={self.content_length}, sha256={self.content_sha256}）。"
        )


class QualityRepairAgent:
    """把 Agno Agent.run() 适配为质量层的 Candidate 协议。"""

    def __init__(
        self,
        model: Any,
        *,
        session_id: str | None = None,
        tools: list[Any] | None = None,
        db: Any | None = None,
        instructions: list[str] | None = None,
        skill_ids: Sequence[str] = DEFAULT_SKILL_IDS,
        tool_call_limit: int = 8,
    ) -> None:
        try:
            from agno.agent import Agent
        except ImportError as exc:  # pragma: no cover - 依赖安装缺失时才触发
            raise RuntimeError("Agno 未安装，请先安装 requirements.txt。") from exc

        kwargs: dict[str, Any] = {
            "model": model,
            "tools": tools or [],
            "output_schema": RepairedDocumentCandidate,
            # DeepSeek 的 OpenAI-compatible endpoint 支持 json_object，
            # 不支持 OpenAI 专有 json_schema。显式 JSON mode 会让 Agno
            # 把 Pydantic schema 写入提示词，再在本地完成类型校验。
            "use_json_mode": True,
            "structured_outputs": False,
        }
        if session_id is not None:
            kwargs["session_id"] = session_id
        if db is not None:
            kwargs["db"] = db
        kwargs["instructions"] = [
            *DEFAULT_REPAIR_INSTRUCTIONS,
            render_skills(skill_ids),
            *(instructions or []),
        ]
        kwargs["tool_call_limit"] = tool_call_limit
        self._agent = Agent(**kwargs)
        self.session_id = session_id

    def run(
        self,
        context: DocumentAgentContext,
        *,
        feedback: CandidateValidation | None = None,
    ) -> RepairedDocumentCandidate:
        # feedback is embedded by DocumentAgentContext.to_prompt(); keeping the
        # argument preserves the RepairAgent protocol for supervisors/tests.
        response = self._agent.run(
            context.to_prompt(),
            session_id=self.session_id,
            output_schema=RepairedDocumentCandidate,
        )
        content = getattr(response, "content", response)
        if isinstance(content, RepairedDocumentCandidate):
            return content
        if isinstance(content, str):
            raise CandidateSchemaError(content)
        return RepairedDocumentCandidate.model_validate(content)


def build_quality_repair_agent(
    model: Any,
    toolbox: "QualityToolbox",
    *,
    session_id: str | None = None,
    instructions: list[str] | None = None,
    skill_ids: Sequence[str] = DEFAULT_SKILL_IDS,
) -> QualityRepairAgent:
    """用当前文档 session 的 既有确定性质量能力 toolbox 构建正式 Agno Agent。"""

    return QualityRepairAgent(
        model,
        session_id=session_id,
        tools=toolbox.as_agno_tools(),
        instructions=instructions,
        skill_ids=skill_ids,
    )
