"""统一文档包的读取和交付前校验。"""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath, PureWindowsPath

from .contracts import BlockKind, ParsedDocument


class DocumentPackageValidationError(ValueError):
    """统一文档包不满足交付前约束。"""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


def load_document_package(package_root: Path) -> ParsedDocument:
    """读取 ``document_package/parsed_document.json`` 并执行完整性校验。"""

    parsed_document_path = package_root / "parsed_document.json"
    if not parsed_document_path.is_file():
        raise DocumentPackageValidationError(
            [f"缺少主输入文件：{parsed_document_path}"]
        )

    document = ParsedDocument.model_validate_json(
        parsed_document_path.read_text(encoding="utf-8")
    )
    validate_parsed_document_integrity(document, package_root=package_root)
    return document


def write_document_package(
    document: ParsedDocument,
    package_root: Path,
    *,
    source_path: Path | None = None,
    native_files: dict[str, bytes] | None = None,
) -> ParsedDocument:
    """把 ``ParsedDocument`` 落成统一文档包目录。

    这个入口只负责交付层面最常见的目录结构：
    - `parsed_document.json`
    - `assets/`
    - `source/original.*`
    - `native/`

    原生 JSON / HTML / OCR 等侧车如果已经由 Adapter 生成，可通过
    ``native_files`` 一并写入。
    """

    package_root.mkdir(parents=True, exist_ok=True)
    (package_root / "assets").mkdir(parents=True, exist_ok=True)
    (package_root / "source").mkdir(parents=True, exist_ok=True)
    (package_root / "native").mkdir(parents=True, exist_ok=True)

    _write_text(package_root / "parsed_document.json", document.model_dump_json(indent=2))
    # Markdown is a readable projection of ParsedDocument, never an independent
    # source of truth.  Keeping it in the package makes the protocol inspectable
    # while integrity validation catches accidental divergence.
    _write_text(package_root / "document.md", document.markdown)

    for asset in document.assets:
        asset_path = package_root / "assets" / asset.path
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(asset.content)

    if source_path is not None:
        destination = package_root / "source" / f"original{source_path.suffix}"
        shutil.copy2(source_path, destination)

    if native_files is not None:
        for relative_path, content in native_files.items():
            safe_relative_path = _validate_package_relative_path(relative_path)
            native_path = package_root / safe_relative_path
            _ensure_inside(package_root, native_path)
            native_path.parent.mkdir(parents=True, exist_ok=True)
            native_path.write_bytes(content)

    validate_parsed_document_integrity(document, package_root=package_root)
    return document


def validate_parsed_document_integrity(
    document: ParsedDocument,
    *,
    package_root: Path | None = None,
) -> None:
    """校验统一层输出是否能安全交给质量层。

    Pydantic 已经负责字段类型、枚举和安全相对路径的基础校验；这里补充跨字段和
    侧车文件完整性检查，例如 table 是否指向真实 table block、asset 引用是否悬空。
    """

    errors: list[str] = []

    if document.schema_name != "ParsedDocument":
        errors.append(f"schema_name 必须是 ParsedDocument，当前为 {document.schema_name}")
    if document.schema_version != "2.2":
        errors.append(f"schema_version 必须是 2.2，当前为 {document.schema_version}")

    block_ids = [str(block.id) for block in document.blocks]
    duplicate_block_ids = _duplicates(block_ids)
    if duplicate_block_ids:
        errors.append(f"blocks[].id 存在重复：{duplicate_block_ids}")

    block_by_id = {str(block.id): block for block in document.blocks}

    table_ids = [table.table_id for table in document.tables]
    duplicate_table_ids = _duplicates(table_ids)
    if duplicate_table_ids:
        errors.append(f"tables[].table_id 存在重复：{duplicate_table_ids}")

    for table in document.tables:
        table_block = block_by_id.get(str(table.block_id))
        if table_block is None:
            errors.append(
                f"表格 {table.table_id} 的 block_id 不存在：{table.block_id}"
            )
        elif table_block.kind != BlockKind.TABLE:
            errors.append(
                f"表格 {table.table_id} 的 block_id 未指向 table block：{table.block_id}"
            )
        if package_root is not None and table.image_path:
            _check_sidecar_exists(
                errors,
                package_root=package_root,
                relative_path=table.image_path,
                owner=f"表格 {table.table_id} image_path",
            )

    for asset in document.assets:
        for referenced_block_id in asset.referenced_by_block_ids:
            if referenced_block_id not in block_by_id:
                errors.append(
                    f"资源 {asset.path} 引用了不存在的 block：{referenced_block_id}"
                )
        if package_root is not None:
            _check_sidecar_exists(
                errors,
                package_root=package_root / "assets",
                relative_path=asset.path,
                owner=f"资源 {asset.path}",
            )

    if package_root is not None:
        rendered_markdown_path = package_root / "document.md"
        # Older persisted packages did not contain the projection.  They remain
        # readable for migration, while every newly written package must contain it.
        if rendered_markdown_path.is_file():
            rendered_markdown = rendered_markdown_path.read_text(encoding="utf-8")
            if rendered_markdown != document.markdown:
                errors.append("document.md 与 ParsedDocument.markdown 不一致")
        for artifact in document.native_artifacts:
            _check_sidecar_exists(
                errors,
                package_root=package_root,
                relative_path=artifact.path,
                owner=f"原生产物 {artifact.artifact_id}",
            )

    missing_reasons = [
        name
        for name, capability in document.capabilities.items()
        if capability.state.value != "available" and not capability.reason
    ]
    if missing_reasons:
        errors.append(f"非 available capability 缺少 reason：{missing_reasons}")

    if errors:
        raise DocumentPackageValidationError(errors)


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    repeated: set[str] = set()
    for value in values:
        if value in seen:
            repeated.add(value)
        seen.add(value)
    return sorted(repeated)


def _check_sidecar_exists(
    errors: list[str],
    *,
    package_root: Path,
    relative_path: str,
    owner: str,
) -> None:
    path = package_root / relative_path
    if not path.is_file():
        errors.append(f"{owner} 指向的侧车文件不存在：{relative_path}")


def _validate_package_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or bool(windows_path.drive)
        or ".." in path.parts
        or normalized.endswith("/")
    ):
        raise DocumentPackageValidationError(
            [f"侧车文件路径必须是任务包内安全相对路径：{value}"]
        )
    return str(path)


def _ensure_inside(package_root: Path, target: Path) -> None:
    root = package_root.resolve()
    resolved = target.resolve()
    if root != resolved and root not in resolved.parents:
        raise DocumentPackageValidationError(
            [f"侧车文件写入路径逃逸任务包：{target}"]
        )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
