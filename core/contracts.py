"""文档解析模块拥有的稳定领域协议。

维护约束：
1. 业务模块只应依赖这里的模型和顶层公开入口，不能依赖具体解析器返回格式。
2. 新解析器必须把私有结果转换为 ``ParsedDocument``，不能把第三方对象向外泄漏。
3. 修改字段含义或枚举值会影响所有调用方；不兼容变更必须提升
   ``ParsedDocument.schema_version``。
"""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any
from uuid import UUID, uuid4

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


def _validate_relative_path(value: str) -> str:
    """统一资源分隔符并拒绝绝对路径和父目录跳转。"""

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
        raise ValueError("path 必须是安全的相对文件路径。")
    return str(path)


def _validate_sha256(value: str) -> str:
    """校验并规范化 SHA-256 十六进制摘要。"""

    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError("SHA-256 必须是 64 位十六进制字符串。")
    return normalized


class BlockKind(StrEnum):
    """下游统一使用的文档块类型。"""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    IMAGE = "image"
    FORMULA = "formula"
    HEADER = "header"
    FOOTER = "footer"
    PAGE_NUMBER = "page_number"
    ASIDE = "aside"
    FOOTNOTE = "footnote"
    REFERENCE = "reference"


class AssetKind(StrEnum):
    """解析结果附属资源类型；当前统一输出重点覆盖图片。"""

    IMAGE = "image"
    ATTACHMENT = "attachment"
    TABLE_SNAPSHOT = "table_snapshot"


class RoutingMode(StrEnum):
    """模型由系统自动选择，或由用户明确指定。"""

    AUTO = "auto"
    MANUAL = "manual"


class EvidenceAvailability(StrEnum):
    """统一结果中某项原始证据的可用程度。"""

    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class ParseRequest(BaseModel):
    """提交给文档解析服务的统一请求。"""

    # 带扩展名的文件名，解析器据此判断输入格式。
    filename: str = Field(min_length=1)
    # 标准文件类型，例如 application/pdf；用于识别扩展名不可靠的上传文件。
    file_type: str = Field(min_length=1)
    # 本地文件的原始字节。
    content: bytes
    # 固定解析器 ID；保留字段用于结果追踪和后续兼容。
    parser_id: str | None = None
    # 传给具体解析器的参数；每个解析器会再次严格校验。
    options: dict[str, Any] = Field(default_factory=dict)


class DocumentSignals(BaseModel):
    """预检阶段产生的文件特征，供路由器选择能力。"""

    # 统一转为小写的文件扩展名，包含开头的点。
    extension: str
    # 本地内容字节数；远程 URL 未下载前通常为 0。
    size_bytes: int = Field(ge=0)
    # 可选页数，由更深入的预检器填写。
    page_count: int | None = Field(default=None, ge=0)
    # PDF 是否已有可复制文本层。
    has_text_layer: bool | None = None
    # 扫描页占比，0 表示纯数字文档，1 表示全扫描。
    scanned_page_ratio: float | None = Field(default=None, ge=0, le=1)
    # 可选语言提示，例如 zh、en。
    language_hint: str | None = None


class ParserCapability(BaseModel):
    """一个解析连接器声明的可用能力。"""

    # 全局唯一且稳定的解析器 ID。
    parser_id: str
    # 实现或服务提供方。
    provider: str
    # 面向使用者展示的中文名称。
    display_name: str
    # 支持的扩展名集合。
    formats: set[str]
    # 可选模型版本及默认版本。
    model_versions: list[str] = Field(default_factory=list)
    default_model_version: str | None = None
    # 能力运行前置条件。
    requires_network: bool = False
    requires_gpu: bool = False
    # 当前环境能否立即使用；不可用时同时给出原因。
    available: bool = True
    unavailable_reason: str | None = None


