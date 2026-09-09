"""大表结构的 SQLite 索引写入与校验。"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Iterator

from document_parser.domain.model.contracts import (
    CanonicalTable,
    QualityCapabilityState,
    QualityPackage,
    TableCell,
)
from document_parser.domain.quality.ids import stable_id
from document_parser.domain.quality.table_storage import TABLE_INDEX_NAME


def external_tables(package: QualityPackage) -> list[CanonicalTable]:
    return [
        table
        for table in package.canonical_document.tables
        if table.metadata.get("table_storage", {}).get("mode") == "sqlite"
    ]


def _cell_id(table: CanonicalTable, cell: TableCell) -> str:
    return cell.cell_id or f"{table.table_id}:r{cell.start_row}c{cell.start_col}"


def _column_paths(
    table: CanonicalTable,
) -> dict[int, list[tuple[str, TableCell]] | None]:
    paths: dict[int, list[tuple[str, TableCell]] | None] = {
        col: [] for col in range(table.num_cols)
    }
    header_rows = set(table.header_row_indices)
    cells_by_row: dict[int, list[TableCell]] = {}
    for cell in table.cells:
        if cell.start_row in header_rows:
            cells_by_row.setdefault(cell.start_row, []).append(cell)
    for row in table.header_row_indices:
        covering_by_col: dict[int, list[TableCell]] = {}
        for cell in cells_by_row.get(row, []):
            for col in range(
                max(0, cell.start_col),
                min(table.num_cols, cell.start_col + cell.col_span),
            ):
                covering_by_col.setdefault(col, []).append(cell)
        for col in range(table.num_cols):
            covering = covering_by_col.get(col, [])
            if len(covering) > 1:
                paths[col] = None
            elif covering and paths[col] is not None and covering[0].text.strip():
                paths[col].append((covering[0].text.strip(), covering[0]))
    return paths


def _row_data(
    table: CanonicalTable,
) -> tuple[
    dict[int, list[TableCell]],
    dict[int, tuple[list[TableCell], list[str], str, bool]],
    set[str],
]:
    cells_by_row: dict[int, list[TableCell]] = {}
    covering_by_slot: dict[tuple[int, int], TableCell | None] = {}
    for cell in table.cells:
        cells_by_row.setdefault(cell.start_row, []).append(cell)
        for row in range(cell.start_row, cell.start_row + cell.row_span):
            for col in range(cell.start_col, cell.start_col + cell.col_span):
                slot = (row, col)
                covering_by_slot[slot] = (
                    None if slot in covering_by_slot else cell
                )

    last_header = max(table.header_row_indices, default=-1)
    rows: dict[int, tuple[list[TableCell], list[str], str, bool]] = {}
    keys: Counter[str] = Counter()
    for row in range(last_header + 1, table.num_rows):
        row_cells = cells_by_row.get(row, [])
        if not row_cells:
            continue
        explicit = sorted(
            (cell for cell in row_cells if cell.row_header),
            key=lambda cell: cell.start_col,
        )
        inferred = [
            cell
            for col in table.row_header_columns
            if (cell := covering_by_slot.get((row, col))) is not None
        ]
        sources: list[TableCell] = []
        seen: set[str] = set()
        for cell in [*explicit, *inferred]:
            identity = _cell_id(table, cell)
            if identity not in seen:
                sources.append(cell)
                seen.add(identity)
        sources = sources or [min(row_cells, key=lambda cell: cell.start_col)]
        row_path = [cell.text.strip() for cell in sources if cell.text.strip()]
        row_key = " / ".join(row_path)
        if not row_key:
            continue
        explicit_key = bool(explicit) or bool(table.row_header_columns and inferred)
        rows[row] = (sources, row_path, row_key, explicit_key)
        keys[row_key] += 1
    return cells_by_row, rows, {key for key, count in keys.items() if count > 1}


def _iter_bindings(table: CanonicalTable) -> Iterator[tuple]:
    column_paths = _column_paths(table)
    cells_by_row, rows, duplicate_keys = _row_data(table)
    for row, (sources, row_path, row_key, explicit_key) in rows.items():
        for cell in cells_by_row[row]:
            if (
                cell.column_header
                or cell.row_header
                or cell.start_col in table.row_header_columns
            ):
                continue
            path = column_paths.get(cell.start_col)
            if not path:
                continue
            path_text = [text for text, _ in path]
            if row_key in duplicate_keys:
                status = QualityCapabilityState.MANUAL_REVIEW_REQUIRED.value
            elif (
                explicit_key
                and table.header_state == QualityCapabilityState.VERIFIED
            ):
                status = QualityCapabilityState.VERIFIED.value
            else:
                status = QualityCapabilityState.INFERRED.value
            anchor = cell.source_anchor
            value_cell_id = _cell_id(table, cell)
            yield (
                stable_id(
                    "indexed-binding|"
                    f"{table.table_id}|{value_cell_id}|{row_key}|{'/'.join(path_text)}"
                ),
                table.table_id,
                row,
                cell.start_col,
                row_key,
                json.dumps(row_path, ensure_ascii=False),
                json.dumps(path_text, ensure_ascii=False),
                cell.text.strip(),
                value_cell_id,
                status,
                anchor.container_name if anchor else table.source_locator.container_name,
                anchor.cell_ref if anchor else None,
                json.dumps([_cell_id(table, source) for source in sources], ensure_ascii=False),
                json.dumps([_cell_id(table, item) for _, item in path], ensure_ascii=False),
            )


def write_table_index(package: QualityPackage, path: Path) -> dict | None:
    """把外置大表按流式批次写入 SQLite，并返回 structure.json 描述。"""

    tables = external_tables(package)
    if not tables:
        return None
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    binding_count = 0
    cell_count = 0
    fts_enabled = False
    try:
        connection.executescript(
            """
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE document_tables (
                table_id TEXT PRIMARY KEY,
                block_id TEXT NOT NULL,
                source_container_name TEXT,
                source_range TEXT,
                num_rows INTEGER NOT NULL,
                num_cols INTEGER NOT NULL,
                header_row_indices_json TEXT NOT NULL,
                row_header_columns_json TEXT NOT NULL,
                view_scope TEXT NOT NULL
            );
            CREATE TABLE table_cells (
                cell_id TEXT PRIMARY KEY,
                table_id TEXT NOT NULL,
                start_row INTEGER NOT NULL,
                start_col INTEGER NOT NULL,
                row_span INTEGER NOT NULL,
                col_span INTEGER NOT NULL,
                text TEXT NOT NULL,
                raw_value_json TEXT,
                display_value TEXT,
                normalized_value TEXT,
                value_type TEXT,
                formula TEXT,
                roles_json TEXT NOT NULL,
                source_container_name TEXT,
                source_cell_ref TEXT,
                FOREIGN KEY(table_id) REFERENCES document_tables(table_id)
            );
            CREATE TABLE field_bindings (
                binding_id TEXT PRIMARY KEY,
                table_id TEXT NOT NULL,
                row_index INTEGER NOT NULL,
                col_index INTEGER NOT NULL,
                row_key TEXT NOT NULL,
                row_path_json TEXT NOT NULL,
                column_path_json TEXT NOT NULL,
                value TEXT NOT NULL,
                value_cell_id TEXT NOT NULL,
                status TEXT NOT NULL,
                source_container_name TEXT,
                source_cell_ref TEXT,
                row_cell_ids_json TEXT NOT NULL,
                column_cell_ids_json TEXT NOT NULL,
                FOREIGN KEY(table_id) REFERENCES document_tables(table_id)
            );
            CREATE INDEX idx_cells_table_position
                ON table_cells(table_id, start_row, start_col);
            CREATE INDEX idx_cells_source_position
                ON table_cells(source_container_name, source_cell_ref);
            CREATE INDEX idx_bindings_table_position
                ON field_bindings(table_id, row_index, col_index);
            CREATE INDEX idx_bindings_row_key
                ON field_bindings(table_id, row_key);
            CREATE INDEX idx_bindings_source_position
                ON field_bindings(source_container_name, source_cell_ref);
            """
        )
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            [
                ("document_id", str(package.document_id)),
                ("storage_kind", "indexed_table_structure"),
            ],
        )
        for table in tables:
            connection.execute(
                """
                INSERT INTO document_tables VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    table.table_id,
                    table.block_id,
                    table.source_locator.container_name,
                    table.source_locator.range_ref,
                    table.num_rows,
                    table.num_cols,
                    json.dumps(table.header_row_indices, ensure_ascii=False),
                    json.dumps(table.row_header_columns, ensure_ascii=False),
                    table.view_scope.value,
                ),
            )
            cell_rows = []
            for cell in table.cells:
                anchor = cell.source_anchor
                cell_rows.append(
                    (
                        _cell_id(table, cell),
                        table.table_id,
                        cell.start_row,
                        cell.start_col,
                        cell.row_span,
                        cell.col_span,
                        cell.text,
                        json.dumps(cell.raw_value, ensure_ascii=False, default=str),
                        cell.display_value,
                        cell.normalized_value,
                        cell.value_type,
                        cell.formula,
                        json.dumps(cell.roles, ensure_ascii=False),
                        anchor.container_name if anchor else table.source_locator.container_name,
                        anchor.cell_ref if anchor else None,
                    )
                )
                if len(cell_rows) >= 2_000:
                    connection.executemany(
                        "INSERT INTO table_cells VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        cell_rows,
                    )
                    cell_count += len(cell_rows)
                    cell_rows.clear()
            if cell_rows:
                connection.executemany(
                    "INSERT INTO table_cells VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    cell_rows,
                )
                cell_count += len(cell_rows)

            binding_rows = []
            for binding in _iter_bindings(table):
                binding_rows.append(binding)
                if len(binding_rows) >= 2_000:
                    connection.executemany(
                        "INSERT INTO field_bindings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        binding_rows,
                    )
                    binding_count += len(binding_rows)
                    binding_rows.clear()
            if binding_rows:
                connection.executemany(
                    "INSERT INTO field_bindings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    binding_rows,
                )
                binding_count += len(binding_rows)
        try:
            connection.execute(
                "CREATE VIRTUAL TABLE cell_search USING fts5(cell_id UNINDEXED, table_id UNINDEXED, text)"
            )
            connection.execute(
                "INSERT INTO cell_search(cell_id, table_id, text) SELECT cell_id, table_id, text FROM table_cells"
            )
            fts_enabled = True
        except sqlite3.OperationalError:
            fts_enabled = False
        connection.commit()
    finally:
        connection.close()
    return {
        "mode": "sqlite",
        "file": TABLE_INDEX_NAME,
        "table_count": len(tables),
        "cell_count": cell_count,
        "binding_count": binding_count,
        "fts_enabled": fts_enabled,
        "tables": ["document_tables", "table_cells", "field_bindings"],
        "query_keys": [
            "table_id + start_row + start_col",
            "source_container_name + source_cell_ref",
            "table_id + row_key",
        ],
    }


def verify_table_index(path: Path, document_id: str) -> None:
    if not path.is_file():
        raise ValueError(f"缺少大表索引文件: {path.name}")
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        stored = connection.execute(
            "SELECT value FROM metadata WHERE key='document_id'"
        ).fetchone()
        if stored is None or stored[0] != document_id:
            raise ValueError("大表索引与结构 JSON 的 document_id 不一致")
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required = {"document_tables", "table_cells", "field_bindings"}
        if not required.issubset(names):
            raise ValueError("大表索引缺少必要数据表")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise ValueError("大表索引完整性检查失败")
    finally:
        connection.close()
