"""Deterministic offline quality baseline runner.

This module evaluates archived ``ParsedDocument`` fixtures only.  It does not
invoke a parser, router, Gateway, network service, or LLM.  ``parser_id`` is a
reported matrix dimension; it is never used to select rules or alter quality
behavior.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import glob
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

from pydantic import ValidationError

from quality import run_quality
from quality.contracts import BlockKind, ParsedDocument


REPORT_SCHEMA_NAME = "QualityBaselineReport"
REPORT_SCHEMA_VERSION = "1.0"
ISSUE_SEVERITIES = ("critical", "warning", "info")
CAPABILITY_STATES = ("available", "partial", "unavailable", "failed")
GATE_STATES = (
    "pass",
    "pass_with_warnings",
    "manual_review_required",
    "reparse_required",
    "rejected",
)


@dataclass(frozen=True)
class BenchmarkInput:
    """One fixture loaded entirely into memory before evaluation."""

    sample_id: str
    fixture_name: str
    fixture_sha256: str
    document: ParsedDocument

    def __post_init__(self) -> None:
        if not self.sample_id:
            raise ValueError("sample_id must not be empty")
        if not self.fixture_name:
            raise ValueError("fixture_name must not be empty")
        normalized_hash = self.fixture_sha256.lower()
        if len(normalized_hash) != 64 or any(
            character not in "0123456789abcdef" for character in normalized_hash
        ):
            raise ValueError("fixture_sha256 must be a SHA-256 hex digest")
        object.__setattr__(self, "fixture_sha256", normalized_hash)


def load_fixture(path: Path | str) -> BenchmarkInput:
    """Load one ParsedDocument fixture without invoking any parser runtime."""

    fixture_path = Path(path)
    raw = fixture_path.read_bytes()
    document = ParsedDocument.model_validate_json(raw)
    return BenchmarkInput(
        sample_id=fixture_path.stem,
        fixture_name=fixture_path.name,
        fixture_sha256=sha256(raw).hexdigest(),
        document=document,
    )


def _check(*, applicable: bool, passed: bool) -> dict[str, bool | None]:
    return {
        "applicable": applicable,
        "passed": passed if applicable else None,
    }


def structural_completeness(document: ParsedDocument) -> dict[str, Any]:
    """Measure contract-level structure without guessing semantic ground truth.

    The score is the ratio of passed applicable checks.  A non-applicable table
    or asset check is excluded from the denominator, not counted as a pass.
    """

    blocks = list(document.blocks)
    block_ids = [str(block.id) for block in blocks]
    block_by_id = {str(block.id): block for block in blocks}
    order_indices = [block.order_index for block in blocks]
    all_ordered = all(index is not None for index in order_indices)
    tables = list(document.tables)
    table_ids = [table.table_id for table in tables]
    assets = list(document.assets)

    table_links_valid = all(
        (
            (target := block_by_id.get(str(table.block_id))) is not None
            and target.kind == BlockKind.TABLE
        )
        for table in tables
    )
    asset_references_valid = all(
        referenced_id in block_by_id
        for asset in assets
        for referenced_id in asset.referenced_by_block_ids
    )

    checks = {
        "blocks_present": _check(
            applicable=True,
            passed=bool(blocks),
        ),
        "block_ids_unique": _check(
            applicable=bool(blocks),
            passed=bool(blocks) and len(block_ids) == len(set(block_ids)),
        ),
        "block_markdown_present": _check(
            applicable=bool(blocks),
            passed=bool(blocks) and all(bool(block.markdown.strip()) for block in blocks),
        ),
        "source_block_ids_complete": _check(
            applicable=bool(blocks),
            passed=bool(blocks) and all(bool(block.source_block_id) for block in blocks),
        ),
        "order_indices_complete": _check(
            applicable=bool(blocks),
            passed=bool(blocks) and all_ordered,
        ),
        "order_indices_unique": _check(
            applicable=bool(blocks) and all_ordered,
            passed=(
                bool(blocks)
                and all_ordered
                and len(order_indices) == len(set(order_indices))
            ),
        ),
        "table_ids_unique": _check(
            applicable=bool(tables),
            passed=len(table_ids) == len(set(table_ids)),
        ),
        "table_block_links_valid": _check(
            applicable=bool(tables),
            passed=table_links_valid,
        ),
        "asset_references_valid": _check(
            applicable=bool(assets),
            passed=asset_references_valid,
        ),
    }
    applicable_checks = [
        name for name, check in checks.items() if check["applicable"]
    ]
    passed_checks = [
        name
        for name in applicable_checks
        if checks[name]["passed"] is True
    ]
    score = (
        round(len(passed_checks) / len(applicable_checks), 6)
        if applicable_checks
        else 0.0
    )
    return {
        "score": score,
        "applicable_check_count": len(applicable_checks),
        "passed_check_count": len(passed_checks),
        "failed_checks": [
            name
            for name in applicable_checks
            if checks[name]["passed"] is False
        ],
        "checks": checks,
    }


def capability_summary(document: ParsedDocument) -> dict[str, Any]:
    """Summarize generic evidence declarations without parser-specific policy."""

    expected = ["page_bbox"] if document.blocks else []
    if document.tables:
        expected.append("table_cells")
    if document.ocr_spans:
        expected.append("ocr_confidence")

    declared = document.capabilities
    state_counts = Counter(
        capability.state.value for capability in declared.values()
    )
    declared_rows = [
        {
            "name": name,
            "state": capability.state.value,
            "granularity": capability.granularity,
            "reason": capability.reason,
        }
        for name, capability in sorted(declared.items())
    ]
    expected_undeclared = [name for name in expected if name not in declared]
    expected_non_available = [
        {
            "name": name,
            "state": declared[name].state.value,
            "reason": declared[name].reason,
        }
        for name in expected
        if name in declared and declared[name].state.value != "available"
    ]
    non_available = [
        {
            "name": name,
            "state": capability.state.value,
            "reason": capability.reason,
        }
        for name, capability in sorted(declared.items())
        if capability.state.value != "available"
    ]
    missing_names = {
        *expected_undeclared,
        *(entry["name"] for entry in expected_non_available),
    }
    return {
        "expected": expected,
        "declared_count": len(declared_rows),
        "declared": declared_rows,
        "state_counts": {
            state: state_counts.get(state, 0) for state in CAPABILITY_STATES
        },
        "expected_undeclared": expected_undeclared,
        "expected_non_available": expected_non_available,
        "all_non_available": non_available,
        "missing_or_non_available_count": len(missing_names),
    }


def quality_summary(document: ParsedDocument) -> dict[str, Any]:
    """Execute the unchanged quality layer and project its deterministic facts."""

    package = run_quality(document)
    report = package.quality_report
    issue_counts = Counter(issue.severity.value for issue in report.issues)
    repair_counts = Counter(repair.rule_id for repair in report.applied_repairs)
    quality_capability_counts = Counter(
        assessment.state.value
        for assessment in report.capability_matrix.values()
    )
    return {
        "gate_state": report.state.value,
        "issue_count": len(report.issues),
        "issue_counts_by_severity": {
            severity: issue_counts.get(severity, 0)
            for severity in ISSUE_SEVERITIES
        },
        "repair_count": len(report.applied_repairs),
        "repair_counts_by_rule": dict(sorted(repair_counts.items())),
        "quality_capability_state_counts": dict(
            sorted(quality_capability_counts.items())
        ),
        "gate_summary": {
            "critical_issue_count": report.gate_summary.critical_issue_count,
            "manual_review_issue_count": report.gate_summary.manual_review_issue_count,
            "warning_or_info_issue_count": report.gate_summary.warning_or_info_issue_count,
            "reparse_issue_count": report.gate_summary.reparse_issue_count,
            "capability_blockers": sorted(report.gate_summary.capability_blockers),
        },
    }


def evaluate_documents(inputs: Iterable[BenchmarkInput]) -> dict[str, Any]:
    """Evaluate in-memory fixtures and return a stable parser-by-sample matrix."""

    input_rows = tuple(inputs)
    if not input_rows:
        raise ValueError("at least one ParsedDocument fixture is required")
    sample_ids = [item.sample_id for item in input_rows]
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("sample_id values must be unique within one benchmark run")

    records: list[dict[str, Any]] = []
    for item in input_rows:
        document = item.document
        # Parser identity is recorded as a matrix key only.  The same call to
        # run_quality is made for every document without parser-specific logic.
        records.append(
            {
                "sample_id": item.sample_id,
                "fixture_name": item.fixture_name,
                "fixture_sha256": item.fixture_sha256,
                "document_id": str(document.document_id),
                "parser_id": document.provenance.parser_id,
                "parser_version": document.provenance.version,
                "input": {
                    "file_type": document.file_type,
                    "block_count": len(document.blocks),
                    "table_count": len(document.tables),
                    "asset_count": len(document.assets),
                    "ocr_span_count": len(document.ocr_spans),
                },
                "structural_completeness": structural_completeness(document),
                "capabilities": capability_summary(document),
                "quality": quality_summary(document),
            }
        )

    records.sort(
        key=lambda item: (
            item["parser_id"],
            item["sample_id"],
            item["fixture_sha256"],
        )
    )
    return {
        "schema_name": REPORT_SCHEMA_NAME,
        "schema_version": REPORT_SCHEMA_VERSION,
        "record_count": len(records),
        "parser_count": len({record["parser_id"] for record in records}),
        "records": records,
        "parser_summaries": _summarize_by_parser(records),
        "overall": _summarize_records(records),
    }


def _summarize_by_parser(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record["parser_id"])].append(record)
    return [
        {"parser_id": parser_id, **_summarize_records(grouped[parser_id])}
        for parser_id in sorted(grouped)
    ]


def _summarize_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    gate_counts = Counter(str(record["quality"]["gate_state"]) for record in records)
    structural_scores = [
        float(record["structural_completeness"]["score"])
        for record in records
    ]
    return {
        "sample_count": len(records),
        "mean_structural_completeness": (
            round(sum(structural_scores) / len(structural_scores), 6)
            if structural_scores
            else 0.0
        ),
        "capability_missing_or_non_available_count": sum(
            int(record["capabilities"]["missing_or_non_available_count"])
            for record in records
        ),
        "issue_count": sum(int(record["quality"]["issue_count"]) for record in records),
        "repair_count": sum(int(record["quality"]["repair_count"]) for record in records),
        "quality_gate_state_counts": {
            state: gate_counts.get(state, 0) for state in GATE_STATES
        },
        "quality_gate_pass_rate": (
            round(
                (
                    gate_counts.get("pass", 0)
                    + gate_counts.get("pass_with_warnings", 0)
                )
                / len(records),
                6,
            )
            if records
            else 0.0
        ),
        "manual_review_required_rate": (
            round(gate_counts.get("manual_review_required", 0) / len(records), 6)
            if records
            else 0.0
        ),
    }


def run_quality_baseline(paths: Iterable[Path | str]) -> dict[str, Any]:
    """Load fixture paths and evaluate them with no live parser execution."""

    return evaluate_documents(load_fixture(path) for path in paths)


def collect_fixture_paths(
    *,
    inputs: Iterable[Path | str] = (),
    patterns: Iterable[str] = (),
) -> tuple[Path, ...]:
    """Collect explicit paths and glob matches in a deterministic order."""

    candidates = [Path(value) for value in inputs]
    for pattern in patterns:
        candidates.extend(Path(value) for value in glob.glob(pattern, recursive=True))

    resolved: dict[str, Path] = {}
    for candidate in candidates:
        if not candidate.is_file():
            raise FileNotFoundError(f"fixture does not exist or is not a file: {candidate}")
        absolute = candidate.resolve()
        resolved[str(absolute).lower()] = absolute
    if not resolved:
        raise ValueError("no ParsedDocument fixture paths were supplied")
    return tuple(sorted(resolved.values(), key=lambda path: str(path).lower()))


def report_to_json(report: Mapping[str, Any]) -> str:
    """Serialize a report canonically for snapshots, CI artifacts, and diffs."""

    return json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        separators=(",", ": "),
    ) + "\n"


def write_report(
    report: Mapping[str, Any],
    output_path: Path | str,
    *,
    replace_existing: bool = False,
) -> Path:
    """Atomically write the report; overwriting requires explicit consent."""

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not replace_existing:
        raise FileExistsError(
            f"benchmark output already exists: {destination}; use --replace-existing"
        )

    payload = report_to_json(report)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            temporary_name = handle.name
        Path(temporary_name).replace(destination)
    except Exception:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise
    return destination


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m benchmarks.quality_baseline",
        description="Evaluate ParsedDocument fixtures through the deterministic quality layer.",
    )
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        type=Path,
        help="One ParsedDocument JSON fixture; repeat for multiple samples.",
    )
    parser.add_argument(
        "--glob",
        action="append",
        default=[],
        dest="patterns",
        help="Glob for ParsedDocument JSON fixtures; repeat for multiple patterns.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON report destination; stdout is used when omitted.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Allow --output to replace an existing report file.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point with deterministic stdout or an explicit JSON artifact."""

    args = _argument_parser().parse_args(argv)
    try:
        paths = collect_fixture_paths(inputs=args.input, patterns=args.patterns)
        report = run_quality_baseline(paths)
        if args.output is None:
            print(report_to_json(report), end="")
        else:
            destination = write_report(
                report,
                args.output,
                replace_existing=args.replace_existing,
            )
            print(f"quality baseline written: {destination}")
    except (FileNotFoundError, OSError, ValidationError, ValueError) as error:
        print(f"quality-baseline: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
