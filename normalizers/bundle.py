"""解析器原始输出与统一 ``ParsedDocument`` 之间的中间层。"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid5

from pydantic import BaseModel, Field

from ..core.contracts import (
    DocumentAsset,
    DocumentBlock,
    EvidenceCapability,
    EvidenceAvailability,
    NativeArtifact,
    OcrSpan,
    ParsedDocument,
    ParsedTable,
    ParseConfidence,
    ParserProvenance,
    RoutingDecision,
)


NORMALIZATION_NAMESPACE = UUID("11111111-1111-4111-8111-111111111111")


def stable_uuid(*parts: str) -> UUID:
    """根据稳定字符串生成确定性 UUID。"""

    payload = "\u241f".join(part or "" for part in parts)
    return uuid5(NORMALIZATION_NAMESPACE, payload)


def make_stable_document_id(
    source_sha256: str | None,
    *,
    parser_id: str,
    parser_version: str,
) -> UUID:
    """根据输入文件和解析器版本生成文档级稳定 ID。"""

    return stable_uuid("document", source_sha256 or "unknown-source", parser_id, parser_version)


def make_stable_block_id(
    *,
    document_id: UUID,
    source_block_id: str | None,
    order_index: int | None,
    kind: str,
    text: str | None,
) -> UUID:
    """根据块来源和顺序生成稳定 block ID。"""

    return stable_uuid(
        "block",
        str(document_id),
        source_block_id or "",
        str(order_index) if order_index is not None else "",
        kind,
        text or "",
    )


def make_stable_table_id(
    *,
    document_id: UUID,
    source_table_id: str | None,
    block_id: UUID,
) -> str:
    """根据文档和块身份生成稳定 table ID。"""

    if source_table_id:
        return source_table_id
    return str(stable_uuid("table", str(document_id), str(block_id)))


def available_capability(
    *,
    granularity: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> EvidenceCapability:
    """构造可用能力记录。"""

    return EvidenceCapability(
        state=EvidenceAvailability.AVAILABLE,
        granularity=granularity,
        evidence=evidence or {},
    )


def partial_capability(
    reason: str,
    *,
    granularity: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> EvidenceCapability:
    """构造部分可用能力记录。"""

    return EvidenceCapability(
        state=EvidenceAvailability.PARTIAL,
        granularity=granularity,
        reason=reason,
        evidence=evidence or {},
    )


def unavailable_capability(
    reason: str,
    *,
    granularity: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> EvidenceCapability:
    """构造不可用能力记录。"""

    return EvidenceCapability(
        state=EvidenceAvailability.UNAVAILABLE,
        granularity=granularity,
        reason=reason,
        evidence=evidence or {},
    )


def failed_capability(
    reason: str,
    *,
    granularity: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> EvidenceCapability:
    """构造失败能力记录。"""

    return EvidenceCapability(
        state=EvidenceAvailability.FAILED,
        granularity=granularity,
        reason=reason,
        evidence=evidence or {},
    )


class ParserNormalizationBundle(BaseModel):
    """Adapter 归一化后的中间层结果。

    这里保留所有质量层需要的证据，但不承担最终 Schema 版本标记。
    解析器只要能把各自的原始输出翻成这个中间包，就能继续交给统一的
    ``ParsedDocument`` / ``document_package`` 处理。
    """

    document_id: UUID
    filename: str
    file_type: str
    source_size_bytes: int | None = Field(default=None, ge=0)
    source_sha256: str | None = None
    routing_decision: RoutingDecision | None = None
    markdown: str
    blocks: list[DocumentBlock] = Field(default_factory=list)
    assets: list[DocumentAsset] = Field(default_factory=list)
    tables: list[ParsedTable] = Field(default_factory=list)
    ocr_spans: list[OcrSpan] = Field(default_factory=list)
    confidence: ParseConfidence
    provenance: ParserProvenance
    warnings: list[str] = Field(default_factory=list)
    native_artifacts: list[NativeArtifact] = Field(default_factory=list)
    native_files: dict[str, bytes] = Field(default_factory=dict)
    capabilities: dict[str, EvidenceCapability] = Field(default_factory=dict)
    alternatives: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def from_minimal_markdown(
        cls,
        *,
        document_id: UUID,
        filename: str,
        file_type: str,
        markdown: str,
        parser_id: str,
        parser_version: str,
        parser_parameters: dict[str, Any] | None = None,
        routing_decision: RoutingDecision | None = None,
        source_size_bytes: int | None = None,
        source_sha256: str | None = None,
        blocks: list[DocumentBlock] | None = None,
        confidence: ParseConfidence | None = None,
        capabilities: dict[str, EvidenceCapability] | None = None,
        warnings: list[str] | None = None,
        native_artifacts: list[NativeArtifact] | None = None,
        native_files: dict[str, bytes] | None = None,
        assets: list[DocumentAsset] | None = None,
        tables: list[ParsedTable] | None = None,
        ocr_spans: list[OcrSpan] | None = None,
        alternatives: list[dict[str, Any]] | None = None,
    ) -> "ParserNormalizationBundle":
        """为只返回 Markdown 或部分结构的解析器构造最小统一包。"""

        return cls(
            document_id=document_id,
            filename=filename,
            file_type=file_type,
            source_size_bytes=source_size_bytes,
            source_sha256=source_sha256,
            routing_decision=routing_decision,
            markdown=markdown,
            blocks=blocks or [],
            assets=assets or [],
            tables=tables or [],
            ocr_spans=ocr_spans or [],
            confidence=confidence or ParseConfidence(),
            provenance=ParserProvenance(
                parser_id=parser_id,
                version=parser_version,
                parameters=parser_parameters or {},
            ),
            warnings=warnings or [],
            native_artifacts=native_artifacts or [],
            native_files=native_files or {},
            capabilities=capabilities or {},
            alternatives=alternatives or [],
        )

    @classmethod
    def from_parsed_document(
        cls,
        parsed_document: ParsedDocument,
    ) -> "ParserNormalizationBundle":
        """把已成型的 ``ParsedDocument`` 转回中间包，便于适配器复用。"""

        return cls(
            document_id=parsed_document.document_id,
            filename=parsed_document.filename,
            file_type=parsed_document.file_type,
            source_size_bytes=parsed_document.source_size_bytes,
            source_sha256=parsed_document.source_sha256,
            routing_decision=parsed_document.routing_decision,
            markdown=parsed_document.markdown,
            blocks=parsed_document.blocks,
            assets=parsed_document.assets,
            tables=parsed_document.tables,
            ocr_spans=parsed_document.ocr_spans,
            confidence=parsed_document.confidence,
            provenance=parsed_document.provenance,
            warnings=parsed_document.warnings,
            native_artifacts=parsed_document.native_artifacts,
            native_files={},
            capabilities=parsed_document.capabilities,
            alternatives=parsed_document.alternatives,
        )

    def with_missing_capabilities(
        self,
        required_capabilities: dict[str, EvidenceCapability],
    ) -> "ParserNormalizationBundle":
        """补齐解析器未提供的能力说明，但不编造证据。"""

        merged = {**required_capabilities, **self.capabilities}
        return self.model_copy(update={"capabilities": merged})

    def to_parsed_document(self) -> ParsedDocument:
        """转换为最终统一协议。"""

        return ParsedDocument(
            document_id=self.document_id,
            filename=self.filename,
            file_type=self.file_type,
            source_size_bytes=self.source_size_bytes,
            source_sha256=self.source_sha256,
            routing_decision=self.routing_decision,
            markdown=self.markdown,
            blocks=self.blocks,
            assets=self.assets,
            tables=self.tables,
            ocr_spans=self.ocr_spans,
            confidence=self.confidence,
            provenance=self.provenance,
            warnings=self.warnings,
            native_artifacts=self.native_artifacts,
            capabilities=self.capabilities,
            alternatives=self.alternatives,
        )
