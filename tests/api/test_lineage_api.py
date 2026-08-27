from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.backend import create_app  # noqa: E402
from document_parser.backend.schemas import LineageJobMetadataSummary  # noqa: E402


def _assert_no_private_storage_or_content(value: object) -> None:
    if isinstance(value, dict):
        assert "package_path" not in value
        assert "source_sha256" not in value
        for nested in value.values():
            _assert_no_private_storage_or_content(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_private_storage_or_content(nested)


def test_lineage_and_same_source_comparison_are_read_only_and_content_free(tmp_path: Path) -> None:
    with TestClient(create_app(storage_root=tmp_path, job_workers=1)) as client:
        storage = client.app.state.storage
        root = storage.create_job(
            parse_id=storage.new_parse_id(),
            source_filename="confidential-name.md",
            source_file_type="text/markdown",
            source_content=b"# Confidential body",
            requested_parser_id="docling",
            options={"language": "zh", "api_token": "not-for-public-output"},
        )
        child = storage.create_reparse_job(
            parent_parse_id=root.parse_id,
            requested_parser_id="mineru",
            options={"language": "en"},
        ).job
        grandchild = storage.create_reparse_job(
            parent_parse_id=child.parse_id,
            requested_parser_id="markitdown",
            options={"language": "en", "enable_ocr": True},
        ).job

        def fail_if_repository_is_enumerated() -> tuple[object, ...]:
            raise AssertionError("lineage must only walk the target parent chain")

        storage.iter_jobs = fail_if_repository_is_enumerated
        lineage_response = client.get(f"/api/jobs/{grandchild.parse_id}/lineage")
        assert lineage_response.status_code == 200, lineage_response.text
        lineage = lineage_response.json()
        assert lineage["parse_id"] == grandchild.parse_id
        assert lineage["root_parse_id"] == root.parse_id
        assert lineage["ancestor_count"] == 2
        assert lineage["lineage_complete"] is True
        assert lineage["lineage_integrity"] == "verified"
        assert [item["parse_id"] for item in lineage["items"]] == [
            root.parse_id,
            child.parse_id,
            grandchild.parse_id,
        ]
        assert [item["generation"] for item in lineage["items"]] == [0, 1, 2]
        assert all("cas_revision" in item and "revision" not in item for item in lineage["items"])
        assert lineage["items"][0]["request"]["options"]["keys"] == [
            "<redacted>",
            "language",
        ]
        assert all(item["structural_counts_available"] is False for item in lineage["items"])
        _assert_no_private_storage_or_content(lineage)
        assert "not-for-public-output" not in json.dumps(lineage)
        assert "confidential-name.md" not in json.dumps(lineage)

        comparison_response = client.get(
            "/api/jobs/compare",
            params={"left": root.parse_id, "right": grandchild.parse_id},
        )
        assert comparison_response.status_code == 200, comparison_response.text
        comparison = comparison_response.json()
        assert comparison["same_source"] is True
        assert comparison["source"] == {"file_type": "text/markdown", "size_bytes": 19}
        assert comparison["differences"]["requested_parser_changed"] is True
        assert comparison["differences"]["options_changed"] is True
        assert comparison["differences"]["structural_counts_delta"] is None
        _assert_no_private_storage_or_content(comparison)

        unrelated = storage.create_job(
            parse_id=storage.new_parse_id(),
            source_filename="other.md",
            source_file_type="text/markdown",
            source_content=b"not the same source",
            requested_parser_id="docling",
            options={},
        )
        rejected = client.get(
            "/api/jobs/compare",
            params={"left": root.parse_id, "right": unrelated.parse_id},
        )
        assert rejected.status_code == 409
        assert "same immutable source identity" in rejected.json()["detail"]


def test_lineage_schema_calls_the_persistence_counter_cas_not_business_revision() -> None:
    schema = LineageJobMetadataSummary.model_json_schema()
    description = schema["properties"]["cas_revision"]["description"]
    assert "CAS" in description
    assert "business" in description
