"""Public, standalone entry points for the quality layer.

``run_quality`` and the input-inspection helpers are pure in-memory operations.
Filesystem delivery is deliberately isolated in ``write_quality_package`` and
loaded only when a caller explicitly asks to write artifacts.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from quality.contracts import ParsedDocument, QualityPackage
from quality.config import QualityConfig
from quality.evidence.context import EvidenceContext
from quality.evidence.negotiation import CapabilityDeclaration
from quality.evidence.requirements import QualityEvidenceRequirements
from quality.pipeline import QUALITY_EVIDENCE_REQUIREMENTS, run_pipeline

if TYPE_CHECKING:
    from pathlib import Path


def load_parsed_document(
    payload: str | bytes | bytearray | Mapping[str, Any],
) -> ParsedDocument:
    """Validate a ParsedDocument 2.2-compatible JSON payload in memory."""

    if isinstance(payload, Mapping):
        return ParsedDocument.model_validate(payload)
    return ParsedDocument.model_validate_json(payload)


def get_quality_evidence_requirements() -> QualityEvidenceRequirements:
    """Return the immutable rule-to-evidence contract owned by quality."""

    return QUALITY_EVIDENCE_REQUIREMENTS


def inspect_quality_capabilities(
    parsed_document: ParsedDocument,
) -> CapabilityDeclaration:
    """Build the parser-neutral evidence declaration for one memory document."""

    return EvidenceContext(parsed_document).capability_declaration


def run_quality_json(
    payload: str | bytes | bytearray | Mapping[str, Any],
    *,
    config: QualityConfig | None = None,
) -> QualityPackage:
    """Validate JSON-compatible input and execute the deterministic pipeline."""

    return run_quality(load_parsed_document(payload), config=config)


def run_quality(
    parsed_document: ParsedDocument,
    *,
    config: QualityConfig | None = None,
) -> QualityPackage:
    """Run quality from ParsedDocument and QualityConfig only; never write files."""

    return run_pipeline(parsed_document, config=config)


def write_quality_package(
    package: QualityPackage,
    output_dir: "Path | str",
    *,
    replace_existing: bool = False,
) -> "Path":
    """Explicit I/O adapter that atomically writes a completed QualityPackage."""

    from pathlib import Path

    from quality.packaging.writer import write_package_directory

    return write_package_directory(
        package,
        Path(output_dir),
        replace_existing=replace_existing,
    )