class RoutingDecision(BaseModel):
    """张云雅路由层交给统一接入层的稳定决策协议。"""

    schema_name: str = "RoutingDecision"
    schema_version: str = "1.0"
    mode: RoutingMode
    requested_parser_id: str | None = None
    selected_parser_id: str
    reason: str = Field(min_length=1)
    signals: DocumentSignals
    parser_options: dict[str, Any] = Field(default_factory=dict)
    fallback_parser_ids: list[str] = Field(default_factory=list)
    allow_automatic_fallback: bool = True
    unavailable_reasons: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_routing_mode(self) -> "RoutingDecision":
        """手动模式必须忠实执行用户选择，fallback 列表也不能自相矛盾。"""

        if self.mode == RoutingMode.MANUAL:
            if self.requested_parser_id is None:
                raise ValueError("手动路由必须提供 requested_parser_id。")
            if self.requested_parser_id != self.selected_parser_id:
                raise ValueError("手动路由的 requested_parser_id 必须等于 selected_parser_id。")
            if self.allow_automatic_fallback:
                raise ValueError("手动路由默认不得允许静默自动 fallback。")
        if self.selected_parser_id in self.fallback_parser_ids:
            raise ValueError("selected_parser_id 不能同时出现在 fallback_parser_ids。")
        if len(self.fallback_parser_ids) != len(set(self.fallback_parser_ids)):
            raise ValueError("fallback_parser_ids 不能包含重复模型。")
        return self


class NativeArtifact(BaseModel):
    """解析器原生产物的安全文件引用，不把大型 JSON/二进制塞入公共结果。"""

    artifact_id: str
    artifact_type: str
    path: str
    file_type: str
    size_bytes: int = Field(ge=0)
    sha256: str
    required_for_quality: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    _normalize_path = field_validator("path")(_validate_relative_path)
    _normalize_sha256 = field_validator("sha256")(_validate_sha256)


class EvidenceCapability(BaseModel):
    """声明某项 page/bbox/table/OCR 证据是否真实可用。"""

    state: EvidenceAvailability
    granularity: str | None = None
    reason: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_reason_for_missing_evidence(self) -> "EvidenceCapability":
        if self.state in {
            EvidenceAvailability.PARTIAL,
            EvidenceAvailability.UNAVAILABLE,
            EvidenceAvailability.FAILED,
        } and not self.reason:
            raise ValueError("非 available 能力必须说明 reason。")
        return self


class SourceAnchor(BaseModel):
    """文档块到原文的定位信息。"""

    # 页码从 1 开始；无分页格式可以为空。
    page_number: int | None = Field(default=None, ge=1)
    # 原页面坐标框：(左、上、右、下)。
    bbox: tuple[float, float, float, float] | None = None
    # 坐标解释所需的页面大小和坐标系，避免不同解析器 bbox 含义混淆。
    page_width: float | None = Field(default=None, gt=0)
    page_height: float | None = Field(default=None, gt=0)
    coordinate_system: str | None = None
    bbox_granularity: str | None = None
    provenance_status: str | None = None
    # 块所在的多级标题路径。
    section_path: list[str] = Field(default_factory=list)
    # 表格单元格坐标，例如 B3。
    table_cell: str | None = None
    # 解析前对应的原始文本，便于追溯。
    original_text: str | None = None


class DocumentBlock(BaseModel):
    """解析器无关的最小文档块。"""

    # 每个块的唯一标识。
    id: UUID = Field(default_factory=uuid4)
    # 解析器原始对象 ID 及统一阅读顺序；旧解析器可以暂时不提供。
    source_block_id: str | None = None
    order_index: int | None = Field(default=None, ge=0)
    # 标题、段落、表格等统一类型。
    kind: BlockKind
    native_type: str | None = None
    text: str | None = None
    heading_level: int | None = Field(default=None, ge=1)
    # 供下游直接使用的 Markdown 内容。
    markdown: str
    # 块在原文中的位置。
    anchor: SourceAnchor = Field(default_factory=SourceAnchor)
    # 解析器特有但非核心的信息。
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentAsset(BaseModel):
    """Markdown 引用的统一二进制资源。

    ``path`` 是相对于输出目录的 POSIX 路径，Markdown 可直接用它作为链接；
    ``content`` 在 Python 调用中保持 bytes，在 JSON 中自动编码为 URL-safe
    Base64。业务方可以统一遍历 assets 保存文件。
    """

    model_config = ConfigDict(
        ser_json_bytes="base64",
        val_json_bytes="base64",
    )

    # Markdown 使用的相对路径，例如 images/figure-1.png。
    path: str
    # 图片或其他附件；新增类型应保持向后兼容。
    kind: AssetKind
    # 标准文件类型，例如 image/png。
    file_type: str = Field(
        validation_alias=AliasChoices("file_type", "media_type")
    )
    # 原始二进制内容；repr=False 防止日志直接打印大量数据。
    content: bytes = Field(repr=False)
    sha256: str | None = None
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    anchor: SourceAnchor | None = None
    referenced_by_block_ids: list[str] = Field(default_factory=list)
    # 供应商特有但不影响通用保存逻辑的信息。
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        """统一资源分隔符并拒绝绝对路径和父目录跳转。"""

        return _validate_relative_path(value)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str | None) -> str | None:
        return None if value is None else _validate_sha256(value)


