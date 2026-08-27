"""Build parser-neutral representations from ParsedDocument 2.2."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from quality.contracts import EvidenceAvailability, ParsedDocument
from quality.packaging.hashing import sha256_bytes, sha256_text, stable_json_bytes
from quality.representations.models import (
    RepresentationDescriptor,
    RepresentationFidelity,
    RepresentationKind,
    RepresentationTarget,
)


@dataclass(frozen=True)
class RepresentationInventory:
    """Immutable inventory of every quality-relevant ParsedDocument field."""

    document_id: str
    parser_id: str
    descriptors: tuple[RepresentationDescriptor, ...]
    _by_key: Mapping[str, RepresentationDescriptor] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        by_key: dict[str, RepresentationDescriptor] = {}
        for descriptor in self.descriptors:
            if descriptor.key in by_key:
                raise ValueError(f"duplicate representation descriptor: {descriptor.key}")
            by_key[descriptor.key] = descriptor
        object.__setattr__(self, "descriptors", tuple(self.descriptors))
        object.__setattr__(self, "_by_key", MappingProxyType(by_key))

    def for_kind(
        self,
        kind: RepresentationKind,
    ) -> tuple[RepresentationDescriptor, ...]:
        return tuple(item for item in self.descriptors if item.kind == kind)

    def find(
        self,
        kind: RepresentationKind,
        *,
        object_id: str,
        field_path: str,
        occurrence: int = 0,
    ) -> RepresentationDescriptor | None:
        target = RepresentationTarget(
            object_type=self._object_type_for(kind),
            object_id=object_id,
            field_path=field_path,
            occurrence=occurrence,
        )
        return self._by_key.get(f"{kind.value}|{target.stable_key}")

    def require(
        self,
        kind: RepresentationKind,
        *,
        object_id: str,
        field_path: str,
        occurrence: int = 0,
    ) -> RepresentationDescriptor:
        descriptor = self.find(
            kind,
            object_id=object_id,
            field_path=field_path,
            occurrence=occurrence,
        )
        if descriptor is None:
            raise KeyError(
                f"representation not found: {kind.value} {object_id}.{field_path}"
            )
        return descriptor

    @property
    def table_cells_status(self) -> tuple[EvidenceAvailability, str | None]:
        descriptors = self.for_kind(RepresentationKind.TABLE_CELLS)
        if not descriptors:
            return (
                EvidenceAvailability.UNAVAILABLE,
                "文档未提供任何 ParsedTable.cells 表示。",
            )
        states = {descriptor.availability for descriptor in descriptors}
        if states == {EvidenceAvailability.AVAILABLE}:
            return EvidenceAvailability.AVAILABLE, None
        if (
            EvidenceAvailability.AVAILABLE in states
            or EvidenceAvailability.PARTIAL in states
        ):
            return (
                EvidenceAvailability.PARTIAL,
                "仅部分表格具备可验证的 cells 网格，或解析器声明其为部分可用。",
            )
        if EvidenceAvailability.FAILED in states:
            return (
                EvidenceAvailability.FAILED,
                "表格 cells 表示包含失败的证据声明。",
            )
        return (
            EvidenceAvailability.UNAVAILABLE,
            "文档中的表格未提供可验证的 cells 网格。",
        )

    @property
    def ocr_spans_status(self) -> tuple[EvidenceAvailability, str | None]:
        descriptors = self.for_kind(RepresentationKind.OCR_SPANS)
        if not descriptors:
            return (
                EvidenceAvailability.UNAVAILABLE,
                "文档未提供 OCR spans 表示。",
            )
        descriptor = descriptors[0]
        return descriptor.availability, descriptor.reason

    @staticmethod
    def _object_type_for(kind: RepresentationKind) -> str:
        if kind == RepresentationKind.DOCUMENT_MARKDOWN:
            return "document"
        if kind == RepresentationKind.BLOCK_MARKDOWN:
            return "block"
        if kind in {
            RepresentationKind.TABLE_HTML,
            RepresentationKind.TABLE_MARKDOWN,
            RepresentationKind.TABLE_CELLS,
        }:
            return "table"
        if kind == RepresentationKind.OCR_SPANS:
            return "document"
        if kind == RepresentationKind.ASSET:
            return "asset"
        if kind == RepresentationKind.NATIVE_ARTIFACT:
            return "native_artifact"
        raise AssertionError(f"unsupported representation kind: {kind}")


class QualityInputAdapter:
    """Compatibility adapter from public ParsedDocument to quality inventory."""

    @classmethod
    def from_parsed_document(
        cls,
        parsed_document: ParsedDocument,
    ) -> RepresentationInventory:
        descriptors: list[RepresentationDescriptor] = []
        occurrences: Counter[tuple[str, str, str]] = Counter()

        def target(
            object_type: str,
            object_id: str,
            field_path: str,
        ) -> RepresentationTarget:
            counter_key = (object_type, object_id, field_path)
            occurrence = occurrences[counter_key]
            occurrences[counter_key] += 1
            return RepresentationTarget(
                object_type=object_type,
                object_id=object_id,
                field_path=field_path,
                occurrence=occurrence,
            )

        def descriptor(
            *,
            kind: RepresentationKind,
            item_target: RepresentationTarget,
            content_sha256: str,
            availability: EvidenceAvailability,
            fidelity: RepresentationFidelity,
            reason: str | None = None,
            metadata: Mapping[str, object] | None = None,
        ) -> None:
            descriptors.append(
                RepresentationDescriptor(
                    kind=kind,
                    target=item_target,
                    content_sha256=content_sha256,
                    availability=availability,
                    fidelity=fidelity,
                    reason=reason,
                    evidence_refs=(
                        item_target.evidence_ref(value_sha256=content_sha256),
                    ),
                    metadata=metadata or {},
                )
            )

        document_id = str(parsed_document.document_id)
        markdown_available = bool(parsed_document.markdown)
        document_markdown_hash = sha256_text(parsed_document.markdown)
        descriptor(
            kind=RepresentationKind.DOCUMENT_MARKDOWN,
            item_target=target("document", document_id, "markdown"),
            content_sha256=document_markdown_hash,
            availability=(
                EvidenceAvailability.AVAILABLE
                if markdown_available
                else EvidenceAvailability.UNAVAILABLE
            ),
            fidelity=RepresentationFidelity.LOSSLESS,
            reason=None if markdown_available else "ParsedDocument.markdown 为空。",
            metadata={"length": len(parsed_document.markdown)},
        )

        for block in parsed_document.blocks:
            value = block.markdown
            available = bool(value)
            block_hash = sha256_text(value)
            descriptor(
                kind=RepresentationKind.BLOCK_MARKDOWN,
                item_target=target("block", str(block.id), "markdown"),
                content_sha256=block_hash,
                availability=(
                    EvidenceAvailability.AVAILABLE
                    if available
                    else EvidenceAvailability.UNAVAILABLE
                ),
                fidelity=RepresentationFidelity.LOSSLESS,
                reason=None if available else "DocumentBlock.markdown 为空。",
                metadata={
                    "block_kind": block.kind.value,
                    "order_index": block.order_index,
                },
            )

        table_cells_capability = parsed_document.capabilities.get("table_cells")
        for table in parsed_document.tables:
            if table.html is not None:
                html_available = bool(table.html.strip())
                html_hash = sha256_text(table.html)
                descriptor(
                    kind=RepresentationKind.TABLE_HTML,
                    item_target=target("table", table.table_id, "html"),
                    content_sha256=html_hash,
                    availability=(
                        EvidenceAvailability.AVAILABLE
                        if html_available
                        else EvidenceAvailability.UNAVAILABLE
                    ),
                    fidelity=RepresentationFidelity.LOSSLESS,
                    reason=None if html_available else "ParsedTable.html 为空。",
                    metadata={"block_id": str(table.block_id)},
                )

            if table.markdown is not None:
                markdown_available = bool(table.markdown.strip())
                table_markdown_hash = sha256_text(table.markdown)
                descriptor(
                    kind=RepresentationKind.TABLE_MARKDOWN,
                    item_target=target("table", table.table_id, "markdown"),
                    content_sha256=table_markdown_hash,
                    availability=(
                        EvidenceAvailability.AVAILABLE
                        if markdown_available
                        else EvidenceAvailability.UNAVAILABLE
                    ),
                    fidelity=RepresentationFidelity.UNKNOWN,
                    reason=(
                        None
                        if markdown_available
                        else "ParsedTable.markdown 为空。"
                    ),
                    metadata={"block_id": str(table.block_id)},
                )

            cells_payload = [
                cell.model_dump(mode="json")
                for cell in table.cells
            ]
            cells_hash = sha256_bytes(stable_json_bytes(cells_payload))
            if not table.cells:
                cells_state = EvidenceAvailability.UNAVAILABLE
                cells_reason = "ParsedTable.cells 为空，无法验证物理表格网格。"
            elif table_cells_capability is None:
                cells_state = EvidenceAvailability.PARTIAL
                cells_reason = "table_cells 存在，但 capabilities 未声明其可靠性。"
            else:
                cells_state = table_cells_capability.state
                cells_reason = table_cells_capability.reason
            descriptor(
                kind=RepresentationKind.TABLE_CELLS,
                item_target=target("table", table.table_id, "cells"),
                content_sha256=cells_hash,
                availability=cells_state,
                fidelity=RepresentationFidelity.LOSSLESS,
                reason=cells_reason,
                metadata={
                    "block_id": str(table.block_id),
                    "cell_count": len(table.cells),
                    "has_spans": any(
                        cell.row_span > 1 or cell.col_span > 1
                        for cell in table.cells
                    ),
                },
            )

        ocr_capability = parsed_document.capabilities.get("ocr_confidence")
        ocr_payload = [
            span.model_dump(mode="json")
            for span in parsed_document.ocr_spans
        ]
        ocr_hash = sha256_bytes(stable_json_bytes(ocr_payload))
        if not parsed_document.ocr_spans:
            ocr_state = EvidenceAvailability.UNAVAILABLE
            if (
                ocr_capability is not None
                and ocr_capability.state == EvidenceAvailability.AVAILABLE
            ):
                ocr_reason = (
                    "ocr_confidence 声明为 available，但 ParsedDocument.ocr_spans "
                    "为空，不能作为可验证 OCR 证据。"
                )
            else:
                ocr_reason = (
                    getattr(ocr_capability, "reason", None)
                    or "ParsedDocument 未提供 OCR spans。"
                )
        elif ocr_capability is None:
            ocr_state = EvidenceAvailability.PARTIAL
            ocr_reason = "存在 OCR spans，但 capabilities 未声明其可靠性。"
        else:
            ocr_state = ocr_capability.state
            ocr_reason = ocr_capability.reason
        descriptor(
            kind=RepresentationKind.OCR_SPANS,
            item_target=target("document", document_id, "ocr_spans"),
            content_sha256=ocr_hash,
            availability=ocr_state,
            fidelity=RepresentationFidelity.LOSSLESS,
            reason=ocr_reason,
            metadata={"span_count": len(parsed_document.ocr_spans)},
        )

        for asset in parsed_document.assets:
            asset_hash = asset.sha256 or sha256_bytes(asset.content)
            descriptor(
                kind=RepresentationKind.ASSET,
                item_target=target("asset", asset.path, "content"),
                content_sha256=asset_hash,
                availability=EvidenceAvailability.AVAILABLE,
                fidelity=RepresentationFidelity.LOSSLESS,
                metadata={
                    "file_type": asset.file_type,
                    "kind": asset.kind.value,
                },
            )

        for artifact in parsed_document.native_artifacts:
            # The descriptor hashes its exact target field (path), not the
            # supplier-declared content digest. Provenance rules must still see
            # malformed declared digests instead of inventory construction
            # failing before those rules can report them.
            descriptor(
                kind=RepresentationKind.NATIVE_ARTIFACT,
                item_target=target("native_artifact", artifact.artifact_id, "path"),
                content_sha256=sha256_text(artifact.path),
                availability=EvidenceAvailability.AVAILABLE,
                fidelity=RepresentationFidelity.LOSSLESS,
                metadata={
                    "path": artifact.path,
                    "declared_sha256": artifact.sha256,
                    "artifact_type": artifact.artifact_type,
                    "required_for_quality": artifact.required_for_quality,
                },
            )

        return RepresentationInventory(
            document_id=document_id,
            parser_id=parsed_document.provenance.parser_id,
            descriptors=tuple(descriptors),
        )
