"""单文档质量修复 Agent 的 Prompt 模板和默认行为约束。"""

from __future__ import annotations

from collections.abc import Sequence

from quality.agent.models import CandidateValidation

PROMPT_VERSION = "quality-repair-v2"

DEFAULT_REPAIR_INSTRUCTIONS: tuple[str, ...] = (
    "你是单文档质量修复 Agent，只修复 Markdown 的格式或结构，不改变事实内容。",
    "先阅读 document_index 了解全篇结构，再按稳定 ID 使用只读工具查看必要证据。",
    "先使用只读工具查看必要证据，再提交 RepairedDocumentCandidate。",
    "优先输出最小范围的 operations；block_markdown 仅用于兼容旧候选。",
    "不要直接调用 commit_revision；候选必须先经过本地验证。",
    "不得修改数字、单位、日期、公式、代码、URL、稳定 ID、页码、bbox 或来源定位。",
    "如果没有明确问题，返回原 Markdown、change_kind=none、空 affected_ids，并说明原因。",
    "所有回答必须是符合 schema 的合法 json 对象。",
)


def render_repair_prompt(
    *,
    revision_id: str,
    document_id: str,
    filename: str,
    markdown: str,
    block_summaries: Sequence[str],
    feedback: CandidateValidation | None = None,
    focus_page: int | None = None,
    document_index: str = "",
    max_chars: int = 12000,
) -> str:
    """渲染一次 Agent run 的用户 Prompt。

    通过 ``max_chars`` 做最终边界控制；段落顺序保证文档身份和任务约束
    优先于大段内容，验证反馈放在正文前，避免长文档截断时丢失反馈。
    """

    feedback_text = ""
    if feedback is not None:
        feedback_text = (
            "<validation_feedback>\n"
            "上一轮候选未通过验证。只修复以下反馈涉及的问题，不要扩大修改范围：\n"
            f"{feedback.model_dump_json(indent=2)}\n"
            "</validation_feedback>\n"
        )

    block_text = "\n".join(block_summaries)
    prefix = (
        f"<quality_repair_prompt version=\"{PROMPT_VERSION}\">\n"
        "<task>\n"
        "根据文档证据检查格式和结构问题，返回 RepairedDocumentCandidate。\n"
        "候选的 base_revision 必须等于当前 revision，lineage 必须包含该 revision。\n"
        "只能改变格式或结构，不能改变事实内容。\n"
        "operations 只能作用于已有 block/table ID，且必须带 evidence_refs。\n"
        "</task>\n"
        f"<document_id>{document_id}</document_id>\n"
        f"<filename>{filename}</filename>\n"
        f"<base_revision>{revision_id}</base_revision>\n"
        f"<focus_page>{focus_page if focus_page is not None else 'document'}</focus_page>\n"
        f"{feedback_text}"
        "<context>\n<document_index>\n"
        f"{document_index}\n"
        "</document_index>\n<block_summaries>\n"
    )
    context_text = (
        f"{block_text}\n"
        "</block_summaries>\n<current_markdown>\n"
        f"{markdown}\n"
        "</current_markdown>\n</context>\n"
    )
    suffix = (
        "<output>请返回合法 json 对象，不要返回 Markdown 代码围栏或额外解释。</output>\n"
        "</quality_repair_prompt>"
    )
    available = max_chars - len(prefix) - len(suffix)
    if available <= 0:
        # Preserve identity fields even when an intentionally tiny budget cannot
        # hold the full task/context body.
        compact_prefix = (
            f'<quality_repair_prompt version="{PROMPT_VERSION}">\n'
            f"<document_id>{document_id}</document_id>\n"
            f"<base_revision>{revision_id}</base_revision>\n"
        )
        prefix_budget = max(0, max_chars - len(suffix))
        compact_prefix = compact_prefix[:prefix_budget]
        return compact_prefix + suffix[:max_chars - len(compact_prefix)]
    if len(context_text) > available:
        marker = "\n[context truncated]"
        # Keep truncation explicit so a partial block/Markdown fragment is not
        # mistaken for the complete document.
        if available <= len(marker):
            context_text = marker[:available]
        else:
            context_text = context_text[: available - len(marker)] + marker
    return prefix + context_text + suffix


__all__ = [
    "DEFAULT_REPAIR_INSTRUCTIONS",
    "PROMPT_VERSION",
    "render_repair_prompt",
]