class OcrSpan(BaseModel):
    """图片或扫描页的行/词级 OCR 证据。"""

    level: str
    text: str
    bbox: tuple[float, float, float, float]
    confidence: float | None = Field(default=None, ge=0, le=1)
    page_number: int | None = Field(default=None, ge=1)
    rotation_angle: float | None = None


class TableCell(BaseModel):
    """解析器提供的物理表格网格单元。"""

    text: str
    start_row: int = Field(ge=0)
    start_col: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    col_span: int = Field(default=1, ge=1)
    column_header: bool = False
    row_header: bool = False
    bbox: tuple[float, float, float, float] | None = None


class ParsedTable(BaseModel):
    """朱统一层交给质量层的表格结构证据。"""

    table_id: str
    block_id: UUID
    html: str | None = None
    markdown: str | None = None
    caption: str | None = None
    image_path: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    bbox: tuple[float, float, float, float] | None = None
    num_rows: int | None = Field(default=None, ge=0)
    num_cols: int | None = Field(default=None, ge=0)
    cells: list[TableCell] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("image_path")
    @classmethod
    def validate_image_path(cls, value: str | None) -> str | None:
        return None if value is None else _validate_relative_path(value)


class FallbackAttempt(BaseModel):
    """路由 fallback 中一次实际失败或跳过的尝试。"""

    parser_id: str
    status: str
    reason: str
    duration_ms: int = Field(default=0, ge=0)


class ParseConfidence(BaseModel):
    """文本、布局、阅读顺序和表格的质量分。"""

    # 各分数范围均为 0～1，越高表示越可信。
    text: float = Field(default=1.0, ge=0, le=1)
    layout: float = Field(default=1.0, ge=0, le=1)
    reading_order: float = Field(default=1.0, ge=0, le=1)
    table: float = Field(default=1.0, ge=0, le=1)
    overall: float = Field(default=1.0, ge=0, le=1)


class ParserProvenance(BaseModel):
    """记录解析器、参数和耗时，保证结果可解释与复现。"""

    # 实际执行的解析器、模型和版本。
    parser_id: str
    requested_parser_id: str | None = None
    routing_mode: RoutingMode | None = None
    model: str | None = None
    version: str = "unknown"
    # 实际使用的解析参数。
    parameters: dict[str, Any] = Field(default_factory=dict)
    # 旧版 Office 转换、MarkItDown 和两者合计耗时，便于定位性能瓶颈。
    format_conversion_duration_ms: int = Field(default=0, ge=0)
    markitdown_duration_ms: int = Field(default=0, ge=0)
    parse_duration_ms: int = Field(
        default=0,
        ge=0,
        validation_alias=AliasChoices("parse_duration_ms", "elapsed_ms"),
    )
    peak_memory_mb: int | None = Field(default=None, ge=0)
    fallback_history: list[FallbackAttempt] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    """所有解析方式必须输出的稳定文档协议。

    外层调用统一读取 ``markdown``；需要结构化检索时读取 ``blocks``；需要保存
    图片时遍历 ``assets``。这三个字段在所有解析器结果中始终存在。
    """

    # 单次解析结果标识。
    document_id: UUID = Field(default_factory=uuid4)
    # 输入文件的基本信息。
    filename: str
    file_type: str = Field(
        validation_alias=AliasChoices("file_type", "media_type")
    )
    source_size_bytes: int | None = Field(default=None, ge=0)
    source_sha256: str | None = None
    routing_decision: RoutingDecision | None = None
    # 完整 Markdown 是业务层最直接的统一内容输出。
    markdown: str
    # 统一文档块和附属资源；无图片时 assets 为空列表。
    blocks: list[DocumentBlock]
    assets: list[DocumentAsset] = Field(default_factory=list)
    tables: list[ParsedTable] = Field(default_factory=list)
    ocr_spans: list[OcrSpan] = Field(default_factory=list)
    # 质量评价和执行来源。
    confidence: ParseConfidence
    provenance: ParserProvenance
    warnings: list[str] = Field(default_factory=list)
    native_artifacts: list[NativeArtifact] = Field(default_factory=list)
    capabilities: dict[str, EvidenceCapability] = Field(default_factory=dict)
    # 可选候选结果，为后续多模型复核保留。
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    # 协议名称和版本用于跨模块兼容判断。
    schema_name: str = "ParsedDocument"
    schema_version: str = "2.2"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("source_sha256")
    @classmethod
    def validate_source_sha256(cls, value: str | None) -> str | None:
        return None if value is None else _validate_sha256(value)


