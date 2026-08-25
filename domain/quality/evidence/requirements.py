"""证据需求声明：每条规则声明它需要哪些证据。

规则调度器先读取 ParsedDocument.capabilities 判断证据可用性，
再决定：执行规则 / 以有限证据执行（限制最高状态）/ 跳过（输出 unavailable）。

对应质量输入需求矩阵（docs/quality_input_requirements.md）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EvidenceKind = Literal[
    "blocks",
    "block_anchor",
    "block_order",
    "heading_level",
    "tables",
    "table_cells",
    "table_bbox",
    "ocr_spans",
    "assets",
    "native_artifacts",
    "capabilities",
    "provenance",
]

EvidenceScope = Literal["document", "block", "table", "cell"]


@dataclass(frozen=True)
class EvidenceRequirement:
    """一项证据需求。

    ``required_state``：available=必须完全可用才执行；
    partial_allowed=部分可用时可执行但限制最高状态。
    """

    kind: EvidenceKind
    required_state: Literal["available", "partial_allowed"]
    scope: EvidenceScope = "document"
    purpose: str = ""
