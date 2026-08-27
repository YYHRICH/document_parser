"""Exact table-HTML repair proposals derived from P3 representation decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from quality.contracts import ParsedTable
from quality.models_internal import EvidenceRef, RepairProposal
from quality.packaging.hashing import sha256_text
from quality.representations.inventory import RepresentationInventory
from quality.representations.models import RepresentationKind, RepresentationTarget
from quality.representations.tables import (
    TableRepresentationResolver,
    TableResolution,
    TableResolutionDecision,
)


@dataclass(frozen=True)
class TableRepairProposalPlan:
    proposals: tuple[RepairProposal, ...] = ()
    resolutions: tuple[TableResolution, ...] = ()
    audit: tuple[dict[str, str], ...] = ()


def plan_table_html_repairs(
    content: str,
    *,
    target: RepresentationTarget,
    inventory: RepresentationInventory,
    tables: Iterable[ParsedTable],
) -> TableRepairProposalPlan:
    """Plan only table HTML replacements that P3 proved safe.

    The mutated field is always the supplied document/block Markdown target.
    ParsedTable.html is retained as source evidence, and its exact descriptor is
    included in every proposal.  No parser identity participates in this flow.
    """
    resolver = TableRepresentationResolver()
    current = content
    proposals: list[RepairProposal] = []
    resolutions: list[TableResolution] = []
    audit: list[dict[str, str]] = []
    for table in tables:
        resolution = resolver.resolve(table, inventory)
        resolutions.append(resolution)
        html_descriptor = inventory.find(
            RepresentationKind.TABLE_HTML,
            object_id=table.table_id,
            field_path="html",
        )
        source_html = table.html or ""
        replacement = _safe_markdown_replacement(table, resolution)
        if html_descriptor is None or not source_html or replacement is None:
            audit.append(
                {
                    "table_id": table.table_id,
                    "decision": resolution.decision.value,
                    "status": "not_proposed",
                    "reason": resolution.reason or "no auto-safe table HTML conversion",
                }
            )
            continue
        occurrences = current.count(source_html)
        if occurrences != 1:
            audit.append(
                {
                    "table_id": table.table_id,
                    "decision": resolution.decision.value,
                    "status": "not_proposed",
                    "reason": (
                        "table HTML source must occur exactly once in the target "
                        f"representation; found {occurrences}"
                    ),
                }
            )
            continue
        before_hash = sha256_text(current)
        after = current.replace(source_html, replacement, 1)
        proposal = RepairProposal(
            rule_id="QL-RPR-003",
            description=(
                f"Convert table {table.table_id} HTML to parser-neutral Markdown."
            ),
            target=target,
            expected_content_sha256=before_hash,
            expected_after_sha256=sha256_text(after),
            affected_block_ids=[str(table.block_id)],
            evidence_refs=list(
                _dedupe_refs(
                    (
                        target.evidence_ref(value_sha256=before_hash),
                        *resolution.evidence_refs,
                        *html_descriptor.evidence_refs,
                    )
                )
            ),
            parameters={
                "operation": "table_html_to_markdown_target",
                "table_id": table.table_id,
                "source_html": source_html,
                "source_html_sha256": html_descriptor.content_sha256,
                "replacement_markdown": replacement,
                "source_representation_target": {
                    "object_type": html_descriptor.target.object_type,
                    "object_id": html_descriptor.target.object_id,
                    "field_path": html_descriptor.target.field_path,
                    "occurrence": html_descriptor.target.occurrence,
                    "stable_key": html_descriptor.target.stable_key,
                },
                "source_representation_fidelity": html_descriptor.fidelity.value,
                "resolution_decision": resolution.decision.value,
            },
            safety="auto_safe",
        )
        proposals.append(proposal)
        audit.append(
            {
                "table_id": table.table_id,
                "decision": resolution.decision.value,
                "status": "proposed_auto_safe",
                "reason": resolution.reason or "table HTML conversion is deterministic",
            }
        )
        current = after
    return TableRepairProposalPlan(
        proposals=tuple(proposals),
        resolutions=tuple(resolutions),
        audit=tuple(audit),
    )


def _safe_markdown_replacement(
    table: ParsedTable,
    resolution: TableResolution,
) -> str | None:
    if resolution.decision == TableResolutionDecision.AUTO_SAFE_HTML_TO_MARKDOWN:
        return resolution.generated_markdown
    if (
        resolution.decision == TableResolutionDecision.USE_TABLE_MARKDOWN
        and not resolution.has_spans
        and table.html
        and table.markdown
    ):
        # P3 has already checked structural consistency.  Reusing the supplied
        # Markdown avoids a second projection while retaining HTML as evidence.
        return table.markdown
    return None


def _dedupe_refs(refs: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    result: list[EvidenceRef] = []
    seen: set[tuple[str, str, str, str | None]] = set()
    for ref in refs:
        key = (ref.object_type, ref.object_id, ref.field_path, ref.value_sha256)
        if key not in seen:
            seen.add(key)
            result.append(ref)
    return tuple(result)
