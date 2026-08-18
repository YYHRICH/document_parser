"""修复候选的确定性安全校验。"""

from __future__ import annotations

from collections import Counter
import hashlib
import re

from document_parser.core.contracts import ParsedDocument

from quality.agent.models import CandidateValidation, RepairedDocumentCandidate
from quality.agent.revision import (
    DocumentRevision,
    materialize_revision_candidate,
    parse_block_id,
)

_TOKEN_RE = re.compile(r"https?://[^\s]+|[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|[\u4e00-\u9fff]+")


def content_fingerprint(markdown: str) -> str:
    """提取事实词元后计算指纹，忽略 Markdown 空白和装饰符号。"""

    tokens = _TOKEN_RE.findall(markdown)
    return hashlib.sha256("\x1f".join(tokens).encode("utf-8")).hexdigest()


class CandidateValidator:
    """只接受基于当前 revision 且不改变事实词元的结构化候选。"""

    def validate(
        self,
        revision: DocumentRevision,
        candidate: RepairedDocumentCandidate,
        *,
        expected_page: int | None = None,
    ) -> CandidateValidation:
        source_fp = content_fingerprint(revision.document.markdown)
        errors: list[str] = []
        if candidate.base_revision != revision.revision_id:
            errors.append("base_revision 与当前 revision 不一致。")

        self._validate_operation_ids(revision.document, candidate, errors)
        self._validate_removals(revision.document, candidate, errors)
        self._validate_scope(revision.document, candidate, errors, expected_page=expected_page)

        try:
            candidate_document, candidate_relations = materialize_revision_candidate(
                revision, candidate
            )
        except (TypeError, ValueError, KeyError) as exc:
            errors.append(f"候选 Patch 无法物化：{exc}")
            candidate_document = revision.document
            candidate_relations = revision.relation_overrides

        changed_ids = _changed_block_ids(revision.document, candidate_document)
        for operation in candidate.operations:
            if operation.operation == "move_block":
                for block_id in (operation.block_id, operation.before_block_id):
                    if block_id and block_id in {str(block.id) for block in revision.document.blocks}:
                        if block_id not in changed_ids:
                            changed_ids.append(block_id)
        changed_table_ids = _changed_table_ids(revision.document, candidate_document)
        changed_relation_keys = _changed_relation_keys(
            revision.relation_overrides, candidate_relations
        )
        changed_asset_paths = _changed_asset_paths(
            revision.document, candidate_document
        )
        declared_ids = set(candidate.affected_ids)
        expected_ids = set(changed_ids) | set(changed_table_ids)
        if declared_ids != expected_ids:
            errors.append("affected_ids 必须与实际改变的 block/table ID 完全一致。")
        explicit_relation_keys = {
            operation.relation.key()
            for operation in candidate.operations
            if operation.operation in {"upsert_relation", "remove_relation"}
            and operation.relation is not None
        }
        if set(candidate.affected_relation_keys) != explicit_relation_keys:
            errors.append("affected_relation_keys 必须与候选中的显式关系操作完全一致。")
        if set(candidate.affected_asset_paths) != set(changed_asset_paths):
            errors.append("affected_asset_paths 必须与实际改变的 asset 归属完全一致。")

        candidate_fp = content_fingerprint(candidate_document.markdown)
        if candidate.source_content_fingerprint not in {None, source_fp}:
            errors.append("候选声明的 source_content_fingerprint 与当前文档不一致。")
        if candidate_fp != source_fp:
            errors.append("候选改变了事实词元，质量层只允许格式/结构修复。")

        for before in revision.document.blocks:
            after = _by_id(candidate_document.blocks).get(str(before.id))
            if after is not None and before.markdown != after.markdown:
                if content_fingerprint(before.markdown) != content_fingerprint(after.markdown):
                    errors.append(f"block {before.id} 改变了事实词元。")

        for before in revision.document.tables:
            after = next(
                (table for table in candidate_document.tables if table.table_id == before.table_id),
                None,
            )
            if after is not None and _table_text_tokens(before) != _table_text_tokens(after):
                errors.append(f"table {before.table_id} 改变了单元格事实文本。")

        removed_ids = {
            operation.block_id
            for operation in candidate.operations
            if operation.operation == "remove_block" and operation.block_id
        }
        if _immutable_fields_changed(revision.document, candidate_document, allowed_removed_ids=removed_ids):
            errors.append("候选试图修改稳定身份、来源、资源或不可变字段。")

        if candidate.change_kind == "none" and expected_ids:
            errors.append("change_kind=none 不能同时包含实际结构变化。")

        no_progress = (
            revision.document.markdown == candidate_document.markdown
            and not changed_ids
            and not changed_table_ids
            and not changed_relation_keys
            and not changed_asset_paths
        )
        accepted = not errors
        return CandidateValidation(
            accepted=accepted,
            code="accepted" if accepted else "rejected_candidate",
            message=("候选通过确定性校验。" if accepted else "候选未通过确定性校验。"),
            errors=errors,
            no_progress=no_progress,
            changed_block_ids=changed_ids,
            changed_table_ids=changed_table_ids,
            changed_relation_keys=changed_relation_keys,
            changed_asset_paths=changed_asset_paths,
            base_revision=candidate.base_revision,
            source_content_fingerprint=source_fp,
            candidate_content_fingerprint=candidate_fp,
        )

    @staticmethod
    def _validate_operation_ids(
        document: ParsedDocument,
        candidate: RepairedDocumentCandidate,
        errors: list[str],
        *,
        expected_page: int | None = None,
    ) -> None:
        block_ids = {str(block.id) for block in document.blocks}
        table_ids = {table.table_id for table in document.tables}
        asset_paths = {asset.path for asset in document.assets}
        update_ids = set(candidate.block_markdown)
        invalid_ids = sorted(
            value for value in update_ids if parse_block_id(value) is None
        )
        unknown_ids = sorted(update_ids - block_ids)
        if invalid_ids:
            errors.append(f"block_markdown 包含非法 UUID：{invalid_ids}")
        if unknown_ids:
            errors.append(f"block_markdown 包含未知 block ID：{unknown_ids}")

        for operation in candidate.operations:
            if operation.block_id is not None:
                if parse_block_id(operation.block_id) is None:
                    errors.append(f"结构操作包含非法 block UUID：{operation.block_id}")
                elif operation.block_id not in block_ids:
                    errors.append(f"结构操作包含未知 block ID：{operation.block_id}")
            if operation.before_block_id is not None:
                if parse_block_id(operation.before_block_id) is None:
                    errors.append(
                        f"move_block 包含非法 before_block UUID：{operation.before_block_id}"
                    )
                elif operation.before_block_id not in block_ids:
                    errors.append(
                        f"move_block 包含未知 before_block ID：{operation.before_block_id}"
                    )
            if operation.table_id is not None and operation.table_id not in table_ids:
                errors.append(f"结构操作包含未知 table ID：{operation.table_id}")
            if operation.operation in {"upsert_relation", "remove_relation"}:
                relation = operation.relation
                if relation is None:
                    continue
                for endpoint_name, endpoint in (
                    ("from_id", relation.from_id),
                    ("to_id", relation.to_id),
                ):
                    if endpoint not in block_ids and endpoint not in asset_paths:
                        errors.append(
                            f"关系操作包含未知 {endpoint_name}：{endpoint}"
                        )
                if operation.operation == "upsert_relation" and relation.action != "upsert":
                    errors.append("upsert_relation 的 action 必须为 upsert。")
                if operation.operation == "remove_relation" and relation.action != "remove":
                    errors.append("remove_relation 的 action 必须为 remove。")
            if operation.operation == "update_asset_references":
                if operation.asset_path not in asset_paths:
                    errors.append(f"结构操作包含未知 asset path：{operation.asset_path}")
                for block_id in operation.referenced_by_block_ids:
                    if block_id not in block_ids:
                        errors.append(
                            f"asset 归属包含未知 referenced_by block ID：{block_id}"
                        )

    @staticmethod
    def _validate_removals(
        document: ParsedDocument,
        candidate: RepairedDocumentCandidate,
        errors: list[str],
    ) -> None:
        blocks = {str(block.id): block for block in document.blocks}
        fingerprints = Counter(
            content_fingerprint(block.markdown) for block in document.blocks
        )
        for operation in candidate.operations:
            if operation.operation != "remove_block" or operation.block_id not in blocks:
                continue
            fingerprint = content_fingerprint(blocks[operation.block_id].markdown)
            if fingerprints[fingerprint] < 2:
                errors.append(
                    f"remove_block {operation.block_id} 没有发现完全重复的 block 证据。"
                )

    @staticmethod
    def _validate_scope(
        document: ParsedDocument,
        candidate: RepairedDocumentCandidate,
        errors: list[str],
        *,
        expected_page: int | None = None,
    ) -> None:
        if expected_page is not None:
            if candidate.scope != "page" or expected_page not in candidate.scope_pages:
                errors.append(
                    f"页面循环要求 scope=page 且包含第 {expected_page} 页。"
                )
        if candidate.scope != "page" or not candidate.scope_pages:
            return
        if candidate.repaired_markdown is not None:
            errors.append("page scope 不能提交整篇 repaired_markdown，只能提交局部 Patch。")
        pages = set(candidate.scope_pages)
        block_pages = {
            str(block.id): block.anchor.page_number
            for block in document.blocks
        }
        table_pages = {table.table_id: table.page_number for table in document.tables}
        for object_id in candidate.affected_ids:
            page = block_pages.get(object_id, table_pages.get(object_id))
            if page not in pages:
                errors.append(
                    f"候选 scope_pages 不包含 affected ID {object_id} 的页码 {page}。"
                )
        asset_pages = {
            asset.path: asset.anchor.page_number if asset.anchor else None
            for asset in document.assets
        }
        for asset_path in candidate.affected_asset_paths:
            page = asset_pages.get(asset_path)
            if page not in pages:
                errors.append(
                    f"候选 scope_pages 不包含 asset {asset_path} 的页码 {page}。"
                )
        for operation in candidate.operations:
            if operation.operation not in {"upsert_relation", "remove_relation"}:
                continue
            relation = operation.relation
            if relation is None:
                continue
            endpoint_pages = []
            for endpoint in (relation.from_id, relation.to_id):
                endpoint_pages.append(
                    block_pages.get(endpoint, table_pages.get(endpoint, asset_pages.get(endpoint)))
                )
            if any(page not in pages for page in endpoint_pages if page is not None):
                errors.append(
                    f"候选 scope_pages 未覆盖关系端点：{relation.key()}。"
                )


