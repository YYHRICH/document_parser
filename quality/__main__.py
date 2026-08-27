"""Standalone command-line debugger for the quality layer."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from quality.api import load_parsed_document, run_quality, write_quality_package


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m quality",
        description="Run the quality layer against one ParsedDocument JSON file.",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to a ParsedDocument 2.2 JSON file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Write the validated QualityPackage artifact set to this directory.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Allow --output-dir to replace an existing package directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Write the full QualityPackage JSON to stdout instead of a summary.",
    )
    parser.add_argument(
        "--show-repairs",
        action="store_true",
        help="Append proposal, policy, execution, verification, and table repair audit JSON.",
    )
    return parser


def _summary(package) -> str:
    severities = Counter(issue.severity.value for issue in package.quality_report.issues)
    issue_counts = ", ".join(
        f"{severity}={count}" for severity, count in sorted(severities.items())
    ) or "none"
    return "\n".join(
        (
            f"document_id: {package.document_id}",
            f"state: {package.quality_report.state.value}",
            f"issues: {len(package.quality_report.issues)} ({issue_counts})",
            f"repairs: {len(package.quality_report.applied_repairs)}",
            "repair_proposals: "
            f"{package.quality_report.metrics.get('repair_proposal_count', 0)}",
        )
    )


def _repair_details(package) -> dict[str, object]:
    """Stable, readable audit view without changing the QualityPackage contract."""
    report = package.quality_report
    return {
        "applied_repairs": [
            {
                "repair_id": repair.repair_id,
                "rule_id": repair.rule_id,
                "target": repair.evidence.get("target"),
                "precondition": repair.evidence.get("precondition"),
                "policy": repair.evidence.get("policy"),
                "verification": repair.evidence.get("verification"),
                "parameters": repair.evidence.get("parameters"),
            }
            for repair in report.applied_repairs
        ],
        "repair_workflow_audit": report.metrics.get("repair_audit", []),
        "table_repair_audit": report.metrics.get("table_repair_audit", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        document = load_parsed_document(args.input.read_bytes())
        package = run_quality(document)
        if args.output_dir is not None:
            destination = write_quality_package(
                package,
                args.output_dir,
                replace_existing=args.replace_existing,
            )
            print(f"quality package written: {destination}", file=sys.stderr)
    except (OSError, ValidationError, ValueError) as error:
        print(f"quality: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(package.model_dump(mode="json"), ensure_ascii=True, indent=2))
    else:
        print(_summary(package))
        if args.show_repairs:
            print(json.dumps(_repair_details(package), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
