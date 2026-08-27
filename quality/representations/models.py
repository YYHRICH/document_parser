"""Typed, immutable representations exposed to the quality layer.

A representation identifies one concrete field in ParsedDocument. It does not
store a mutable copy of the parser result; its hash and target are the
preconditions a future repair executor must check before writing a patch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from quality.contracts import EvidenceAvailability
from quality.models_internal import EvidenceObjectType, EvidenceRef


class RepresentationKind(StrEnum):
    DOCUMENT_MARKDOWN = "document_markdown"
    BLOCK_MARKDOWN = "block_markdown"
    TABLE_HTML = "table_html"
    TABLE_MARKDOWN = "table_markdown"
    TABLE_CELLS = "table_cells"
    OCR_SPANS = "ocr_spans"
    ASSET = "asset"
    NATIVE_ARTIFACT = "native_artifact"


class RepresentationFidelity(StrEnum):
    """Whether this representation is a faithful view of its source evidence."""

    LOSSLESS = "lossless"
    LOSSY = "lossy"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RepresentationTarget:
    """Exact ParsedDocument field locator.

    occurrence prevents collisions when a legacy parser emits duplicate object
    IDs. The combination of target and content hash is the repair precondition;
    parser_id is deliberately not part of the target.
    """

    object_type: EvidenceObjectType
    object_id: str
    field_path: str
    occurrence: int = 0

    def __post_init__(self) -> None:
        if not self.object_id:
            raise ValueError("representation target object_id must not be empty")
        if not self.field_path:
            raise ValueError("representation target field_path must not be empty")
        if self.occurrence < 0:
            raise ValueError("representation target occurrence must be non-negative")

    @property
    def stable_key(self) -> str:
        return (
            f"{self.object_type}:{self.object_id}:"
            f"{self.field_path}:{self.occurrence}"
        )

    @property
    def evidence_field_path(self) -> str:
        if self.occurrence == 0:
            return self.field_path
        return f"{self.field_path}[{self.occurrence}]"

    def evidence_ref(self, *, value_sha256: str) -> EvidenceRef:
        return EvidenceRef(
            object_type=self.object_type,
            object_id=self.object_id,
            field_path=self.evidence_field_path,
            value_sha256=value_sha256,
        )


@dataclass(frozen=True)
class RepresentationDescriptor:
    """One usable, partial, or unavailable representation."""

    kind: RepresentationKind
    target: RepresentationTarget
    content_sha256: str
    availability: EvidenceAvailability
    fidelity: RepresentationFidelity = RepresentationFidelity.UNKNOWN
    reason: str | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()
    derived_from: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.content_sha256) != 64:
            raise ValueError("representation content_sha256 must be a SHA-256 digest")
        if any(char not in "0123456789abcdef" for char in self.content_sha256.lower()):
            raise ValueError("representation content_sha256 must be hexadecimal")
        if (
            self.availability
            in {
                EvidenceAvailability.PARTIAL,
                EvidenceAvailability.UNAVAILABLE,
                EvidenceAvailability.FAILED,
            }
            and not self.reason
        ):
            raise ValueError("non-available representation requires a reason")
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "derived_from", tuple(self.derived_from))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def key(self) -> str:
        return f"{self.kind.value}|{self.target.stable_key}"