def _by_id(blocks):
    return {str(block.id): block for block in blocks}


def _changed_block_ids(before: ParsedDocument, after: ParsedDocument) -> list[str]:
    before_map = _by_id(before.blocks)
    after_map = _by_id(after.blocks)
    changed = []
    for block_id in before_map:
        left, right = before_map[block_id], after_map.get(block_id)
        if right is None:
            changed.append(block_id)
            continue
        if left.markdown != right.markdown or left.heading_level != right.heading_level:
            changed.append(block_id)
    return changed


def _changed_table_ids(before: ParsedDocument, after: ParsedDocument) -> list[str]:
    before_map = {table.table_id: table for table in before.tables}
    after_map = {table.table_id: table for table in after.tables}
    return [
        table_id
        for table_id, left in before_map.items()
        if after_map.get(table_id) != left
    ]


def _relation_key(patch) -> str:
    return patch.key()


def _changed_relation_keys(before, after) -> list[str]:
    before_map = {_relation_key(patch): patch for patch in before}
    after_map = {_relation_key(patch): patch for patch in after}
    return sorted(
        key
        for key in set(before_map) | set(after_map)
        if before_map.get(key) != after_map.get(key)
    )


def _changed_asset_paths(before: ParsedDocument, after: ParsedDocument) -> list[str]:
    before_map = {asset.path: asset for asset in before.assets}
    after_map = {asset.path: asset for asset in after.assets}
    return sorted(
        path
        for path, left in before_map.items()
        if path in after_map
        and left.referenced_by_block_ids != after_map[path].referenced_by_block_ids
    )


