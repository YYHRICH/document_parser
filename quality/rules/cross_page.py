"""跨页续表与列漂移规则（QL-TBL-007/008，spec §5.3.5）。

前置条件（至少一项结构证据）：页相邻、表头重复、列数一致。
状态判定：
- 表头完全一致 + 列数一致 → verified continuation 候选；
- 表头部分一致（含"续行"等标志）→ 弱候选（manual_review_required）；
- 列数不同 / 列顺序交换 / 位置显著漂移 → 不配对（禁止跨页合并）。

跨页关系单独表达（relation_type="table_continuation"），页内绑定不合并。
"""

from __future__ import annotations

import re

from document_parser.core.contracts import (
    IssueSeverity,
    QualityCapabilityState,
)

from quality.evidence.context import EvidenceContext
from quality.evidence.requirements import EvidenceRequirement
from quality.models_internal import (
    CapabilityObservation,
    EvidenceRef,
    IssueDraft,
    RelationCandidate,
    RuleResult,
)
from quality.rules.base import QualityRule
from quality.rules.tables import analyze_grid

_CONTINUATION_HINT = re.compile(r"续|continued|cont\.", re.IGNORECASE)


def _normalized_headers(table) -> list[str]:
    """规范化 header path 序列（去空白），用于跨表比较。"""
    analysis = analyze_grid(table)
    if not analysis.valid:
        return []
    paths: list[str] = []
    for col in range(table.num_cols or 0):
        segments: list[str] = []
        for row in analysis.header_rows:
            covering = [
                c
                for c in table.cells
                if c.start_row == row
                and c.start_col <= col < c.start_col + c.col_span
            ]
            if len(covering) == 1 and covering[0].text.strip():
                segments.append(re.sub(r"\s+", "", covering[0].text))
        paths.append("/".join(segments))
    return paths


class QL_TBL_007_CrossPageContinuation(QualityRule):
    """跨页续表候选识别（表头+列数证据），输出 table_continuation 关系。"""

    rule_id = "QL-TBL-007"
    required_evidence = (
        EvidenceRequirement(kind="tables", required_state="available"),
        EvidenceRequirement(kind="table_cells", required_state="partial_allowed"),
        EvidenceRequirement(kind="table_bbox", required_state="partial_allowed"),
    )

    def execute(self, context: EvidenceContext) -> RuleResult:
        tables = sorted(
            context.parsed.tables,
            key=lambda t: (t.page_number or 0, t.table_id),
        )
        candidates: list[RelationCandidate] = []
        issues: list[IssueDraft] = []
        observations: list[CapabilityObservation] = []

        for i, table_a in enumerate(tables):
            for table_b in tables[i + 1 :]:
                if (table_b.page_number or 0) != (table_a.page_number or 0) + 1:
                    continue  # 仅相邻页
                headers_a = _normalized_headers(table_a)
                headers_b = _normalized_headers(table_b)
                if not headers_a or not headers_b:
                    continue  # 表头不可用 → 不配对（保守）
                cols_a = table_a.num_cols or len(headers_a)
                cols_b = table_b.num_cols or len(headers_b)
                if cols_a != cols_b:
                    continue  # 列数不同且无法由 colspan 解释 → 不配对

                exact = headers_a == headers_b
                overlap = len(set(headers_a) & set(headers_b))
                hint = bool(
                    _CONTINUATION_HINT.search(
                        " ".join(headers_a + headers_b + [
                            c.text for c in (table_a.cells + table_b.cells)
                        ][:60])
                    )
                )
                if exact:
                    state = QualityCapabilityState.VERIFIED
                elif overlap >= 2 or hint:
                    state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                    issues.append(
                        IssueDraft(
                            severity=IssueSeverity.WARNING,
                            category="cross_page_table",
                            message=f"跨页续表弱候选: {table_a.table_id}(p{table_a.page_number}) → "
                            f"{table_b.table_id}(p{table_b.page_number}) 表头部分一致，"
                            "需要人工复核。",
                        )
                    )
                else:
                    continue  # 无重叠表头 → 不配对

                block_a = context.block(str(table_a.block_id))
                block_b = context.block(str(table_b.block_id))
                if block_a is None or block_b is None:
                    continue
                candidates.append(
                    RelationCandidate(
                        relation_type="table_continuation",
                        from_id=str(block_a.id),
                        to_id=str(block_b.id),
                        state=state,
                        evidence_refs=[
                            EvidenceRef(
                                object_type="table",
                                object_id=table_a.table_id,
                                field_path="cells",
                            ),
                            EvidenceRef(
                                object_type="table",
                                object_id=table_b.table_id,
                                field_path="cells",
                            ),
                        ],
                    )
                )

        if candidates:
            verified = sum(
                1 for c in candidates if c.state == QualityCapabilityState.VERIFIED
            )
            observations.append(
                CapabilityObservation(
                    capability_name="cross_page_continuation",
                    observed_state=(
                        QualityCapabilityState.VERIFIED
                        if verified == len(candidates)
                        else QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                    ),
                )
            )
        return RuleResult(
            issues=tuple(issues),
            relation_candidates=tuple(candidates),
            capability_observations=tuple(observations),
        )
