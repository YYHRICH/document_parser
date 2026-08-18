"""表格网格与字段绑定规则（QL-TBL-*，spec §5.3）。

一期（表格结构阶段 1）：
- QL-TBL-001 单元格坐标与 span 合法性
- QL-TBL-002 物理网格占位冲突和空洞检测
- QL-TBL-003 header 区域恢复（含多级表头连续区域）
- QL-TBL-004 多级 column_path 生成（cell identity 去重，不拍平）
- QL-TBL-005 row_key 生成（row_header 优先，首列推断为 inferred）
- QL-TBL-006 binding 来源粒度检查（禁止伪造 cell bbox）

跨页续表与列漂移（QL-TBL-007/008）在二期实现。
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from document_parser.core.contracts import (
    BlockKind,
    CanonicalSourceLocator,
    IssueSeverity,
    ParsedTable,
    QualityCapabilityState,
    TableCell,
)

from quality.evidence.context import EvidenceContext
from quality.evidence.requirements import EvidenceRequirement
from quality.models_internal import (
    BindingCandidate,
    CapabilityObservation,
    EvidenceRef,
    IssueDraft,
    RuleResult,
)
from quality.rules.base import QualityRule


def _cell_identity(cell: TableCell) -> tuple[int, int]:
    """D-09：cell 身份 = (start_row, start_col) 坐标组合。"""
    return (cell.start_row, cell.start_col)


@dataclass
class _GridAnalysis:
    """一张表的网格分析结果。"""

    table: ParsedTable
    issues: list[IssueDraft] = None  # type: ignore[assignment]
    conflict_cells: list[TableCell] = None  # type: ignore[assignment]
    holes: list[tuple[int, int]] = None  # type: ignore[assignment]
    header_rows: list[int] = None  # type: ignore[assignment]
    valid: bool = True

    def __post_init__(self) -> None:
        if self.issues is None:
            self.issues = []
        if self.conflict_cells is None:
            self.conflict_cells = []
        if self.holes is None:
            self.holes = []
        if self.header_rows is None:
            self.header_rows = []


def analyze_grid(table: ParsedTable) -> _GridAnalysis:
    """QL-TBL-001/002/003：网格合法性、占位冲突、header 区域恢复。"""
    analysis = _GridAnalysis(table=table)
    cells = table.cells
    if not cells:
        analysis.valid = False
        analysis.issues.append(
            IssueDraft(
                severity=IssueSeverity.WARNING,
                category="table_grid",
                message="表格没有可用单元格，网格无法恢复。",
            )
        )
        return analysis

    max_row = max(c.start_row + c.row_span for c in cells)
    max_col = max(c.start_col + c.col_span for c in cells)
    declared_rows = table.num_rows if table.num_rows is not None else max_row
    declared_cols = table.num_cols if table.num_cols is not None else max_col

    # QL-TBL-001：坐标/span 合法性
    for cell in cells:
        if cell.start_row < 0 or cell.start_col < 0:
            analysis.issues.append(
                IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="table_grid",
                    message=f"单元格坐标为负: {_cell_identity(cell)}",
                )
            )
            analysis.valid = False
        if (
            cell.start_row + cell.row_span > declared_rows
            or cell.start_col + cell.col_span > declared_cols
        ):
            analysis.issues.append(
                IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="table_grid",
                    message=f"单元格越过声明尺寸: {_cell_identity(cell)} "
                    f"span=({cell.row_span},{cell.col_span}) rows={declared_rows} cols={declared_cols}",
                )
            )
            analysis.valid = False

    # QL-TBL-002：占位冲突与空洞
    occupancy: dict[tuple[int, int], TableCell] = {}
    for cell in cells:
        for row in range(cell.start_row, cell.start_row + cell.row_span):
            for col in range(cell.start_col, cell.start_col + cell.col_span):
                slot = (row, col)
                if slot in occupancy:
                    analysis.conflict_cells.append(cell)
                else:
                    occupancy[slot] = cell
    if analysis.conflict_cells:
        analysis.issues.append(
            IssueDraft(
                severity=IssueSeverity.WARNING,
                category="table_grid",
                message=f"网格占位冲突（{len(analysis.conflict_cells)} 个单元格重叠）。",
            )
        )
        analysis.valid = False
    # 空洞：声明尺寸内未被任何 cell 覆盖的槽位（span 展开后）
    for row in range(declared_rows):
        for col in range(declared_cols):
            if (row, col) not in occupancy:
                analysis.holes.append((row, col))
    # QL-TBL-003：header 区域恢复
    # 1) 有 column_header 标记的连续起始行
    marked_header_rows = sorted({c.start_row for c in cells if c.column_header})
    header_rows: list[int] = []
    if marked_header_rows:
        # header 标记必须从第 0 行开始并连续；否则区域边界不确定。
        expected = 0
        while expected in marked_header_rows:
            header_rows.append(expected)
            expected += 1
        if marked_header_rows[0] != 0 or len(header_rows) != len(marked_header_rows):
            analysis.issues.append(
                IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="table_header_structure",
                    message="column_header 标记不构成从第 0 行开始的连续表头区域。",
                )
            )
            analysis.valid = False
        # 多级表头：header 标记行后紧随的非数据行（无 row_header 标记）
        # ——通过"下一个被 row_header 标记或含数据特征的行"前连续的未标记行判断：
        # 这里保守策略：如果 header 区域第一行存在 colspan>1（多级表头），
        # 将紧随其后的未标记行也纳入 header，直到出现 rowhdr=True 或非空数据行
        if header_rows and any(
            c.col_span > 1 and c.start_row == header_rows[0] for c in cells
        ):
            next_row = header_rows[-1] + 1
            while next_row < declared_rows:
                row_cells = [c for c in cells if c.start_row == next_row]
                if any(c.row_header for c in row_cells):
                    break
                # 表头第二级特征：行内文本均不含数字（数据行必有数值）。
                # 保守方向：宁少勿错——误判只会少 binding，不会产生错误 verified。
                non_empty = [c.text.strip() for c in row_cells if c.text.strip()]
                if non_empty and all(not re.search(r"\d", t) for t in non_empty):
                    header_rows.append(next_row)
                    next_row += 1
                    continue
                break
    else:
        # 2) 无标记：第一行视为表头（保守）
        header_rows = [0] if declared_rows > 0 else []
    analysis.header_rows = header_rows
    # 表头多级结构中，父表头下方的空槽位是合法布局；数据区空洞才是结构缺失。
    data_holes = [h for h in analysis.holes if h[0] > max(header_rows or [0])]
    if data_holes:
        analysis.issues.append(
            IssueDraft(
                severity=IssueSeverity.WARNING,
                category="table_grid",
                message=f"数据区网格存在 {len(data_holes)} 个空洞槽位。",
            )
        )
        analysis.valid = False
    return analysis


def _column_path_for_col(
    table: ParsedTable, col: int, header_rows: list[int]
) -> list[tuple[str, TableCell]] | None:
    """收集覆盖 col 的 header cell 文本与证据（按行序，cell identity 去重）。

    同一 header 行出现多个覆盖 cell → 互斥候选 → 返回 None（不 verified）。
    """
    segments: list[tuple[str, TableCell]] = []
    for row in header_rows:
        covering = [
            c
            for c in table.cells
            if c.start_row == row
            and c.start_col <= col < c.start_col + c.col_span
        ]
        if len(covering) > 1:
            return None  # 同层互斥候选
        if covering:
            cell = covering[0]
            if cell.text.strip():
                segments.append((cell.text.strip(), cell))
    return segments


class QL_TBL_004_ColumnPath(QualityRule):
    """多级 column_path 生成（对每个数据列）。"""

    rule_id = "QL-TBL-004"
    required_evidence = (
        EvidenceRequirement(kind="tables", required_state="available"),
        EvidenceRequirement(kind="table_cells", required_state="partial_allowed"),
    )

    def execute(self, context: EvidenceContext) -> RuleResult:
        issues: list[IssueDraft] = []
        observations: list[CapabilityObservation] = []
        if not context.parsed.tables:
            return RuleResult()
        grid_verified = True
        for table in context.parsed.tables:
            analysis = analyze_grid(table)
            if not analysis.valid:
                grid_verified = False
                issues.extend(analysis.issues)
                continue
            # 验证每个数据列的 column_path 可确定
            for col in range(table.num_cols or 0):
                path = _column_path_for_col(table, col, analysis.header_rows)
                if path is None or not path:
                    issues.append(
                        IssueDraft(
                            severity=IssueSeverity.WARNING,
                            category="table_field_binding",
                            message=f"table {table.table_id} 列 {col} 的 column_path 无法确定（表头互斥或为空）。",
                        )
                    )
                    grid_verified = False
        observations.append(
            CapabilityObservation(
                capability_name="table_grid_reliable",
                observed_state=(
                    QualityCapabilityState.VERIFIED
                    if grid_verified
                    else QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                ),
            )
        )
        return RuleResult(
            issues=tuple(issues),
            capability_observations=tuple(observations),
        )


class QL_TBL_006_BuildBindings(QualityRule):
    """生成 TableFieldBinding 候选（row_key + column_path + value）。"""

    rule_id = "QL-TBL-006"
    required_evidence = (
        EvidenceRequirement(kind="tables", required_state="available"),
        EvidenceRequirement(kind="table_cells", required_state="partial_allowed"),
    )

    def execute(self, context: EvidenceContext) -> RuleResult:
        candidates: list[BindingCandidate] = []
        issues: list[IssueDraft] = []
        observations: list[CapabilityObservation] = []

        for table in context.parsed.tables:
            analysis = analyze_grid(table)
            if not analysis.valid:
                issues.extend(analysis.issues)
                continue
            header_rows = analysis.header_rows
            last_header_row = max(header_rows) if header_rows else -1
            # table.block_id 是 DocumentBlock 的 UUID（对应解析器的 table block）
            block = context.block(str(table.block_id))

            # 先建立每行 row_key，并检测重复；禁止用序号伪造唯一性。
            row_infos: dict[int, tuple[list[TableCell], str, QualityCapabilityState]] = {}
            key_rows: dict[str, list[int]] = {}
            for row in range(last_header_row + 1, table.num_rows or 0):
                row_cells = [c for c in table.cells if c.start_row == row]
                if not row_cells:
                    continue
                row_headers = sorted((c for c in row_cells if c.row_header), key=lambda c: c.start_col)
                first_cell = min(row_cells, key=lambda c: c.start_col)
                sources = row_headers or [first_cell]
                row_key = " / ".join(c.text.strip() for c in sources if c.text.strip())
                if not row_key:
                    continue
                row_key_state = (
                    QualityCapabilityState.VERIFIED
                    if row_headers
                    else QualityCapabilityState.INFERRED
                )
                row_infos[row] = (row_cells, row_key, row_key_state)
                key_rows.setdefault(row_key, []).append(row)
            duplicate_keys = {key for key, rows in key_rows.items() if len(rows) > 1}
            if duplicate_keys:
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="table_field_binding",
                        message=f"row_key 重复，无法唯一定位: {', '.join(sorted(duplicate_keys))}。",
                        affected_block_ids=[str(table.block_id)],
                    )
                )

            for row, (row_cells, row_key, row_key_state) in row_infos.items():
                if row_key in duplicate_keys:
                    row_key_state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED

                # 每个非 header 数据单元格 → binding
                for cell in row_cells:
                    if cell.column_header or cell.row_header:
                        continue
                    if cell.start_row != row:
                        continue
                    path = _column_path_for_col(table, cell.start_col, header_rows)
                    if not path:
                        continue  # path 无法确定 → 不生成（不制造错误绑定）
                    path_text = [text for text, _ in path]
                    # binding 状态：path 全部来自真实 header cell + row_key 状态
                    path_verified = True  # 已通过互斥检查
                    if row_key_state == QualityCapabilityState.MANUAL_REVIEW_REQUIRED:
                        state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                    elif path_verified and row_key_state == QualityCapabilityState.VERIFIED:
                        state = QualityCapabilityState.VERIFIED
                    else:
                        state = QualityCapabilityState.INFERRED
                    if block is None or not block.source_block_id:
                        state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                    if cell.bbox is not None:
                        source_bbox = cell.bbox
                        bbox_granularity = "cell"
                    else:
                        source_bbox = table.bbox
                        bbox_granularity = "table" if table.bbox is not None else None
                    source_locator = CanonicalSourceLocator(
                        source_block_id=block.source_block_id if block else "",
                        page_number=table.page_number,
                        bbox=source_bbox,
                        bbox_granularity=bbox_granularity,
                        table_cell=f"r{row}c{cell.start_col}",
                        provenance_status=state,
                    )
                    path_evidence = [
                        {
                            "cell_id": f"{table.table_id}:r{c.start_row}c{c.start_col}",
                            "text": text,
                            "start_row": c.start_row,
                            "start_col": c.start_col,
                            "row_span": c.row_span,
                            "col_span": c.col_span,
                        }
                        for text, c in path
                    ]
                    candidates.append(
                        BindingCandidate(
                            table_id=table.table_id,
                            block_id=str(table.block_id),
                            row_key=row_key,
                            column_path=path_text,
                            value=cell.text.strip(),
                            source_locator=source_locator,
                            cell_key=f"r{row}c{cell.start_col}",
                            evidence_refs=[
                                EvidenceRef(
                                    object_type="cell",
                                    object_id=f"{table.table_id}:r{row}c{cell.start_col}",
                                    field_path="text",
                                ),
                                *[
                                    EvidenceRef(
                                        object_type="cell",
                                        object_id=f"{table.table_id}:r{c.start_row}c{c.start_col}",
                                        field_path="text",
                                    )
                                    for _, c in path
                                ],
                            ],
                            evidence={
                                "row_key": {
                                    "value": row_key,
                                    "source_cells": [
                                        {
                                            "cell_id": f"{table.table_id}:r{c.start_row}c{c.start_col}",
                                            "start_row": c.start_row,
                                            "start_col": c.start_col,
                                            "row_span": c.row_span,
                                            "col_span": c.col_span,
                                        }
                                        for c in (sorted((c for c in row_cells if c.row_header), key=lambda c: c.start_col) or [min(row_cells, key=lambda c: c.start_col)])
                                    ],
                                },
                                "column_path_segments": path_evidence,
                                "value_cell": {
                                    "cell_id": f"{table.table_id}:r{row}c{cell.start_col}",
                                    "start_row": row,
                                    "start_col": cell.start_col,
                                    "row_span": cell.row_span,
                                    "col_span": cell.col_span,
                                },
                            },
                        )
                    )

        if candidates:
            verified = sum(
                1 for c in candidates if c.source_locator.provenance_status == QualityCapabilityState.VERIFIED
            )
            observations.append(
                CapabilityObservation(
                    capability_name="table_field_binding_reliable",
                    observed_state=(
                        QualityCapabilityState.VERIFIED
                        if verified == len(candidates)
                        else QualityCapabilityState.INFERRED
                    ),
                )
            )
        return RuleResult(
            issues=tuple(issues),
            binding_candidates=tuple(candidates),
            capability_observations=tuple(observations),
        )
