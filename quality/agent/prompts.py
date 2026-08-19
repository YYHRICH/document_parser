"""单文档质量修复 Agent 的 Prompt 模板和默认行为约束。"""

from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
import json
from typing import Any

from quality.agent.models import CandidateValidation

PROMPT_VERSION = "quality-repair-v3-few-shot"

DEFAULT_REPAIR_INSTRUCTIONS: tuple[str, ...] = (
    "你是单文档质量修复 Agent，只修复 Markdown 的格式或结构，不改变事实内容。",
    "先阅读 document_index 了解全篇结构，再按稳定 ID 使用只读工具查看必要证据。",
    "先使用只读工具查看必要证据，再提交 RepairedDocumentCandidate。",
    "优先输出最小范围的 operations；block_markdown 仅用于兼容旧候选。",
    "单个候选最多提交 8 个 operations；问题较多时按页或局部分批，只提交当前证据最充分的一小批。",
    "不要在一次工具调用中提交整篇标题或表格修复，保持候选 JSON 紧凑，避免工具参数截断。",
    "单个候选最多提交 8 个 operations；问题较多时按页或局部分批，只提交当前证据最充分的一小批。",
    "不要在一次工具调用中提交整篇标题或表格修复，保持候选 JSON 紧凑，避免工具参数截断。",
    "表格只提交 update_table_cell_layout 的 cell_layout_patches，不要提交单元格正文；宿主会保留原文本。",
    "不要主动提交整篇 repaired_markdown；根 Markdown 由宿主根据 block operations 投影生成。",
    "不要直接调用 commit_revision；候选必须先经过本地验证。",
    "不得修改数字、单位、日期、公式、代码、URL、稳定 ID、页码、bbox 或来源定位。",
    "只处理 quality_diagnostics 中有证据且允许由结构 Patch 修复的问题。",
    "affected_ids、affected_relation_keys、affected_asset_paths 可以留空，由宿主根据 operations 的实际差异规范化。",
    "如果没有明确可修问题，返回 repaired_markdown=null、change_kind=none、空 operations 和空 affected_ids，并说明原因。",
    "所有回答必须是符合 schema 的合法 json 对象。",
)


def _render_few_shot_examples(revision_id: str) -> str:
    """渲染面向真实修复场景的紧凑 few-shot。"""

    return (
        "示例中的 ID 仅用于说明格式；实际输出必须替换为上下文中已有的稳定 ID。\n"
        '<example name="heading_patch">\n'
        'input: quality_diagnostics={"issues":[{"category":"heading_level_mismatch","page":2,"block_id":"example-heading-id"}]}\n'
        'block_summary={"id":"example-heading-id","kind":"heading","markdown":"### 2 方法","heading_level":3}\n'
        "output: {"
        f'"base_revision":"{revision_id}","scope":"page","scope_pages":[2],'
        '"operations":[{"operation":"update_heading_level","block_id":"example-heading-id","heading_level":2}],'
        '"affected_ids":[],"evidence_refs":[{"object_type":"block","object_id":"example-heading-id","field_path":"heading_level"}],'
        '"change_kind":"structure","reasoning":"只按已有编号和标题证据修复层级，不改标题文字。","confidence":0.95}\n'
        "</example>\n"
        '<example name="formula_parser_loss_noop">\n'
        'input: quality_diagnostics={"issues":[{"category":"formula_placeholder","page":3,"block_id":"example-formula-id"}]}\n'
        'block_summary={"id":"example-formula-id","markdown":"[[FORMULA_UNAVAILABLE]]","native_formula":null}\n'
        "output: {"
        f'"base_revision":"{revision_id}","lineage":["{revision_id}"],'
        '"operations":[],"affected_ids":[],"evidence_refs":[],"change_kind":"none",'
        '"reasoning":"解析器没有提供可验证的原始公式，不能猜测或伪造公式；保留占位符并交给下游标记。","confidence":0.99}\n'
        "</example>\n"
        '<example name="table_layout_only">\n'
        'input: quality_diagnostics={"issues":[{"category":"table_grid_gap","page":4,"table_id":"example-table-id","cell_index":2}]}\n'
        'table_summary={"id":"example-table-id","cell_index":2,"text_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}\n'
        "output: {"
        f'"base_revision":"{revision_id}","lineage":["{revision_id}"],'
        '"operations":[{"operation":"update_table_cell_layout","table_id":"example-table-id","cell_layout_patches":[{"cell_index":2,"start_row":1,"start_col":1,"row_span":1,"col_span":1,"expected_text_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}]}],'
        '"affected_ids":[],"evidence_refs":[{"object_type":"table","object_id":"example-table-id","field_path":"cells[2].grid"}],'
        '"change_kind":"structure","reasoning":"只修复表格网格坐标，保留宿主中的单元格正文。","confidence":0.9}\n'
        "</example>\n"
        '<example name="schema_retry">\n'
        'input: validation_feedback={"code":"candidate_schema_error","errors":["候选 lineage 必须包含 base_revision"]}\n'
        "output: {"
        f'"base_revision":"{revision_id}","lineage":["{revision_id}"],'
        '"operations":[],"affected_ids":[],"evidence_refs":[],"change_kind":"none",'
        '"reasoning":"已按验证反馈补齐当前 revision 的 base_revision 和 lineage；没有其他可安全修复的问题。","confidence":0.99}\n'
        "</example>"
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
    quality_diagnostics: Mapping[str, Any] | None = None,
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
    diagnostics_text = json.dumps(
        dict(quality_diagnostics or {}),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    prefix = (
        f"<quality_repair_prompt version=\"{PROMPT_VERSION}\">\n"
        "<task>\n"
        "根据文档证据检查格式和结构问题，返回 RepairedDocumentCandidate。\n"
        "候选的 base_revision 必须等于当前 revision，lineage 必须包含该 revision。\n"
        "只能改变格式或结构，不能改变事实内容。\n"
        "operations 只能作用于已有 block/table ID，且必须带 evidence_refs。\n"
        "单个候选最多包含 8 个 operations；问题较多时按页或局部分批提交。\n"
        "单个候选最多包含 8 个 operations；问题较多时按页或局部分批提交。\n"
        "affected 声明字段可以为空，宿主会从实际 Patch 自动推导。\n"
        "</task>\n"
        f"<document_id>{document_id}</document_id>\n"
        f"<filename>{filename}</filename>\n"
        f"<base_revision>{revision_id}</base_revision>\n"
        f"<focus_page>{focus_page if focus_page is not None else 'document'}</focus_page>\n"
        f"{feedback_text}"
        "<quality_diagnostics>\n"
        f"{diagnostics_text}\n"
        "</quality_diagnostics>\n"
        "<few_shot_examples>\n"
        f"{_render_few_shot_examples(revision_id)}\n"
        "</few_shot_examples>\n"
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
