"""统一文档包加载器。

上游解析器可以把大型资源和原生结果放在文档包目录中，但质量层只应读取
``parsed_document.json`` 对应的统一 ``ParsedDocument 2.2``。本模块负责在交给
质量层前完成 JSON 校验、资源加载、路径约束和 sidecar 完整性校验。
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import ValidationError

from .contracts import ParsedDocument


class DocumentPackageError(ValueError):
    """统一文档包不满足交付契约时抛出的错误。"""


class DocumentPackageAdapter:
    """从统一文档包目录加载并验证 ``ParsedDocument 2.2``。"""

    DOCUMENT_FILENAME = "parsed_document.json"

    def __init__(self, *, verify_artifacts: bool = True) -> None:
        self.verify_artifacts = verify_artifacts

    def load(self, package_dir: str | Path) -> ParsedDocument:
        """加载一个文档包，并返回可直接交给质量层的统一对象。"""

        root = Path(package_dir)
        if not root.is_dir():
            raise DocumentPackageError(f"文档包目录不存在：{root}")

        document_path = root / self.DOCUMENT_FILENAME
        if not document_path.is_file():
            raise DocumentPackageError(
                f"文档包缺少必需文件：{self.DOCUMENT_FILENAME}"
            )

        try:
            payload = json.loads(document_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DocumentPackageError(
                f"无法读取 {self.DOCUMENT_FILENAME}：{exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise DocumentPackageError("parsed_document.json 顶层必须是 JSON 对象。")

        hydrated_payload = self._hydrate_asset_sidecars(root, payload)
        try:
            document = ParsedDocument.model_validate(hydrated_payload)
        except ValidationError as exc:
            raise DocumentPackageError(
                f"parsed_document.json 不是合法 ParsedDocument 2.2：{exc}"
            ) from exc

        if document.schema_name != "ParsedDocument" or document.schema_version != "2.2":
            raise DocumentPackageError(
                "统一文档包必须使用 schema_name=ParsedDocument、schema_version=2.2。"
            )

        self._validate_references(root, document)
        if self.verify_artifacts:
            self._verify_assets(root, document)
            self._verify_native_artifacts(root, document)
        return document

    def _hydrate_asset_sidecars(
        self, root: Path, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """把 assets/ 下的 sidecar bytes 注入 JSON，再交给 Pydantic 解码。"""

        result = dict(payload)
        raw_assets = result.get("assets", [])
        if not isinstance(raw_assets, list):
            return result

        assets: list[Any] = []
        for index, raw_asset in enumerate(raw_assets):
            if not isinstance(raw_asset, dict):
                assets.append(raw_asset)
                continue
            asset = dict(raw_asset)
            path_value = asset.get("path")
            if not isinstance(path_value, str):
                assets.append(asset)
                continue
            sidecar = self._safe_path(root, path_value, f"assets[{index}].path")
            if sidecar.is_file():
                if "content" not in asset:
                    asset["content"] = base64.b64encode(sidecar.read_bytes()).decode(
                        "ascii"
                    )
            elif "content" not in asset:
                raise DocumentPackageError(
                    f"资源不存在且未内嵌：{path_value}"
                )
            assets.append(asset)
        result["assets"] = assets
        return result

    def _validate_references(self, root: Path, document: ParsedDocument) -> None:
        """校验统一层生成的跨对象引用不会悬空。"""

        block_ids = {str(block.id) for block in document.blocks}
        asset_paths = {asset.path for asset in document.assets}

        for asset in document.assets:
            for block_id in asset.referenced_by_block_ids:
                if block_id not in block_ids:
                    raise DocumentPackageError(
                        f"资源 {asset.path} 引用了不存在的 block：{block_id}"
                    )
            self._safe_path(root, asset.path, "asset.path")

        for table in document.tables:
            if str(table.block_id) not in block_ids:
                raise DocumentPackageError(
                    f"表格 {table.table_id} 引用了不存在的 block：{table.block_id}"
                )
            if table.image_path is not None:
                self._safe_path(root, table.image_path, "table.image_path")
                if table.image_path not in asset_paths:
                    raise DocumentPackageError(
                        f"表格 {table.table_id} 的 image_path 未出现在 assets："
                        f"{table.image_path}"
                    )

        for artifact in document.native_artifacts:
            self._safe_path(root, artifact.path, "native_artifact.path")

    def _verify_assets(self, root: Path, document: ParsedDocument) -> None:
        for asset in document.assets:
            content = asset.content
            sidecar = self._safe_path(root, asset.path, "asset.path")
            if sidecar.is_file() and sidecar.read_bytes() != content:
                raise DocumentPackageError(
                    f"资源内嵌内容与 sidecar 不一致：{asset.path}"
                )
            if asset.sha256 is not None:
                actual = _sha256_bytes(content)
                if actual != asset.sha256:
                    raise DocumentPackageError(
                        f"资源 SHA-256 不匹配：{asset.path}"
                    )

    def _verify_native_artifacts(
        self, root: Path, document: ParsedDocument
    ) -> None:
        for artifact in document.native_artifacts:
            path = self._safe_path(root, artifact.path, "native_artifact.path")
            if not path.is_file():
                raise DocumentPackageError(
                    f"native artifact 不存在：{artifact.path}"
                )
            if path.stat().st_size != artifact.size_bytes:
                raise DocumentPackageError(
                    f"native artifact 大小不匹配：{artifact.path}"
                )
            if _sha256_file(path) != artifact.sha256:
                raise DocumentPackageError(
                    f"native artifact SHA-256 不匹配：{artifact.path}"
                )

    @staticmethod
    def _safe_path(root: Path, relative_path: str, field_name: str) -> Path:
        """解析 POSIX 相对路径，拒绝绝对路径、盘符和父目录跳转。"""

        normalized = relative_path.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if (
            not normalized
            or pure.is_absolute()
            or Path(normalized).drive
            or ".." in pure.parts
        ):
            raise DocumentPackageError(
                f"{field_name} 必须是安全的包内相对路径：{relative_path}"
            )
        candidate = (root / Path(*pure.parts)).resolve()
        root_resolved = root.resolve()
        if candidate != root_resolved and root_resolved not in candidate.parents:
            raise DocumentPackageError(
                f"{field_name} 超出文档包目录：{relative_path}"
            )
        return candidate


def load_document_package(
    package_dir: str | Path, *, verify_artifacts: bool = True
) -> ParsedDocument:
    """加载统一文档包的便捷函数。"""

    return DocumentPackageAdapter(verify_artifacts=verify_artifacts).load(package_dir)


# “Loader” 是对调用方更直观的兼容别名；业务文档统一称为 Adapter。
DocumentPackageLoader = DocumentPackageAdapter


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
