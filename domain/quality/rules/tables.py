"""表格网格与字段绑定规则（QL-TBL-*，spec §5.3）。

- QL-TBL-001 单元格坐标与 span 合法性
- QL-TBL-002 物理网格占位冲突和空洞检测
- QL-TBL-003 header 区域恢复（含多级表头连续区域）
- QL-TBL-004 多级 column_path 生成（cell identity 去重，不拍平）
- QL-TBL-005 row_key 生成（row_header 优先，首列推断为 inferred）
- QL-TBL-006 binding 来源粒度检查（禁止伪造 cell bbox）

跨页续表与列漂移由 QL-TBL-007/008 处理。
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from document_parser.domain.model.contracts import (
    BlockKind,
    CanonicalSourceLocator,
    IssueSeverity,
    IssueStatus,
    ParsedTable,
    QualityCapabilityState,
    TableCell,
    TableSlotKind,
)

from ..evidence.context import EvidenceContext
from ..evidence.requirements import EvidenceRequirement
from ..models_internal import (
    BindingCandidate,
    CapabilityObservation,
    EvidenceRef,
    IssueDraft,
    RuleResult,
)
from ..table_storage import uses_external_table_index
from .base import QualityRule


def _cell_identity(cell: TableCell) -> tuple[int, int]:
    """D-09：cell 身份 = (start_row, start_col) 坐标组合。"""
    return (cell.start_row, cell.start_col)


def _cell_id(table: ParsedTable, cell: TableCell) -> str:
    return cell.cell_id or f"{table.table_id}:r{cell.start_row}c{cell.start_col}"


@dataclass
class _GridAnalysis:
    """一张表的网格分析结果。"""

    table: ParsedTable
    issues: list[IssueDraft] = None  # type: ignore[assignment]
    conflict_cells: list[TableCell] = None  # type: ignore[assignment]
    holes: list[tuple[int, int]] = None  # type: ignore[assignment]
    header_rows: list[int] = None  # type: ignore[assignment]
    title_rows: list[int] = None  # type: ignore[assignment]
    row_header_columns: list[int] = None  # type: ignore[assignment]
    header_inferred: bool = False
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
        if self.title_rows is None:
            self.title_rows = []
        if self.row_header_columns is None:
            self.row_header_columns = []


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
                rule_id="QL-TBL-003",
                message="表格没有可用单元格，网格无法恢复。",
            )
        )
        return analysis

    max_row = max(c.start_row + c.row_span for c in cells)
    max_col = max(c.start_col + c.col_span for c in cells)
    declared_rows = table.num_rows if table.num_rows is not None else max_row
    declared_cols = table.num_cols if table.num_cols is not None else max_col

    cell_ids = [_cell_id(table, cell) for cell in cells]
    if len(cell_ids) != len(set(cell_ids)):
        analysis.issues.append(
            IssueDraft(
                severity=IssueSeverity.WARNING,
                category="table_structure",
                rule_id="QL-TBL-001",
                message=f"table {table.table_id} 存在重复 cell_id。",
                affected_block_ids=[str(table.block_id)],
                evidence={"table_id": table.table_id},
            )
        )
        analysis.valid = False

    # QL-TBL-001：坐标/span 合法性
    for cell in cells:
        if cell.start_row < 0 or cell.start_col < 0:
            analysis.issues.append(
                IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="table_grid",
                    rule_id="QL-TBL-001",
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
                    rule_id="QL-TBL-001",
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
                rule_id="QL-TBL-002",
                message=f"网格占位冲突（{len(analysis.conflict_cells)} 个单元格重叠）。",
            )
        )
        analysis.valid = False

    # 原生逻辑网格存在时，对照 origin/covered 引用，防止 span 虽合法但
    # 覆盖关系在适配过程中丢失或错指。
    if table.grid:
        if len(table.grid) != declared_rows or any(len(row) != declared_cols for row in table.grid):
            analysis.issues.append(
                IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="table_structure",
                    rule_id="QL-TBL-002",
                    message=(
                        f"table {table.table_id} 的逻辑网格尺寸与声明尺寸不一致："
                        f"grid={len(table.grid)}x{max((len(row) for row in table.grid), default=0)}，"
                        f"declared={declared_rows}x{declared_cols}。"
                    ),
                    affected_block_ids=[str(table.block_id)],
                    evidence={"table_id": table.table_id},
                )
            )
            analysis.valid = False
        known = {_cell_id(table, cell): cell for cell in cells}
        for row_index, row in enumerate(table.grid):
            for col_index, slot in enumerate(row):
                if slot.kind == TableSlotKind.ORIGIN:
                    cell = known.get(slot.cell_id or "")
                    if cell is None or (cell.start_row, cell.start_col) != (row_index, col_index):
                        analysis.issues.append(
                            IssueDraft(
                                severity=IssueSeverity.WARNING,
                                category="table_structure",
                                rule_id="QL-TBL-002",
                                message=f"table {table.table_id} 的 origin 槽位引用无效：r{row_index}c{col_index}。",
                                affected_block_ids=[str(table.block_id)],
                                evidence={"table_id": table.table_id, "cell_id": slot.cell_id},
                            )
                        )
                        analysis.valid = False
                else:
                    origin = known.get(slot.origin_cell_id or "")
                    if origin is None or not (
                        origin.start_row <= row_index < origin.start_row + origin.row_span
                        and origin.start_col <= col_index < origin.start_col + origin.col_span
                    ):
                        analysis.issues.append(
                            IssueDraft(
                                severity=IssueSeverity.WARNING,
                                category="table_structure",
                                rule_id="QL-TBL-002",
                                message=f"table {table.table_id} 的 covered 槽位没有合法合并锚点：r{row_index}c{col_index}。",
                                affected_block_ids=[str(table.block_id)],
                                evidence={
                                    "table_id": table.table_id,
                                    "origin_cell_id": slot.origin_cell_id,
                                },
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
    if table.header_rows is not None and table.header_rows > 0:
        if table.header_rows > declared_rows:
            analysis.issues.append(
                IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="table_header_structure",
                    rule_id="QL-TBL-003",
                    message=f"table {table.table_id} 的 header_rows 超过表格行数。",
                    affected_block_ids=[str(table.block_id)],
                    evidence={"table_id": table.table_id},
                )
            )
            analysis.valid = False
        else:
            header_rows = list(range(table.header_rows))
    elif marked_header_rows:
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
                    rule_id="QL-TBL-003",
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
        # AnyDoc 对部分 Excel 复杂表返回 headerRows=0，但 origin/covered 和
        # span 仍完整。采用交接数据验证过的保守策略：先排除连续的全宽标题行，
        # 再从顶部连续合并区域恢复多级表头；该结论只能是 inferred。
        title_rows: list[int] = []
        for row in range(declared_rows):
            full_width = any(
                cell.start_row == row
                and cell.start_col == 0
                and cell.col_span == declared_cols
                for cell in cells
            )
            if full_width and row == len(title_rows):
                title_rows.append(row)
            else:
                break
        start_row = len(title_rows)
        candidate_rows: list[int] = []
        row = start_row
        if row < declared_rows and any(
            cell.start_row == row and (cell.row_span > 1 or cell.col_span > 1)
            for cell in cells
        ):
            candidate_rows.append(row)
            row += 1
            while row < declared_rows:
                row_cells = [cell for cell in cells if cell.start_row == row]
                non_empty = [cell.text.strip() for cell in row_cells if cell.text.strip()]
                has_span = any(
                    cell.start_row == row and (cell.row_span > 1 or cell.col_span > 1)
                    for cell in cells
                )
                if has_span or (
                    non_empty
                    and all(not re.search(r"\d", text) for text in non_empty)
                ):
                    candidate_rows.append(row)
                    row += 1
                    continue
                break
        analysis.title_rows = title_rows
        if candidate_rows:
            header_rows = candidate_rows
            analysis.header_inferred = True
        elif table.header_rows is None and declared_rows > 0:
            # 完全没有原生 headerRows 字段的旧解析器仍保留第一行保守推断。
            header_rows = [0]
            analysis.header_inferred = True
    analysis.header_rows = header_rows
    # A pipe table reconstructed from Markdown exposes rows and columns, but it
    # cannot prove native merge semantics or source-cell coordinates. Keep the
    # usable grid while preventing downstream capabilities/bindings from being
    # overstated as verified.
    if table.metadata.get("structure_source") == "markdown_pipe_table":
        analysis.header_inferred = True
    analysis.row_header_columns = list(table.row_header_columns) or [
        col
        for col in range(declared_cols)
        if any(
            cell.start_col == col
            and cell.start_row in header_rows
            and cell.row_span > 1
            for cell in cells
        )
    ]
    # 表头多级结构中，父表头下方的空槽位是合法布局；数据区空洞才是结构缺失。
    data_holes = [h for h in analysis.holes if h[0] > max(header_rows or [0])]
    if data_holes:
        analysis.issues.append(
            IssueDraft(
                severity=IssueSeverity.WARNING,
                category="table_grid",
                rule_id="QL-TBL-002",
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
    return _column_paths_for_table(table, header_rows).get(col, [])


def _column_paths_for_table(
    table: ParsedTable, header_rows: list[int]
) -> dict[int, list[tuple[str, TableCell]] | None]:
    """一次构建所有列路径，避免每个数据单元格重复扫描全表。"""

    column_count = table.num_cols or max(
        (cell.start_col + cell.col_span for cell in table.cells), default=0
    )
    paths: dict[int, list[tuple[str, TableCell]] | None] = {
        col: [] for col in range(column_count)
    }
    header_set = set(header_rows)
    cells_by_row: dict[int, list[TableCell]] = {}
    for cell in table.cells:
        if cell.start_row in header_set:
            cells_by_row.setdefault(cell.start_row, []).append(cell)

    for row in header_rows:
        covering_by_col: dict[int, list[TableCell]] = {}
        for cell in cells_by_row.get(row, []):
            start = max(0, cell.start_col)
            stop = min(column_count, cell.start_col + cell.col_span)
            for col in range(start, stop):
                covering_by_col.setdefault(col, []).append(cell)
        for col in range(column_count):
            covering = covering_by_col.get(col, [])
            if len(covering) > 1:
                paths[col] = None
                continue
            if not covering or paths[col] is None:
                continue
            cell = covering[0]
            if cell.text.strip():
                paths[col].append((cell.text.strip(), cell))
    return paths


def _table_cell_indexes(
    table: ParsedTable,
) -> tuple[dict[int, list[TableCell]], dict[tuple[int, int], TableCell | None]]:
    """构建行索引和逻辑槽位索引；冲突槽位记为 None。"""

    cells_by_row: dict[int, list[TableCell]] = {}
    covering_by_slot: dict[tuple[int, int], TableCell | None] = {}
    for cell in table.cells:
        cells_by_row.setdefault(cell.start_row, []).append(cell)
        for row in range(cell.start_row, cell.start_row + cell.row_span):
            for col in range(cell.start_col, cell.start_col + cell.col_span):
                slot = (row, col)
                if slot in covering_by_slot:
                    covering_by_slot[slot] = None
                else:
                    covering_by_slot[slot] = cell
    return cells_by_row, covering_by_slot


def _covering_cell(table: ParsedTable, row: int, col: int) -> TableCell | None:
    """返回逻辑坐标对应的源锚点单元格，包括合并区域的 covered 位置。"""

    covering = [
        cell
        for cell in table.cells
        if cell.start_row <= row < cell.start_row + cell.row_span
        and cell.start_col <= col < cell.start_col + cell.col_span
    ]
    return covering[0] if len(covering) == 1 else None


class QL_TBL_004_ColumnPath(QualityRule):
    """多级 column_path 生成（对每个数据列）。"""

    rule_id = "QL-TBL-004"
    required_evidence = (
        EvidenceRequirement(kind="tables", required_state="available"),
        EvidenceRequirement(kind="table_cells", required_state="partial_allowed"),
    )

    def execute(self, context: EvidenceContext) -> RuleResult:
        if not context.parsed.tables:
            return RuleResult()
        issues: list[IssueDraft] = []
        observations: list[CapabilityObservation] = []
        grid_verified = True
        header_inferred = False
        grid_evidence_refs: list[EvidenceRef] = []
        for table in context.parsed.tables:
            grid_evidence_refs.append(
                EvidenceRef(
                    object_type="table",
                    object_id=table.table_id,
                    field_path="grid" if table.grid else "cells",
                )
            )
            analysis = analyze_grid(table)
            header_inferred = header_inferred or analysis.header_inferred
            if not analysis.valid:
                grid_verified = False
                issues.extend(analysis.issues)
                continue
            column_paths = _column_paths_for_table(table, analysis.header_rows)
            # 验证每个数据列的 column_path 可确定
            for col in range(table.num_cols or 0):
                path = column_paths.get(col)
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
                    if grid_verified and not header_inferred
                    else QualityCapabilityState.INFERRED
                    if grid_verified
                    else QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                ),
                evidence_refs=grid_evidence_refs,
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
        binding_evidence_refs: list[EvidenceRef] = []

        for table in context.parsed.tables:
            binding_evidence_refs.append(
                EvidenceRef(
                    object_type="table",
                    object_id=table.table_id,
                    field_path="cells",
                )
            )
            analysis = analyze_grid(table)
            if not analysis.valid:
                issues.extend(analysis.issues)
                continue
            if uses_external_table_index(table):
                observations.append(
                    CapabilityObservation(
                        capability_name="table_field_binding_reliable",
                        observed_state=QualityCapabilityState.INFERRED,
                        evidence_refs=[
                            EvidenceRef(
                                object_type="table",
                                object_id=table.table_id,
                                field_path="external_table_index",
                            )
                        ],
                    )
                )
                continue
            header_rows = analysis.header_rows
            last_header_row = max(header_rows) if header_rows else -1
            cells_by_row, covering_by_slot = _table_cell_indexes(table)
            column_paths = _column_paths_for_table(table, header_rows)
            # table.block_id 是 DocumentBlock 的 UUID（对应解析器的 table block）
            block = context.block(str(table.block_id))

            # 先建立每行 row_key，并检测重复；禁止用序号伪造唯一性。
            row_infos: dict[
                int,
                tuple[
                    list[TableCell],
                    list[TableCell],
                    list[str],
                    str,
                    QualityCapabilityState,
                ],
            ] = {}
            key_rows: dict[str, list[int]] = {}
            for row in range(last_header_row + 1, table.num_rows or 0):
                row_cells = cells_by_row.get(row, [])
                if not row_cells:
                    continue
                explicit_row_headers = sorted(
                    (c for c in row_cells if c.row_header),
                    key=lambda c: c.start_col,
                )
                inferred_row_headers = [
                    cell
                    for col in analysis.row_header_columns
                    if (cell := covering_by_slot.get((row, col))) is not None
                ]
                # 合并行头必须沿 covered 槽位继承源锚点，且同一源单元格只保留一次。
                row_headers: list[TableCell] = []
                seen_row_header_ids: set[str] = set()
                for cell in [*explicit_row_headers, *inferred_row_headers]:
                    identity = _cell_id(table, cell)
                    if identity not in seen_row_header_ids:
                        row_headers.append(cell)
                        seen_row_header_ids.add(identity)
                row_header_is_explicit = bool(explicit_row_headers) or bool(
                    table.row_header_columns and inferred_row_headers
                )
                first_cell = min(row_cells, key=lambda c: c.start_col)
                sources = row_headers or [first_cell]
                row_path = [c.text.strip() for c in sources if c.text.strip()]
                row_key = " / ".join(row_path)
                if not row_key:
                    continue
                row_key_state = (
                    QualityCapabilityState.VERIFIED
                    if row_header_is_explicit
                    else QualityCapabilityState.INFERRED
                )
                row_infos[row] = (row_cells, sources, row_path, row_key, row_key_state)
                key_rows.setdefault(row_key, []).append(row)
            duplicate_keys = {key for key, rows in key_rows.items() if len(rows) > 1}
            if duplicate_keys:
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="table_field_binding",
                        rule_id="QL-TBL-005",
                        message=f"row_key 重复，无法唯一定位: {', '.join(sorted(duplicate_keys))}。",
                        status=IssueStatus.MANUAL_REVIEW_REQUIRED,
                        affected_block_ids=[str(table.block_id)],
                    )
                )

            for row, (row_cells, sources, row_path, row_key, row_key_state) in row_infos.items():
                if row_key in duplicate_keys:
                    row_key_state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED

                # 每个非 header 数据单元格 → binding
                for cell in row_cells:
                    if (
                        cell.column_header
                        or cell.row_header
                        or cell.start_col in analysis.row_header_columns
                    ):
                        continue
                    if cell.start_row != row:
                        continue
                    path = column_paths.get(cell.start_col)
                    if not path:
                        continue  # path 无法确定 → 不生成（不制造错误绑定）
                    path_text = [text for text, _ in path]
                    # binding 状态：path 全部来自真实 header cell + row_key 状态
                    path_verified = not analysis.header_inferred
                    if row_key_state == QualityCapabilityState.MANUAL_REVIEW_REQUIRED:
                        state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                    elif path_verified and row_key_state == QualityCapabilityState.VERIFIED:
                        state = QualityCapabilityState.VERIFIED
                    else:
                        state = QualityCapabilityState.INFERRED
                    if block is None or not block.source_block_id:
                        state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                    cell_anchor = cell.source_anchor
                    if cell.bbox is not None or (cell_anchor and cell_anchor.bbox is not None):
                        source_bbox = cell.bbox or cell_anchor.bbox
                        bbox_granularity = "cell"
                    else:
                        source_bbox = table.bbox
                        bbox_granularity = "table" if table.bbox is not None else None
                    source_locator = CanonicalSourceLocator(
                        source_block_id=block.source_block_id if block else "",
                        page_number=table.page_number,
                        bbox=source_bbox,
                        bbox_granularity=bbox_granularity,
                        container=(cell_anchor.container if cell_anchor else None)
                        or table.source_container,
                        container_name=(cell_anchor.container_name if cell_anchor else None)
                        or table.source_container_name,
                        cell_ref=cell_anchor.cell_ref if cell_anchor else None,
                        range_ref=table.source_range,
                        table_cell=f"r{row}c{cell.start_col}",
                        provenance_status=state,
                    )
                    path_evidence = [
                        {
                            "cell_id": _cell_id(table, c),
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
                            row_path=row_path,
                            row_cell_ids=[_cell_id(table, c) for c in sources],
                            column_cell_ids=[_cell_id(table, c) for _, c in path],
                            value_cell_id=_cell_id(table, cell),
                            cell_key=_cell_id(table, cell),
                            evidence_refs=[
                                EvidenceRef(
                                    object_type="cell",
                                    object_id=_cell_id(table, cell),
                                    field_path="text",
                                ),
                                *[
                                    EvidenceRef(
                                        object_type="cell",
                                        object_id=_cell_id(table, c),
                                        field_path="text",
                                    )
                                    for c in sources
                                ],
                                *[
                                    EvidenceRef(
                                        object_type="cell",
                                        object_id=_cell_id(table, c),
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
                                            "cell_id": _cell_id(table, c),
                                            "start_row": c.start_row,
                                            "start_col": c.start_col,
                                            "row_span": c.row_span,
                                            "col_span": c.col_span,
                                        }
                                        for c in sources
                                    ],
                                },
                                "column_path_segments": path_evidence,
                                "value_cell": {
                                    "cell_id": _cell_id(table, cell),
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
            manual_review_required = any(
                candidate.source_locator.provenance_status
                == QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                for candidate in candidates
            )
            observations.append(
                CapabilityObservation(
                    capability_name="table_field_binding_reliable",
                    observed_state=(
                        QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                        if manual_review_required
                        else QualityCapabilityState.VERIFIED
                        if verified == len(candidates)
                        else QualityCapabilityState.INFERRED
                    ),
                    evidence_refs=binding_evidence_refs,
                )
            )
        return RuleResult(
            issues=tuple(issues),
            binding_candidates=tuple(candidates),
            capability_observations=tuple(observations),
        )


class QL_TBL_010_TableEvidenceIntegrity(QualityRule):
    """检查工作表视图计数和嵌套表格父子引用，不把视图差异误报为丢失。"""

    rule_id = "QL-TBL-010"
    required_evidence = (EvidenceRequirement(kind="tables", required_state="available"),)

    def execute(self, context: EvidenceContext) -> RuleResult:
        if not context.parsed.tables:
            return RuleResult()
        issues: list[IssueDraft] = []
        observations: list[CapabilityObservation] = []
        table_by_id = {table.table_id: table for table in context.parsed.tables}
        structure_valid = True
        view_states: list[QualityCapabilityState] = []
        structure_evidence_refs: list[EvidenceRef] = []
        view_evidence_refs: list[EvidenceRef] = []

        for table in context.parsed.tables:
            evidence = {"table_id": table.table_id}
            structure_evidence_refs.append(
                EvidenceRef(
                    object_type="table",
                    object_id=table.table_id,
                    field_path="cells",
                )
            )
            for cell in table.cells:
                if (
                    (cell.row_span > 1 or cell.col_span > 1)
                    and ("\t" in cell.text or cell.text.count("\n") >= 2)
                ):
                    issues.append(
                        IssueDraft(
                            severity=IssueSeverity.WARNING,
                            category="table_pseudo_nested",
                            message=(
                                f"table {table.table_id} 的单元格 {_cell_id(table, cell)} "
                                "包含类似子表的分隔文本，但没有真实嵌套表结构证据。"
                            ),
                            status=IssueStatus.MANUAL_REVIEW_REQUIRED,
                            affected_block_ids=[str(table.block_id)],
                            evidence={
                                **evidence,
                                "cell_id": _cell_id(table, cell),
                                "row_span": cell.row_span,
                                "col_span": cell.col_span,
                                "decision": "preserve_text_and_review",
                            },
                        )
                    )
            if (
                table.emitted_row_count is not None
                and table.num_rows is not None
                and table.emitted_row_count != table.num_rows
            ):
                structure_valid = False
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="table_structure",
                        message=f"table {table.table_id} 的 emitted_row_count 与逻辑网格行数不一致。",
                        status=IssueStatus.MANUAL_REVIEW_REQUIRED,
                        affected_block_ids=[str(table.block_id)],
                        evidence={
                            **evidence,
                            "emitted_row_count": table.emitted_row_count,
                            "grid_row_count": table.num_rows,
                        },
                    )
                )
            if (
                table.source_row_count is not None
                and table.hidden_row_count is not None
                and table.hidden_row_count > table.source_row_count
            ):
                structure_valid = False
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="table_view",
                        message=f"table {table.table_id} 的隐藏行数超过源非空行数。",
                        status=IssueStatus.MANUAL_REVIEW_REQUIRED,
                        affected_block_ids=[str(table.block_id)],
                        evidence={
                            **evidence,
                            "source_row_count": table.source_row_count,
                            "hidden_row_count": table.hidden_row_count,
                        },
                    )
                )

            view_applicable = table.source_container == "sheet" or table.source_row_count is not None
            if view_applicable:
                view_evidence_refs.append(
                    EvidenceRef(
                        object_type="table",
                        object_id=table.table_id,
                        field_path="view_scope",
                    )
                )
                view_state = QualityCapabilityState.VERIFIED
                if table.view_scope.value == "unknown":
                    view_state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                    issues.append(
                        IssueDraft(
                            severity=IssueSeverity.WARNING,
                            category="table_view",
                            message=f"table {table.table_id} 无法确定交付的是全量行还是可见行。",
                            status=IssueStatus.MANUAL_REVIEW_REQUIRED,
                            affected_block_ids=[str(table.block_id)],
                            evidence={
                                **evidence,
                                "source_row_count": table.source_row_count,
                                "emitted_row_count": table.emitted_row_count,
                                "hidden_row_count": table.hidden_row_count,
                                "source_has_filter": table.source_has_filter,
                            },
                        )
                    )
                elif (
                    table.view_scope.value == "all_rows"
                    and table.source_row_count is not None
                    and table.emitted_row_count is not None
                    and table.emitted_row_count != table.source_row_count
                ):
                    view_state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                    issues.append(
                        IssueDraft(
                            severity=IssueSeverity.WARNING,
                            category="table_view",
                            message=f"table {table.table_id} 标记为全量行，但交付行数与源非空行数不相等。",
                            status=IssueStatus.MANUAL_REVIEW_REQUIRED,
                            affected_block_ids=[str(table.block_id)],
                            evidence={
                                **evidence,
                                "view_scope": table.view_scope.value,
                                "source_row_count": table.source_row_count,
                                "emitted_row_count": table.emitted_row_count,
                            },
                        )
                    )
                elif (
                    table.view_scope.value == "visible_rows"
                    and table.source_row_count is not None
                    and table.emitted_row_count is not None
                    and table.hidden_row_count is not None
                    and table.emitted_row_count + table.hidden_row_count
                    != table.source_row_count
                ):
                    view_state = QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                    issues.append(
                        IssueDraft(
                            severity=IssueSeverity.WARNING,
                            category="table_view",
                            message=f"table {table.table_id} 标记为可见行，但可见行与隐藏行无法和源行数对账。",
                            status=IssueStatus.MANUAL_REVIEW_REQUIRED,
                            affected_block_ids=[str(table.block_id)],
                            evidence={
                                **evidence,
                                "view_scope": table.view_scope.value,
                                "source_row_count": table.source_row_count,
                                "emitted_row_count": table.emitted_row_count,
                                "hidden_row_count": table.hidden_row_count,
                            },
                        )
                    )
                view_states.append(view_state)

            missing_source_refs = [
                _cell_id(table, cell)
                for cell in table.cells
                if table.source_container == "sheet"
                and (cell.source_anchor is None or not cell.source_anchor.cell_ref)
            ]
            if missing_source_refs:
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="table_source_mapping",
                        message=f"table {table.table_id} 有单元格无法定位到源工作表 A1 坐标。",
                        status=IssueStatus.MANUAL_REVIEW_REQUIRED,
                        affected_block_ids=[str(table.block_id)],
                        evidence={
                            **evidence,
                            "missing_cell_ref_count": len(missing_source_refs),
                            "sample_cell_ids": missing_source_refs[:20],
                        },
                    )
                )

            if table.parent_table_id is not None:
                parent = table_by_id.get(table.parent_table_id)
                parent_cells = {
                    _cell_id(parent, cell) for cell in parent.cells
                } if parent is not None else set()
                if (
                    parent is None
                    or not table.parent_cell_id
                    or table.parent_cell_id not in parent_cells
                    or table.nesting_depth != parent.nesting_depth + 1
                ):
                    structure_valid = False
                    issues.append(
                        IssueDraft(
                            severity=IssueSeverity.WARNING,
                            category="table_structure",
                            message=f"table {table.table_id} 的嵌套父表或父单元格引用无效。",
                            status=IssueStatus.MANUAL_REVIEW_REQUIRED,
                            affected_block_ids=[str(table.block_id)],
                            evidence={
                                **evidence,
                                "parent_table_id": table.parent_table_id,
                                "parent_cell_id": table.parent_cell_id,
                            },
                        )
                    )

        observations.append(
            CapabilityObservation(
                capability_name="table_structure_reliable",
                observed_state=(
                    QualityCapabilityState.VERIFIED
                    if structure_valid
                    else QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                ),
                evidence_refs=structure_evidence_refs,
            )
        )
        if view_states:
            observations.append(
                CapabilityObservation(
                    capability_name="table_view_scope_reliable",
                    observed_state=(
                        QualityCapabilityState.VERIFIED
                        if all(state == QualityCapabilityState.VERIFIED for state in view_states)
                        else QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                    ),
                    evidence_refs=view_evidence_refs,
                )
            )
        return RuleResult(
            issues=tuple(issues),
            capability_observations=tuple(observations),
        )