class QualityState(StrEnum):
    """整篇文档的最终准入状态。"""

    PASS = "pass"
    PASS_WITH_WARNINGS = "pass_with_warnings"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"
    REPARSE_REQUIRED = "reparse_required"
    REJECTED = "rejected"


class QualityCapabilityState(StrEnum):
    """Canonical 中某项能力或关系的证据状态。"""

    VERIFIED = "verified"
    INFERRED = "inferred"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"
    REPARSE_REQUIRED = "reparse_required"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


class IssueSeverity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class IssueStatus(StrEnum):
    UNFIXED = "unfixed"
    REPAIRED = "repaired"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"
    REPARSE_REQUIRED = "reparse_required"
    REJECTED = "rejected"


class CanonicalSourceLocator(BaseModel):
    """质量层节点、关系或字段绑定回到解析器原始证据的位置。"""

    source_block_id: str
    page_number: int | None = Field(default=None, ge=1)
    bbox: tuple[float, float, float, float] | None = None
    bbox_granularity: str | None = None
    provenance_status: QualityCapabilityState


class CanonicalBlock(BaseModel):
    """质量层稳定文档节点。"""

    block_id: str
    kind: str
    order_index: int = Field(ge=0)
    content: str
    source_locator: CanonicalSourceLocator
    metadata: dict[str, Any] = Field(default_factory=dict)


class TableFieldBinding(BaseModel):
    """行键、完整列路径和值之间的可回溯表格绑定。"""

    binding_id: str
    table_id: str
    block_id: str
    row_key: str
    column_path: list[str] = Field(min_length=1)
    value: str
    source_locator: CanonicalSourceLocator
    status: QualityCapabilityState
    evidence: dict[str, Any] = Field(default_factory=dict)


class CanonicalRelation(BaseModel):
    """标题、引用等文档内关系及其可验证依据。"""

    relation_id: str
    relation_type: str
    from_id: str
    to_id: str
    status: QualityCapabilityState
    evidence: dict[str, Any] = Field(default_factory=dict)


