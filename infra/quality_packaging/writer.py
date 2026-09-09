"""质量包安全写入与目录校验。"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

from document_parser.domain.model.contracts import QualityPackage
from document_parser.domain.quality.table_storage import TABLE_INDEX_NAME

from .artifacts import (
    build_package_artifacts,
    read_package_files,
    verify_package_files,
)
from .table_index import verify_table_index, write_table_index


def _write_bytes(path: Path, data: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def write_package_directory(
    package: QualityPackage,
    output_dir: Path,
    *,
    replace_existing: bool = False,
) -> Path:
    """原子写入质量产物；大表会附带 SQLite 索引文件。"""
    output_dir = Path(output_dir)
    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists() and not replace_existing:
        raise FileExistsError(f"output directory already exists: {output_dir}")

    temp_name = tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=str(parent))
    temp_dir = Path(temp_name)
    backup_dir: Path | None = None
    try:
        table_index = write_table_index(package, temp_dir / TABLE_INDEX_NAME)
        artifacts = build_package_artifacts(package, table_index=table_index)
        for name, data in artifacts.files.items():
            _write_bytes(temp_dir / name, data)
        verify_package_files({name: (temp_dir / name).read_bytes() for name in artifacts.files})
        if table_index is not None:
            verify_table_index(temp_dir / TABLE_INDEX_NAME, str(package.document_id))

        if output_dir.exists():
            backup_dir = parent / f".{output_dir.name}.backup-{uuid.uuid4().hex}"
            os.replace(output_dir, backup_dir)
        try:
            os.replace(temp_dir, output_dir)
        except Exception:
            if backup_dir is not None and backup_dir.exists() and not output_dir.exists():
                os.replace(backup_dir, output_dir)
            raise
        if backup_dir is not None and backup_dir.exists():
            if backup_dir.is_dir():
                shutil.rmtree(backup_dir)
            else:
                backup_dir.unlink()
        return output_dir
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise


def verify_package_directory(directory: Path) -> None:
    """读取并校验已落盘的质量包及可选大表索引。"""
    read_package_files(Path(directory))
