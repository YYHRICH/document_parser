"""跨页续表与列漂移规则（QL-TBL-007/008，spec §5.3.5）。"""

from __future__ import annotations

import re

from quality.contracts import IssueSeverity, QualityCapabilityState

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

_CONTINUATION_HINT = re.compile(r"续|continued|continuation|cont\.", re.IGNORECASE)


def _normalized_headers(table) -> list[str]:
    """规范化 header path 序列（保留列顺序和重复路径）。"""
    analysis = analyze_grid(table)
    if not analysis.valid:
        return []
    paths: list[str] = []
    for col in range(table.num_cols or 0):
        segments: list[str] = []
        for row in analysis.header_rows:
            covering = [
                c for c in table.cells
                if c.start_row == row
                and c.start_col <= col < c.start_col + c.col_span
            ]
            if len(covering) == 1 and covering[0].text.strip():
                segments.append(re.sub(r"\s+", "", covering[0].text))
        paths.append("/".join(segments))
    return paths


def _table_order(context: EvidenceContext, table) -> int | None:
    block = context.block(str(table.block_id))
    return block.order_index if block else None


def _adjacent_pairs(context: EvidenceContext):
    """只返回页码已知且在阅读顺序中相邻的跨页表格。"""
    tables = sorted(
        context.parsed.tables,
        key=lambda t: (_table_order(context, t) if _table_order(context, t) is not None else 10**12, str(t.block_id), t.table_id),
    )
    for a, b in zip(tables, tables[1:]):
        if a.page_number is None or b.page_number is None:
            continue
        if b.page_number != a.page_number + 1:
            continue
        order_a, order_b = _table_order(context, a), _table_order(context, b)
        if order_a is None or order_b is None or order_b <= order_a:
            continue
        yield a, b


def _continuation_hint(context: EvidenceContext, table_a, table_b) -> bool:
    """Read continuation signals from table-level evidence only.

    Scanning flattened table body text is unsafe: an ordinary cell may mention
    “跨页” as business content and turn two unrelated adjacent tables into a
    false continuation pair. Header cells, captions, and explicit metadata are
    structural evidence and remain safe to inspect.
    """
    values: list[str] = [table_a.caption or "", table_b.caption or ""]
    for table in (table_a, table_b):
        values.extend(
            str(value)
            for key, value in table.metadata.items()
            if any(token in str(key).lower() for token in ("caption", "title", "continu", "续", "标题"))
        )
        analysis = analyze_grid(table)
        if analysis.valid:
            values.extend(
                cell.text
                for cell in table.cells
                if cell.column_header
            )
        block = context.block(str(table.block_id))
        if block:
            values.extend(
                str(value)
                for key, value in block.metadata.items()
                if any(token in str(key).lower() for token in ("caption", "title", "continu", "续", "标题"))
            )
    return bool(_CONTINUATION_HINT.search(" ".join(values)))


def _position_evidence(table_a, table_b, hint: bool) -> bool:
    """没有页面尺寸时，至少要求 continuation 标记或两侧真实表级 bbox。"""
    return hint or (table_a.bbox is not None and table_b.bbox is not None)


def _continuation_candidate(context: EvidenceContext, table_a, table_b, headers_a, headers_b) -> bool:
    """Only compare adjacent tables when there is evidence they may be one table."""
    if not headers_a or not headers_b:
        return False
    if _continuation_hint(context, table_a, table_b):
        return True
    if headers_a == headers_b:
        return True
    return len(set(headers_a) & set(headers_b)) >= 2


def _column_geometry(table) -> list[tuple[float, float]] | None:
    """返回各列 header bbox 的归一化中心/宽度；缺失时返回 None。"""
    if table.bbox is None or table.bbox[2] <= table.bbox[0]:
        return None
    analysis = analyze_grid(table)
    if not analysis.valid:
        return None
    left, _, right, _ = table.bbox
    width = right - left
    result: list[tuple[float, float]] = []
    for col in range(table.num_cols or 0):
        cells = [
            c for c in table.cells
            if c.column_header
            and c.start_col <= col < c.start_col + c.col_span
            and c.bbox is not None
        ]
        if not cells:
            return None
        cell = sorted(cells, key=lambda c: (c.start_row, c.start_col))[-1]
        c_left, _, c_right, _ = cell.bbox
        result.append((((c_left + c_right) / 2 - left) / width, (c_right - c_left) / width))
    return result


def _geometry_drift(table_a, table_b) -> bool | None:
    ga, gb = _column_geometry(table_a), _column_geometry(table_b)
    if ga is None or gb is None or len(ga) != len(gb):
        return None
    return any(abs(a - b) > 0.12 for pair_a, pair_b in zip(ga, gb) for a, b in zip(pair_a, pair_b))


def _pair_evidence(table_a, table_b, headers_a, headers_b, hint, drift) -> dict:
    return {
        "table_ids": [table_a.table_id, table_b.table_id],
        "page_numbers": [table_a.page_number, table_b.page_number],
        "header_paths": [headers_a, headers_b],
        "column_count": [table_a.num_cols, table_b.num_cols],
        "continuation_hint": hint,
        "column_geometry_drift": drift,
    }


