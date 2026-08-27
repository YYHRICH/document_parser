"""Parser-neutral table representation selection and consistency checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from quality.contracts import EvidenceAvailability, ParsedTable
from quality.models_internal import EvidenceRef
from quality.representations.inventory import RepresentationInventory
from quality.representations.models import (
    RepresentationDescriptor,
    RepresentationFidelity,
    RepresentationKind,
    RepresentationTarget,
)
from quality.representations.table_html import html_table_to_markdown, parse_html_table


class TableResolutionDecision(StrEnum):
    """A display decision; it does not mutate ParsedDocument."""

    USE_TABLE_MARKDOWN = "use_table_markdown"
    AUTO_SAFE_HTML_TO_MARKDOWN = "auto_safe_html_to_markdown"
    LOSSY_HTML_PROJECTION_REVIEW = "lossy_html_projection_review"
    REVIEW_INCONSISTENT = "review_inconsistent_representations"
    REVIEW_UNUSABLE_HTML = "review_unusable_html"
    NO_DISPLAY_REPRESENTATION = "no_display_representation"


@dataclass(frozen=True)
class TableGrid:
    """A normalized rectangular view used only for structural comparisons."""

    kind: RepresentationKind
    rows: tuple[tuple[str, ...], ...]
    complete: bool
    has_spans: bool = False
    reason: str | None = None

    @property
    def shape(self) -> tuple[int, int]:
        return (len(self.rows), len(self.rows[0]) if self.rows else 0)


@dataclass(frozen=True)
class TableRepresentationComparison:
    """Compatibility result for two independently supplied table views."""

    left_kind: RepresentationKind
    right_kind: RepresentationKind
    compatible: bool
    reasons: tuple[str, ...] = ()
    mismatched_cells: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class TableResolution:
    """The resolver result consumed by a later policy/executor stage."""

    table_id: str
    decision: TableResolutionDecision
    selected_representation: RepresentationDescriptor | None = None
    conversion_target: RepresentationTarget | None = None
    generated_markdown: str | None = None
    generated_fidelity: RepresentationFidelity = RepresentationFidelity.UNKNOWN
    has_spans: bool = False
    comparisons: tuple[TableRepresentationComparison, ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()
    reason: str | None = None

    @property
    def review_required(self) -> bool:
        return self.decision in {
            TableResolutionDecision.LOSSY_HTML_PROJECTION_REVIEW,
            TableResolutionDecision.REVIEW_INCONSISTENT,
            TableResolutionDecision.REVIEW_UNUSABLE_HTML,
        }

    @property
    def auto_safe(self) -> bool:
        return self.decision == TableResolutionDecision.AUTO_SAFE_HTML_TO_MARKDOWN


_SEPARATOR_CELL = re.compile(r"\s*:?-{3,}:?\s*")


def _normalise_for_compare(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("<br>", " ")).strip()


def _split_markdown_row(line: str) -> tuple[str, ...] | None:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return None
    cells: list[str] = []
    current: list[str] = []
    index = 1
    end = len(stripped) - 1
    while index < end:
        char = stripped[index]
        if char == "\\" and index + 1 < end and stripped[index + 1] == "|":
            current.append("|")
            index += 2
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    cells.append("".join(current).strip())
    return tuple(cells)


def parse_markdown_table(markdown: str) -> TableGrid | None:
    """Parse one strict pipe table; non-table prose is deliberately rejected."""
    lines = markdown.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) < 2:
        return None
    parsed_lines = [_split_markdown_row(line) for line in lines]
    if any(row is None for row in parsed_lines):
        return None
    rows = [row for row in parsed_lines if row is not None]
    width = len(rows[0])
    if width == 0 or len(rows[1]) != width:
        return None
    if not all(_SEPARATOR_CELL.fullmatch(cell) for cell in rows[1]):
        return None
    data_rows = [rows[0], *rows[2:]]
    if any(len(row) != width for row in data_rows):
        return None
    return TableGrid(
        kind=RepresentationKind.TABLE_MARKDOWN,
        rows=tuple(data_rows),
        complete=True,
    )


def _grid_from_cells(table: ParsedTable) -> TableGrid | None:
    if not table.cells:
        return None
    max_row = max(cell.start_row + cell.row_span for cell in table.cells)
    max_col = max(cell.start_col + cell.col_span for cell in table.cells)
    row_count = table.num_rows if table.num_rows is not None else max_row
    col_count = table.num_cols if table.num_cols is not None else max_col
    if row_count <= 0 or col_count <= 0 or max_row > row_count or max_col > col_count:
        return TableGrid(
            kind=RepresentationKind.TABLE_CELLS,
            rows=(),
            complete=False,
            reason="cell coordinates exceed the declared table dimensions",
        )

    occupied: set[tuple[int, int]] = set()
    grid = [["" for _ in range(col_count)] for _ in range(row_count)]
    for cell in table.cells:
        for row in range(cell.start_row, cell.start_row + cell.row_span):
            for column in range(cell.start_col, cell.start_col + cell.col_span):
                position = (row, column)
                if position in occupied:
                    return TableGrid(
                        kind=RepresentationKind.TABLE_CELLS,
                        rows=(),
                        complete=False,
                        reason="cell spans overlap",
                    )
                occupied.add(position)
        grid[cell.start_row][cell.start_col] = cell.text
    return TableGrid(
        kind=RepresentationKind.TABLE_CELLS,
        rows=tuple(tuple(row) for row in grid),
        complete=len(occupied) == row_count * col_count,
        has_spans=any(
            cell.row_span > 1 or cell.col_span > 1
            for cell in table.cells
        ),
        reason=None if len(occupied) == row_count * col_count else "cell grid has uncovered positions",
    )


def _compare(left: TableGrid, right: TableGrid) -> TableRepresentationComparison:
    reasons: list[str] = []
    if not left.complete:
        reasons.append(f"{left.kind.value} is incomplete")
    if not right.complete:
        reasons.append(f"{right.kind.value} is incomplete")
    if left.shape != right.shape:
        reasons.append(f"shape differs: {left.shape} != {right.shape}")
        return TableRepresentationComparison(
            left_kind=left.kind,
            right_kind=right.kind,
            compatible=False,
            reasons=tuple(reasons),
        )
    mismatches = tuple(
        (row_index, column_index)
        for row_index, (left_row, right_row) in enumerate(zip(left.rows, right.rows))
        for column_index, (left_value, right_value) in enumerate(zip(left_row, right_row))
        if _normalise_for_compare(left_value) != _normalise_for_compare(right_value)
    )
    if mismatches:
        reasons.append(f"{len(mismatches)} cell values differ")
    return TableRepresentationComparison(
        left_kind=left.kind,
        right_kind=right.kind,
        compatible=not reasons,
        reasons=tuple(reasons),
        mismatched_cells=mismatches,
    )


class TableRepresentationResolver:
    """Choose a table display representation without looking at parser identity."""

    def resolve(
        self,
        table: ParsedTable,
        inventory: RepresentationInventory,
    ) -> TableResolution:
        html_descriptor = inventory.find(
            RepresentationKind.TABLE_HTML,
            object_id=table.table_id,
            field_path="html",
        )
        markdown_descriptor = inventory.find(
            RepresentationKind.TABLE_MARKDOWN,
            object_id=table.table_id,
            field_path="markdown",
        )
        cells_descriptor = inventory.find(
            RepresentationKind.TABLE_CELLS,
            object_id=table.table_id,
            field_path="cells",
        )

        html_grid: TableGrid | None = None
        if html_descriptor and html_descriptor.availability == EvidenceAvailability.AVAILABLE:
            html_structure = parse_html_table(table.html or "")
            if html_structure is not None:
                html_grid = TableGrid(
                    kind=RepresentationKind.TABLE_HTML,
                    rows=html_structure.grid,
                    complete=html_structure.complete,
                    has_spans=html_structure.has_spans,
                    reason=None if html_structure.complete else "HTML table has uncovered positions",
                )

        markdown_grid: TableGrid | None = None
        if markdown_descriptor and markdown_descriptor.availability == EvidenceAvailability.AVAILABLE:
            markdown_grid = parse_markdown_table(table.markdown or "")

        cells_grid = _grid_from_cells(table)
        if cells_grid is not None and (
            cells_descriptor is None
            or cells_descriptor.availability
            in {EvidenceAvailability.UNAVAILABLE, EvidenceAvailability.FAILED}
        ):
            # An unavailable/failed descriptor cannot authorize a structural
            # comparison, even if a caller supplied cells.
            cells_grid = TableGrid(
                kind=cells_grid.kind,
                rows=cells_grid.rows,
                complete=False,
                has_spans=cells_grid.has_spans,
                reason=cells_descriptor.reason if cells_descriptor else cells_grid.reason,
            )
        # PARTIAL can describe missing locators (for example cell bbox) rather
        # than a missing grid.  _grid_from_cells independently verifies every
        # declared cell span and rejects overlap or holes, so retain a complete
        # partial grid for representation comparison and deterministic repair.
        # An incomplete partial grid remains incomplete and still forces review.

        grids = [grid for grid in (html_grid, markdown_grid, cells_grid) if grid is not None]
        comparisons = tuple(
            _compare(grids[left_index], grids[right_index])
            for left_index in range(len(grids))
            for right_index in range(left_index + 1, len(grids))
        )
        conflicts = tuple(result for result in comparisons if not result.compatible)
        evidence_refs = tuple(
            reference
            for descriptor in (html_descriptor, markdown_descriptor, cells_descriptor)
            if descriptor is not None
            for reference in descriptor.evidence_refs
        )
        has_spans = any(grid.has_spans for grid in grids)

        if conflicts:
            return TableResolution(
                table_id=table.table_id,
                decision=TableResolutionDecision.REVIEW_INCONSISTENT,
                has_spans=has_spans,
                comparisons=comparisons,
                evidence_refs=evidence_refs,
                reason="table representations disagree; no representation was selected",
            )

        if markdown_grid is not None and markdown_grid.complete and markdown_descriptor:
            return TableResolution(
                table_id=table.table_id,
                decision=TableResolutionDecision.USE_TABLE_MARKDOWN,
                selected_representation=markdown_descriptor,
                generated_fidelity=(
                    RepresentationFidelity.LOSSY
                    if has_spans
                    else markdown_descriptor.fidelity
                ),
                has_spans=has_spans,
                comparisons=comparisons,
                evidence_refs=evidence_refs,
                reason=(
                    "existing Markdown is structurally consistent with the available evidence"
                ),
            )

        if html_grid is not None and html_descriptor:
            candidate = html_table_to_markdown(table.html or "", allow_lossy=True)
            if candidate is None or not html_grid.complete:
                return TableResolution(
                    table_id=table.table_id,
                    decision=TableResolutionDecision.REVIEW_UNUSABLE_HTML,
                    conversion_target=html_descriptor.target,
                    has_spans=has_spans,
                    comparisons=comparisons,
                    evidence_refs=evidence_refs,
                    reason="HTML table cannot be converted without an ambiguous grid",
                )
            if html_grid.has_spans:
                return TableResolution(
                    table_id=table.table_id,
                    decision=TableResolutionDecision.LOSSY_HTML_PROJECTION_REVIEW,
                    conversion_target=html_descriptor.target,
                    generated_markdown=candidate,
                    generated_fidelity=RepresentationFidelity.LOSSY,
                    has_spans=True,
                    comparisons=comparisons,
                    evidence_refs=evidence_refs,
                    reason="rowspan/colspan requires a lossy Markdown projection and review",
                )
            return TableResolution(
                table_id=table.table_id,
                decision=TableResolutionDecision.AUTO_SAFE_HTML_TO_MARKDOWN,
                conversion_target=html_descriptor.target,
                generated_markdown=candidate,
                generated_fidelity=RepresentationFidelity.LOSSLESS,
                comparisons=comparisons,
                evidence_refs=evidence_refs,
                reason="complete span-free HTML table can be converted deterministically",
            )

        if html_descriptor and html_grid is None:
            return TableResolution(
                table_id=table.table_id,
                decision=TableResolutionDecision.REVIEW_UNUSABLE_HTML,
                conversion_target=html_descriptor.target,
                has_spans=has_spans,
                comparisons=comparisons,
                evidence_refs=evidence_refs,
                reason="HTML table is malformed or not structurally parseable",
            )

        return TableResolution(
            table_id=table.table_id,
            decision=TableResolutionDecision.NO_DISPLAY_REPRESENTATION,
            has_spans=has_spans,
            comparisons=comparisons,
            evidence_refs=evidence_refs,
            reason="no structurally valid table Markdown or HTML representation is available",
        )
