"""Tests for the pure offline quality baseline runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.quality_baseline.runner import (
    BenchmarkInput,
    collect_fixture_paths,
    evaluate_documents,
    load_fixture,
    main,
    report_to_json,
    run_quality_baseline,
    write_report,
)


FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "quality"
    / "fixtures"
    / "parsed_documents"
)
SAMPLES = tuple(
    FIXTURES / name
    for name in (
        "sdp-004-docling.json",
        "sdp-004-mineru.json",
        "sdp-004-fallback.json",
    )
)


def test_runner_builds_deterministic_parser_by_sample_matrix():
    first = run_quality_baseline(reversed(SAMPLES))
    second = run_quality_baseline(SAMPLES)

    assert first == second
    assert first["schema_name"] == "QualityBaselineReport"
    assert first["schema_version"] == "1.0"
    assert first["record_count"] == 3
    assert first["parser_count"] == 3
    assert 0.0 <= first["overall"]["quality_gate_pass_rate"] <= 1.0
    assert 0.0 <= first["overall"]["manual_review_required_rate"] <= 1.0
    assert [record["parser_id"] for record in first["records"]] == [
        "docling-local",
        "mineru-cloud",
        "pdfplumber-fallback",
    ]
    for record in first["records"]:
        assert len(record["fixture_sha256"]) == 64
        assert 0.0 <= record["structural_completeness"]["score"] <= 1.0
        assert "missing_or_non_available_count" in record["capabilities"]
        assert record["quality"]["gate_state"]
        assert isinstance(record["quality"]["issue_count"], int)
        assert isinstance(record["quality"]["repair_count"], int)


def test_runner_uses_parser_identity_only_as_a_report_dimension():
    fixture = load_fixture(SAMPLES[0])
    left = BenchmarkInput(
        sample_id="left",
        fixture_name="same.json",
        fixture_sha256="a" * 64,
        document=fixture.document.model_copy(
            update={
                "provenance": fixture.document.provenance.model_copy(
                    update={"parser_id": "parser-a"}
                )
            }
        ),
    )
    right = BenchmarkInput(
        sample_id="right",
        fixture_name="same.json",
        fixture_sha256="b" * 64,
        document=fixture.document.model_copy(
            update={
                "provenance": fixture.document.provenance.model_copy(
                    update={"parser_id": "parser-b"}
                )
            }
        ),
    )

    report = evaluate_documents((left, right))
    records = {record["parser_id"]: record for record in report["records"]}
    assert records["parser-a"]["structural_completeness"] == records["parser-b"][
        "structural_completeness"
    ]
    assert records["parser-a"]["capabilities"] == records["parser-b"][
        "capabilities"
    ]
    assert records["parser-a"]["quality"] == records["parser-b"]["quality"]


def test_duplicate_sample_ids_are_rejected():
    fixture = load_fixture(SAMPLES[0])
    duplicate = BenchmarkInput(
        sample_id=fixture.sample_id,
        fixture_name="duplicate.json",
        fixture_sha256="f" * 64,
        document=fixture.document,
    )

    with pytest.raises(ValueError, match="sample_id"):
        evaluate_documents((fixture, duplicate))


def test_cli_stdout_is_machine_readable_json(capsys):
    status = main(["--input", str(SAMPLES[0]), "--input", str(SAMPLES[1])])
    captured = capsys.readouterr()

    assert status == 0
    report = json.loads(captured.out)
    assert report["record_count"] == 2
    assert captured.err == ""
    assert report_to_json(report).endswith("\n")


def test_collect_paths_and_explicit_output_protection(tmp_path):
    paths = collect_fixture_paths(patterns=[str(FIXTURES / "sdp-004-*.json")])
    assert paths == tuple(sorted(SAMPLES))

    report = run_quality_baseline(paths)
    destination = tmp_path / "quality-baseline.json"
    assert write_report(report, destination) == destination
    assert json.loads(destination.read_text(encoding="utf-8")) == report
    with pytest.raises(FileExistsError):
        write_report(report, destination)
    write_report(report, destination, replace_existing=True)