def _table_text_tokens(table) -> Counter[str]:
    return Counter(_TOKEN_RE.findall(" ".join(cell.text for cell in table.cells)))


def _immutable_fields_changed(
    before: ParsedDocument,
    after: ParsedDocument,
    *,
    allowed_removed_ids: set[str] | None = None,
) -> bool:
    if before.model_copy(
        update={"markdown": "", "blocks": [], "tables": [], "assets": []}
    ).model_dump(mode="json") != after.model_copy(
        update={"markdown": "", "blocks": [], "tables": [], "assets": []}
    ).model_dump(mode="json"):
        return True

    before_blocks = _by_id(before.blocks)
    after_blocks = _by_id(after.blocks)
    allowed_removed_ids = allowed_removed_ids or set()
    removed_ids = set(before_blocks) - set(after_blocks)
    added_ids = set(after_blocks) - set(before_blocks)
    if added_ids or not removed_ids.issubset(allowed_removed_ids):
        return True
    for block_id, left in before_blocks.items():
        if block_id not in after_blocks:
            continue
        right = after_blocks[block_id]
        for field in (
            "id",
            "source_block_id",
            "kind",
            "native_type",
            "text",
            "anchor",
            "metadata",
        ):
            if getattr(left, field) != getattr(right, field):
                return True

    before_tables = {table.table_id: table for table in before.tables}
    after_tables = {table.table_id: table for table in after.tables}
    if set(before_tables) != set(after_tables):
        return True
    for table_id, left in before_tables.items():
        right = after_tables[table_id]
        for field in (
            "table_id",
            "block_id",
            "html",
            "markdown",
            "caption",
            "image_path",
            "page_number",
            "bbox",
            "metadata",
        ):
            if getattr(left, field) != getattr(right, field):
                return True
    before_assets = {asset.path: asset for asset in before.assets}
    after_assets = {asset.path: asset for asset in after.assets}
    if set(before_assets) != set(after_assets):
        return True
    for path, left in before_assets.items():
        right = after_assets[path]
        for field in (
            "path",
            "kind",
            "file_type",
            "content",
            "sha256",
            "width",
            "height",
            "anchor",
            "metadata",
        ):
            if getattr(left, field) != getattr(right, field):
                return True
    return False
