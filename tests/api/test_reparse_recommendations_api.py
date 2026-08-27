from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.backend import create_app  # noqa: E402
from document_parser.core.contracts import ParserCapability  # noqa: E402
from document_parser.orchestration import ParseFailureKind, ParseJobStatus  # noqa: E402


class _CapabilityGateway:
    """Minimal gateway seam: the endpoint only needs a capability snapshot."""

    def __init__(
        self,
        capabilities: list[ParserCapability],
        *,
        server_allow_cloud: bool = False,
    ) -> None:
        self._capabilities = capabilities
        # Deliberately public-looking deployment state: endpoint policy must ignore it
        # until a Principal + CloudExecutionGrant contract exists.
        self.server_allow_cloud = server_allow_cloud
        self.list_calls = 0

    def list_parsers(self) -> list[ParserCapability]:
        self.list_calls += 1
        return [capability.model_copy(deep=True) for capability in self._capabilities]


def _capability(
    parser_id: str,
    *,
    requires_network: bool = False,
    available: bool = True,
    unavailable_reason: str | None = None,
) -> ParserCapability:
    return ParserCapability(
        parser_id=parser_id,
        provider="test-provider",
        display_name=parser_id,
        formats={".pdf"},
        requires_network=requires_network,
        available=available,
        unavailable_reason=unavailable_reason,
    )


def _create_job(
    client: TestClient,
    *,
    options: dict[str, object] | None = None,
):
    storage = client.app.state.storage
    return storage.create_job(
        parse_id=storage.new_parse_id(),
        source_filename="confidential-input.pdf",
        source_file_type="application/pdf",
        source_content=b"confidential source bytes",
        requested_parser_id="previous-parser",
        options=options or {},
    )


def _assert_public_payload_is_safe(value: object) -> None:
    forbidden_keys = {
        "auto_options",
        "blockers",
        "error",
        "message",
        "options",
        "package_path",
        "reason",
        "source_sha256",
    }
    if isinstance(value, dict):
        assert not (forbidden_keys & set(value))
        for nested in value.values():
            _assert_public_payload_is_safe(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_public_payload_is_safe(nested)


def test_quality_reparse_signal_returns_safe_candidates_without_option_values(tmp_path: Path) -> None:
    gateway = _CapabilityGateway(
        [_capability("local-parser"), _capability("generic-cloud", requires_network=True)]
    )
    with TestClient(create_app(storage_root=tmp_path, gateway=gateway, job_workers=1)) as client:
        storage = client.app.state.storage
        job = _create_job(
            client,
            options={"language": "zh", "api_token": "do-not-return-this"},
        )
        job = storage.save_job(job.model_copy(update={"quality_state": "reparse_required"}))

        response = client.get(f"/api/jobs/{job.parse_id}/reparse-recommendations")

    assert response.status_code == 200, response.text
    payload = response.json()
    recommendation = payload["recommendations"]
    assert recommendation is not None
    assert recommendation["signals"] == [
        {"source": "quality", "code": "reparse-required", "retryable": False}
    ]
    candidates = {item["parser_id"]: item for item in recommendation["candidates"]}
    assert candidates["local-parser"]["executable"] is True
    assert candidates["generic-cloud"]["executable"] is False
    assert recommendation["automatic"] == {
        "parser_id": "local-parser",
        "requires_cloud": False,
    }
    _assert_public_payload_is_safe(payload)
    serialized = json.dumps(payload)
    assert "do-not-return-this" not in serialized
    assert "confidential-input.pdf" not in serialized
    assert "confidential source bytes" not in serialized


def test_retryable_failure_signal_does_not_expose_raw_job_error(tmp_path: Path) -> None:
    gateway = _CapabilityGateway([_capability("local-parser")])
    with TestClient(create_app(storage_root=tmp_path, gateway=gateway, job_workers=1)) as client:
        storage = client.app.state.storage
        job = _create_job(client)
        failed = storage.save_job(
            job.transition(
                ParseJobStatus.FAILED,
                error="backend token=raw-secret must stay private",
                failure_kind=ParseFailureKind.TRANSIENT,
                retryable=True,
            )
        )

        response = client.get(f"/api/jobs/{failed.parse_id}/reparse-recommendations")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["recommendations"]["signals"] == [
        {"source": "failure", "code": "failure-transient", "retryable": True}
    ]
    _assert_public_payload_is_safe(payload)
    assert "raw-secret" not in json.dumps(payload)


def test_no_actionable_signal_returns_explicit_null_without_capability_lookup(tmp_path: Path) -> None:
    gateway = _CapabilityGateway([_capability("local-parser")])
    with TestClient(create_app(storage_root=tmp_path, gateway=gateway, job_workers=1)) as client:
        job = _create_job(client)

        response = client.get(f"/api/jobs/{job.parse_id}/reparse-recommendations")

    assert response.status_code == 200, response.text
    assert response.json() == {"parse_id": job.parse_id, "recommendations": None}
    assert gateway.list_calls == 0


def test_cloud_candidates_remain_blocked_without_identity_grant_even_if_requested_or_deployed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DOCUMENT_PARSER_ALLOW_CLOUD", "true")
    gateway = _CapabilityGateway(
        [_capability("generic-cloud", requires_network=True)],
        server_allow_cloud=True,
    )
    with TestClient(create_app(storage_root=tmp_path, gateway=gateway, job_workers=1)) as client:
        storage = client.app.state.storage
        job = _create_job(client, options={"allow_cloud": True})
        job = storage.save_job(job.model_copy(update={"quality_state": "reparse_required"}))

        response = client.get(f"/api/jobs/{job.parse_id}/reparse-recommendations")

    assert response.status_code == 200, response.text
    recommendation = response.json()["recommendations"]
    assert recommendation is not None
    assert recommendation["candidates"] == [
        {
            "parser_id": "generic-cloud",
            "executable": False,
            "replaces_current_parser": True,
            "requires_cloud": True,
        }
    ]
    assert recommendation["automatic"] is None
    _assert_public_payload_is_safe(response.json())

def test_capability_snapshot_failure_returns_a_generic_error(tmp_path: Path) -> None:
    class _FailingCapabilityGateway(_CapabilityGateway):
        def list_parsers(self) -> list[ParserCapability]:
            raise RuntimeError("authorization=raw-capability-secret")

    gateway = _FailingCapabilityGateway([])
    with TestClient(create_app(storage_root=tmp_path, gateway=gateway, job_workers=1)) as client:
        storage = client.app.state.storage
        job = _create_job(client)
        job = storage.save_job(job.model_copy(update={"quality_state": "reparse_required"}))

        response = client.get(f"/api/jobs/{job.parse_id}/reparse-recommendations")

    assert response.status_code == 503
    assert response.json() == {"detail": "Reparse recommendations are temporarily unavailable."}
    assert "raw-capability-secret" not in response.text