class CanonicalDocument(BaseModel):
    """带顺序、表格绑定、关系和来源的质量层文档图。"""

    schema_name: str = "CanonicalDocument"
    schema_version: str = "1.0"
    document_id: UUID
    blocks: list[CanonicalBlock]
    table_bindings: list[TableFieldBinding] = Field(default_factory=list)
    relations: list[CanonicalRelation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class QualityIssue(BaseModel):
    """一条可定位、可跟踪、可复核的质量问题。"""

    issue_id: str
    severity: IssueSeverity
    category: str
    status: IssueStatus
    message: str
    affected_block_ids: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class AppliedRepair(BaseModel):
    """一次实际执行且可回放的白名单修复。"""

    repair_id: str
    rule_id: str
    description: str
    affected_block_ids: list[str] = Field(default_factory=list)
    replayable: bool = True
    evidence: dict[str, Any] = Field(default_factory=dict)


class CapabilityAssessment(BaseModel):
    """质量层对单项能力的结论与数量证据。"""

    state: QualityCapabilityState
    evidence: dict[str, Any] = Field(default_factory=dict)


class GateSummary(BaseModel):
    """将 issues 和能力阻断项汇总为最终准入依据。"""

    critical_issue_count: int = Field(default=0, ge=0)
    manual_review_issue_count: int = Field(default=0, ge=0)
    warning_or_info_issue_count: int = Field(default=0, ge=0)
    reparse_issue_count: int = Field(default=0, ge=0)
    capability_blockers: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    critical_false_pass: bool = False


class ReparseRecommendation(BaseModel):
    """质量层返回给路由层的重新解析建议。"""

    parser_id: str
    reason: str = Field(min_length=1)
    parser_options: dict[str, Any] = Field(default_factory=dict)


class QualityReport(BaseModel):
    """质量层给编排、审核台和前端的正式报告。"""

    contract_version: str = "1.0"
    document_id: UUID
    state: QualityState
    artifacts: dict[str, str]
    issues: list[QualityIssue] = Field(default_factory=list)
    applied_repairs: list[AppliedRepair] = Field(default_factory=list)
    capability_matrix: dict[str, CapabilityAssessment]
    gate_summary: GateSummary
    metrics: dict[str, Any] = Field(default_factory=dict)
    reparse_recommendation: ReparseRecommendation | None = None

    @field_validator("artifacts")
    @classmethod
    def validate_artifact_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        return {key: _validate_sha256(digest) for key, digest in value.items()}

    @model_validator(mode="after")
    def validate_reparse_recommendation(self) -> "QualityReport":
        if (
            self.state == QualityState.REPARSE_REQUIRED
            and self.reparse_recommendation is None
        ):
            raise ValueError("reparse_required 必须提供 reparse_recommendation。")
        if self.gate_summary.critical_false_pass and self.state in {
            QualityState.PASS,
            QualityState.PASS_WITH_WARNINGS,
        }:
            raise ValueError("critical_false_pass=true 时禁止质量门放行。")
        return self


class PackageManifest(BaseModel):
    """四件套的契约版本和 SHA-256 绑定。"""

    contract_version: str = "1.0"
    artifacts: dict[str, str]

    @field_validator("artifacts")
    @classmethod
    def validate_manifest_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        required = {
            "optimized.md",
            "canonical_document.json",
            "quality_report.json",
        }
        missing = required - set(value)
        if missing:
            raise ValueError(f"package manifest 缺少核心产物：{sorted(missing)}")
        return {key: _validate_sha256(digest) for key, digest in value.items()}


class QualityPackage(BaseModel):
    """质量层交给朱的统一返回协议，对应最终四件套。"""

    schema_name: str = "QualityPackage"
    schema_version: str = "1.0"
    document_id: UUID
    optimized_markdown: str
    canonical_document: CanonicalDocument
    quality_report: QualityReport
    package_manifest: PackageManifest

    @model_validator(mode="after")
    def validate_document_identity(self) -> "QualityPackage":
        if self.document_id != self.canonical_document.document_id:
            raise ValueError("QualityPackage 与 CanonicalDocument 的 document_id 不一致。")
        if self.document_id != self.quality_report.document_id:
            raise ValueError("QualityPackage 与 QualityReport 的 document_id 不一致。")
        return self


class WikiCitation(BaseModel):
    """Wiki 知识块回指质量层最终证据的位置。"""

    citation_id: str
    canonical_block_id: str
    source_block_id: str
    page_number: int | None = Field(default=None, ge=1)
    bbox: tuple[float, float, float, float] | None = None
    table_id: str | None = None
    table_cell: str | None = None
    provenance_status: QualityCapabilityState
    evidence: dict[str, Any] = Field(default_factory=dict)


class WikiChunk(BaseModel):
    """交给 Wiki 索引层的最小可追溯知识块。"""

    chunk_id: str
    kind: str
    order_index: int = Field(ge=0)
    content: str
    citation_ids: list[str] = Field(default_factory=list)
    evidence_status: QualityCapabilityState
    metadata: dict[str, Any] = Field(default_factory=dict)


class WikiHandoff(BaseModel):
    """质量 Agent 完成后交给 Wiki 系统的稳定交接协议。"""

    schema_name: str = "WikiHandoff"
    schema_version: str = "1.0"
    document_id: UUID
    quality_state: QualityState
    optimized_markdown: str
    chunks: list[WikiChunk] = Field(default_factory=list)
    citations: list[WikiCitation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> "WikiHandoff":
        chunk_ids = {chunk.chunk_id for chunk in self.chunks}
        citation_ids = {citation.citation_id for citation in self.citations}
        if len(chunk_ids) != len(self.chunks):
            raise ValueError("WikiHandoff 的 chunk_id 不能重复。")
        if len(citation_ids) != len(self.citations):
            raise ValueError("WikiHandoff 的 citation_id 不能重复。")
        for chunk in self.chunks:
            missing = set(chunk.citation_ids) - citation_ids
            if missing:
                raise ValueError(
                    f"WikiChunk {chunk.chunk_id} 引用了不存在的 citation: {sorted(missing)}"
                )
        return self