class QL_TBL_007_CrossPageContinuation(QualityRule):
    """跨页续表候选识别；跨页关系与页内 binding 独立降级。"""

    rule_id = "QL-TBL-007"
    required_evidence = (
        EvidenceRequirement(kind="tables", required_state="available"),
        EvidenceRequirement(kind="table_cells", required_state="partial_allowed"),
        EvidenceRequirement(kind="table_bbox", required_state="partial_allowed"),
    )

    def execute(self, context: EvidenceContext) -> RuleResult:
        candidates: list[RelationCandidate] = []
        issues: list[IssueDraft] = []
        for table_a, table_b in _adjacent_pairs(context):
            headers_a = _normalized_headers(table_a)
            headers_b = _normalized_headers(table_b)
            if not headers_a or not headers_b:
                continue
            cols_a = table_a.num_cols or len(headers_a)
            cols_b = table_b.num_cols or len(headers_b)
            if cols_a != cols_b:
                continue
            exact = headers_a == headers_b
            hint = _continuation_hint(context, table_a, table_b)
            position_ok = _position_evidence(table_a, table_b, hint)
            drift = _geometry_drift(table_a, table_b)
            order_conflict = bool(context.duplicate_order_indices)
            block_a = context.block(str(table_a.block_id))
            block_b = context.block(str(table_b.block_id))
            if not _continuation_candidate(context, table_a, table_b, headers_a, headers_b):
                continue
            state = QualityCapabilityState.VERIFIED
            if (
                not exact
                or not position_ok
                or drift is True
                or order_conflict
                or block_a is None
                or block_b is None
                or not block_a.source_block_id
                or not block_b.source_block_id
            ):
                state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                issues.append(IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="cross_page_table",
                    message=(
                        f"跨页续表需要人工复核: {table_a.table_id}(p{table_a.page_number}) → "
                        f"{table_b.table_id}(p{table_b.page_number})。"
                    ),
                    affected_block_ids=[str(table_a.block_id), str(table_b.block_id)],
                    evidence={"table_ids": [table_a.table_id, table_b.table_id], "header_paths": [headers_a, headers_b]},
                ))
            evidence = _pair_evidence(table_a, table_b, headers_a, headers_b, hint, drift)
            if block_a is None or block_b is None:
                continue
            candidates.append(RelationCandidate(
                relation_type="table_continuation",
                from_id=str(block_a.id),
                to_id=str(block_b.id),
                state=state,
                marker_key=f"{table_a.table_id}->{table_b.table_id}",
                evidence=evidence,
                evidence_refs=[
                    EvidenceRef(object_type="table", object_id=table_a.table_id, field_path="cells"),
                    EvidenceRef(object_type="table", object_id=table_b.table_id, field_path="cells"),
                    EvidenceRef(object_type="table", object_id=table_a.table_id, field_path="page_number"),
                    EvidenceRef(object_type="table", object_id=table_b.table_id, field_path="page_number"),
                    EvidenceRef(object_type="table", object_id=table_a.table_id, field_path="bbox"),
                    EvidenceRef(object_type="table", object_id=table_b.table_id, field_path="bbox"),
                ],
            ))
        observations: list[CapabilityObservation] = []
        if candidates:
            verified = sum(c.state == QualityCapabilityState.VERIFIED for c in candidates)
            observations.append(CapabilityObservation(
                capability_name="cross_page_continuation",
                observed_state=(QualityCapabilityState.VERIFIED if verified == len(candidates) else QualityCapabilityState.MANUAL_REVIEW_REQUIRED),
            ))
        return RuleResult(issues=tuple(issues), relation_candidates=tuple(candidates), capability_observations=tuple(observations))


class QL_TBL_008_ColumnDrift(QualityRule):
    """跨页列数、顺序和列几何漂移检测。"""

    rule_id = "QL-TBL-008"
    required_evidence = QL_TBL_007_CrossPageContinuation.required_evidence

    def execute(self, context: EvidenceContext) -> RuleResult:
        issues: list[IssueDraft] = []
        pairs_seen = 0
        for table_a, table_b in _adjacent_pairs(context):
            headers_a = _normalized_headers(table_a)
            headers_b = _normalized_headers(table_b)
            if not headers_a or not headers_b:
                continue
            if not _continuation_candidate(context, table_a, table_b, headers_a, headers_b):
                continue
            pairs_seen += 1
            cols_a = table_a.num_cols or len(headers_a)
            cols_b = table_b.num_cols or len(headers_b)
            drift_reasons: list[str] = []
            if cols_a != cols_b:
                drift_reasons.append("column_count")
            elif headers_a != headers_b:
                drift_reasons.append("column_order_or_header")
            geometry_drift = _geometry_drift(table_a, table_b)
            if geometry_drift is True:
                drift_reasons.append("column_bbox")
            if drift_reasons:
                issues.append(IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="column_drift",
                    message=(
                        f"跨页表格列结构漂移: {table_a.table_id} → {table_b.table_id}；"
                        f"原因={', '.join(drift_reasons)}。"
                    ),
                    affected_block_ids=[str(table_a.block_id), str(table_b.block_id)],
                    evidence=_pair_evidence(table_a, table_b, headers_a, headers_b, _continuation_hint(context, table_a, table_b), geometry_drift),
                ))
        observations = ()
        if issues or pairs_seen:
            observations = (CapabilityObservation(
                capability_name="table_column_drift_reliable",
                observed_state=(QualityCapabilityState.MANUAL_REVIEW_REQUIRED if issues else QualityCapabilityState.VERIFIED),
            ),)
        return RuleResult(issues=tuple(issues), capability_observations=observations)
