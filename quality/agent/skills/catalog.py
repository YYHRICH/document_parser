"""加载与组合质量修复 Skill 文本，不承担文档修改。"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
DEFAULT_SKILL_IDS = ("document_quality_repair",)

_SKILL_FILES = {
    "document_quality_repair": "document_quality_repair.md",
    "reading_order": "reading_order.md",
    "heading_structure": "heading_structure.md",
    "table_structure": "table_structure.md",
    "markdown_format": "markdown_format.md",
    "reference_structure": "reference_structure.md",
    "asset_formula_layout": "asset_formula_layout.md",
    "cross_page_structure": "cross_page_structure.md",
    "completeness": "completeness.md",
}


def available_skill_ids() -> tuple[str, ...]:
    return tuple(_SKILL_FILES)


def load_skill(skill_id: str) -> str:
    filename = _SKILL_FILES.get(skill_id)
    if filename is None:
        raise ValueError(f"未知质量修复 Skill: {skill_id}")
    return (SKILL_DIR / filename).read_text(encoding="utf-8")


def render_skills(skill_ids: Iterable[str] = DEFAULT_SKILL_IDS) -> str:
    """按稳定顺序合并 Skill，供 Agent instructions 使用。"""

    selected = tuple(dict.fromkeys(skill_ids))
    chunks = []
    for skill_id in selected:
        chunks.append(
            f'<quality_skill id="{skill_id}">\n'
            f"{load_skill(skill_id)}\n"
            "</quality_skill>"
        )
    return "\n\n".join(chunks)


__all__ = ["DEFAULT_SKILL_IDS", "available_skill_ids", "load_skill", "render_skills"]
