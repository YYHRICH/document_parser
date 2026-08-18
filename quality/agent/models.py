"""单文档质量修复 Agent 的结构化候选、作用域和 Patch 模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CandidateEvidenceRef(BaseModel):
    """候选引用的只读证据位置。"""

    object_type: str = Field(min_length=1)
    object_id: str = Field(min_length=1)
    field_path: str = Field(min_length=1)
    value_sha256: str | None = None


class TableCellPatch(BaseModel):
    """表格布局 Patch；文本保留用于事实词元校验。"""

    text: str
    start_row: int = Field(ge=0)
    start_col: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    col_span: int = Field(default=1, ge=1)
    column_header: bool = False
    row_header: bool = False


class RelationPatch(BaseModel):
    """对已有文档关系的最小覆盖；端点必须来自输入文档。"""

    action: Literal["upsert", "remove"] = "upsert"
    relation_type: str = Field(min_length=1)
    from_id: str = Field(min_length=1)
    to_id: str = Field(min_length=1)
    marker_key: str = ""

    def key(self) -> str:
        return "|".join(
            (self.relation_type, self.from_id, self.to_id, self.marker_key)
        )


class RepairOperation(BaseModel):
    """通用结构操作，不绑定某一种问题类型。"""

    operation: Literal[
        "update_block_markdown",
        "move_block",
        "update_heading_level",
        "remove_block",
        "replace_table_cells",
        "upsert_relation",
        "remove_relation",
        "update_asset_references",
    ]
    block_id: str | None = None
    before_block_id: str | None = None
    markdown: str | None = None
    heading_level: int | None = Field(default=None, ge=1, le=6)
    table_id: str | None = None
    cells: list[TableCellPatch] = Field(default_factory=list)
    relation: RelationPatch | None = None
    asset_path: str | None = None
    referenced_by_block_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_operation_payload(self) -> "RepairOperation":
        if self.operation in {
            "update_block_markdown",
            "move_block",
            "update_heading_level",
            "remove_block",
        } and not self.block_id:
            raise ValueError(f"{self.operation} 必须提供 block_id。")
        if self.operation == "update_block_markdown" and self.markdown is None:
            raise ValueError("update_block_markdown 必须提供 markdown。")
        if self.operation == "update_heading_level" and self.heading_level is None:
            raise ValueError("update_heading_level 必须提供 heading_level。")
        if self.operation == "replace_table_cells":
            if not self.table_id:
                raise ValueError("replace_table_cells 必须提供 table_id。")
            if not self.cells:
                raise ValueError("replace_table_cells 必须提供 cells。")
        if self.operation in {"upsert_relation", "remove_relation"}:
            if self.relation is None:
                raise ValueError(f"{self.operation} 必须提供 relation。")
            if self.operation == "upsert_relation" and self.relation.action != "upsert":
                raise ValueError("upsert_relation 的 relation.action 必须为 upsert。")
            if self.operation == "remove_relation" and self.relation.action != "remove":
                raise ValueError("remove_relation 的 relation.action 必须为 remove。")
        if self.operation == "update_asset_references":
            if not self.asset_path:
                raise ValueError("update_asset_references 必须提供 asset_path。")
            if len(self.referenced_by_block_ids) != len(set(self.referenced_by_block_ids)):
                raise ValueError("referenced_by_block_ids 不能重复。")
        return self


class RepairedDocumentCandidate(BaseModel):
    """LLM/Agent 提交的最小结构化修复候选。

    block_markdown 保留第一阶段兼容字段；新实现优先使用通用 operations。
    候选可以只携带局部 Patch，宿主负责在当前 revision 上物化完整文档。
    """

    schema_name: str = "RepairedDocumentCandidate"
    schema_version: str = "2.0"
    base_revision: str = Field(min_length=1)
    scope: Literal["document", "page", "region"] = "document"
    scope_pages: list[int] = Field(default_factory=list)
    repaired_markdown: str | None = None
    block_markdown: dict[str, str] = Field(default_factory=dict)
    operations: list[RepairOperation] = Field(default_factory=list)
    affected_ids: list[str] = Field(default_factory=list)
    affected_relation_keys: list[str] = Field(default_factory=list)
    affected_asset_paths: list[str] = Field(default_factory=list)
    lineage: list[str] = Field(default_factory=list)
    evidence_refs: list[CandidateEvidenceRef] = Field(default_factory=list)
    change_kind: Literal["format", "structure", "none"] = "format"
    reasoning: str = Field(min_length=1)
    source_content_fingerprint: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_lineage_and_scope(self) -> "RepairedDocumentCandidate":
        if self.base_revision not in self.lineage:
            raise ValueError("候选 lineage 必须包含 base_revision。")
        if len(self.affected_ids) != len(set(self.affected_ids)):
            raise ValueError("候选 affected_ids 不能重复。")
        if len(self.affected_relation_keys) != len(set(self.affected_relation_keys)):
            raise ValueError("候选 affected_relation_keys 不能重复。")
        if len(self.affected_asset_paths) != len(set(self.affected_asset_paths)):
            raise ValueError("候选 affected_asset_paths 不能重复。")
        if self.scope == "page" and not self.scope_pages:
            raise ValueError("page scope 必须提供 scope_pages。")
        if any(page < 1 for page in self.scope_pages):
            raise ValueError("scope_pages 必须从 1 开始。")
        return self


class CandidateValidation(BaseModel):
    """确定性验证器对一次候选的机器可读结论。"""

    accepted: bool
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    errors: list[str] = Field(default_factory=list)
    no_progress: bool = False
    changed_block_ids: list[str] = Field(default_factory=list)
    changed_table_ids: list[str] = Field(default_factory=list)
    changed_relation_keys: list[str] = Field(default_factory=list)
    changed_asset_paths: list[str] = Field(default_factory=list)
    base_revision: str
    source_content_fingerprint: str
    candidate_content_fingerprint: str
