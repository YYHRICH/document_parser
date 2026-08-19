"""Agno 运行时适配器；不把 Agno 类型泄漏到质量层内部契约。"""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
import json
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

    def __init__(self, content: str, *, reason: str = "invalid_candidate") -> None:
        encoded = content.encode("utf-8", errors="replace")
        self.content_length = len(content)
        self.content_sha256 = sha256(encoded).hexdigest()
        self.reason = reason
        super().__init__(
            "Agno 未返回结构化候选"
            f"（reason={reason}, length={self.content_length}, "
            f"sha256={self.content_sha256}）。"
        )


def _strip_json_fence(content: str) -> str:
    """剥离唯一一层 JSON Markdown 围栏；不吞掉其他尾部文本。"""

    stripped = content.strip()
    fence = chr(96) * 3
    if not stripped.startswith(fence):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 3 or lines[-1].strip() != fence:
        return stripped
    if lines[0].strip().lower() not in {fence, fence + "json"}:
        return stripped
    return "\n".join(lines[1:-1]).strip()


def _decode_candidate_content(content: Any) -> RepairedDocumentCandidate:
    """把 Agno 原始响应转换成一个且仅一个候选对象。

    不从多个 JSON 响应中擅自挑选第一个，也不截断尾部解释文本；
    这些情况必须反馈给 Agent 重试。
    """

    if isinstance(content, RepairedDocumentCandidate):
        return content
    if not isinstance(content, str):
        try:
            return RepairedDocumentCandidate.model_validate(content)
        except Exception as exc:
            # Do not hash or log arbitrary provider objects; retain only their
            # type so the runtime can distinguish this from malformed JSON.
            content_type = f"{type(content).__module__}.{type(content).__name__}"
            raise CandidateSchemaError(
                f"<non-string-content:{content_type}>",
                reason="non_string_content",
            ) from exc

    raw = _strip_json_fence(content)
    decoder = json.JSONDecoder()
    try:
        payload, end = decoder.raw_decode(raw)
    except json.JSONDecodeError as exc:
        raise CandidateSchemaError(raw, reason="malformed_json") from exc
    trailing = raw[end:].strip()
    if trailing:
        reason = (
            "multiple_json_objects"
            if trailing.startswith(("{", "["))
            else "trailing_text"
        )
        raise CandidateSchemaError(raw, reason=reason)
    if not isinstance(payload, dict):
        raise CandidateSchemaError(raw, reason="json_not_object")
    try:
        return RepairedDocumentCandidate.model_validate(payload)
    except Exception as exc:
        raise CandidateSchemaError(raw, reason="schema_validation") from exc


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
            # DeepSeek 的 OpenAI-compatible endpoint 支持 json_object，
            # 不支持 OpenAI 专有 json_schema。Schema 已经通过 prompt 和
            # few-shot 明确给出；不再把 output_schema 交给 Agno，避免工具
            # 调用的中间响应被 Agno 当成最终 Pydantic 输出转换。
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
        )
        content = getattr(response, "content", response)
        return _decode_candidate_content(content)


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
