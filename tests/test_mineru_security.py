import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.common.url_security import (  # noqa: E402
    TrustedUrlError,
    resolve_trusted_redirect_url,
    validate_trusted_https_url,
)
from document_parser.core.contracts import DocumentSignals, ParseRequest  # noqa: E402
from document_parser.parsers.mineru import (  # noqa: E402
    MinerUConfigurationError,
    MinerUParser,
    MinerURequestOptionError,
    MinerUServiceConfig,
    MinerUUntrustedUrlError,
)


@pytest.mark.parametrize(
    "value",
    [
        "http://mineru.net/api/v4",
        "https://127.0.0.1/api/v4",
        "https://127.1/api/v4",
        "https://0x7f000001/api/v4",
        "https://mineru.net\\@attacker.invalid/api/v4",
        "https://mineru.net@attacker.invalid/api/v4",
        "https://attacker.invalid/api/v4",
    ],
)
def test_trusted_url_policy_rejects_untrusted_or_ambiguous_endpoints(value: str) -> None:
    with pytest.raises(TrustedUrlError):
        validate_trusted_https_url(value, trusted_hosts=("mineru.net",))


@pytest.mark.parametrize("host", ["127.0.0.1", "127.1", "0x7f000001"])
def test_trusted_host_policy_rejects_numeric_ip_forms(host: str) -> None:
    with pytest.raises(TrustedUrlError):
        validate_trusted_https_url(
            f"https://{host}/api/v4",
            trusted_hosts=(host,),
        )


def test_trusted_redirect_policy_rejects_cross_host_redirect() -> None:
    with pytest.raises(TrustedUrlError):
        resolve_trusted_redirect_url(
            "https://mineru.net/api/v4/tasks/1",
            "//attacker.invalid/metadata",
            trusted_hosts=("mineru.net",),
        )


@pytest.mark.parametrize(
    "option_name",
    [
        "api_base_url",
        "api_token",
        "authorization",
        "bearer_token",
        "mineru_api_base_url",
        "mineru_api_token",
        "mineru_server_url",
        "server_url",
        "native_output_dir",
    ],
)
def test_mineru_rejects_request_level_sensitive_options(option_name: str) -> None:
    adapter = MinerUParser()
    request = ParseRequest(
        filename="paper.pdf",
        file_type="application/pdf",
        content=b"%PDF-1.7\nfixture",
        parser_id="mineru",
        options={option_name: "untrusted-value"},
    )
    signals = DocumentSignals(extension=".pdf", size_bytes=len(request.content), has_text_layer=True)

    with pytest.raises(MinerURequestOptionError, match=option_name):
        adapter.build_native_result(request, signals)


def test_mineru_service_config_rejects_untrusted_environment_base_url(monkeypatch) -> None:
    monkeypatch.setenv("MINERU_API_BASE_URL", "https://attacker.invalid/api/v4")
    monkeypatch.delenv("MINERU_API_TRUSTED_HOSTS", raising=False)

    with pytest.raises(MinerUConfigurationError, match="endpoint policy"):
        MinerUServiceConfig.from_environment()


def test_mineru_service_config_allows_explicit_server_trust_policy(monkeypatch) -> None:
    monkeypatch.setenv("MINERU_API_TRUSTED_HOSTS", "mineru.test, results.mineru.test")
    monkeypatch.setenv("MINERU_API_BASE_URL", "https://mineru.test/api/v4")

    config = MinerUServiceConfig.from_environment()

    assert config.api_base_url == "https://mineru.test/api/v4"
    assert config.validate_callback_url(
        "https://results.mineru.test/download?id=signed",
        kind="result",
    ).endswith("?id=signed")


def test_mineru_rejects_untrusted_task_urls_before_poll_or_download() -> None:
    adapter = MinerUParser()
    config = MinerUServiceConfig.from_environment()

    with pytest.raises(MinerUUntrustedUrlError, match="status URL"):
        adapter._validated_task_info(
            {
                "task_id": "task-1",
                "status_url": "https://attacker.invalid/tasks/task-1",
                "result_url": "https://mineru.net/api/v4/tasks/task-1/result",
            },
            service_config=config,
        )


class _FakeResponse:
    def __init__(self, status_code: int, *, headers: dict[str, str] | None = None, payload=None) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload
        self.text = "fake response"
        self.closed = False

    def json(self):
        return self._payload

    def close(self) -> None:
        self.closed = True


class _SubmitClient:
    instances: list["_SubmitClient"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.post_calls: list[tuple[str, dict[str, str]]] = []
        type(self).instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def post(self, url, *, data, files, headers):
        self.post_calls.append((url, headers))
        return _FakeResponse(
            202,
            payload={
                "task_id": "task-1",
                "status_url": "https://attacker.invalid/tasks/task-1",
                "result_url": "https://mineru.net/api/v4/tasks/task-1/result",
            },
        )


class _SubmitHttpx:
    Client = _SubmitClient


def test_mineru_submission_disables_automatic_redirects_and_validates_api_urls(tmp_path: Path) -> None:
    _SubmitClient.instances.clear()
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.7\nfixture")
    adapter = MinerUParser()

    with pytest.raises(MinerUUntrustedUrlError, match="status URL"):
        adapter._submit_mineru_task(
            httpx=_SubmitHttpx,
            base_url="https://mineru.net/api/v4",
            source_path=source,
            form_data={},
            headers={"Authorization": "Bearer service-token"},
        )

    assert _SubmitClient.instances[0].kwargs["follow_redirects"] is False
    assert _SubmitClient.instances[0].post_calls[0][1]["Authorization"] == "Bearer service-token"


class _RedirectClient:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, *, headers: dict[str, str]):
        self.calls.append((url, headers))
        return self.responses.pop(0)


def test_mineru_rejects_untrusted_status_redirect_before_following() -> None:
    adapter = MinerUParser()
    config = MinerUServiceConfig.from_environment()
    client = _RedirectClient(
        [_FakeResponse(302, headers={"location": "https://attacker.invalid/internal"})]
    )

    with pytest.raises(MinerUUntrustedUrlError, match="redirect URL"):
        adapter._get_with_trusted_redirects(
            client,
            url="https://mineru.net/api/v4/tasks/task-1",
            headers={"Authorization": "Bearer service-token"},
            service_config=config,
            kind="status",
        )

    assert len(client.calls) == 1


def test_mineru_strips_authorization_on_trusted_cross_origin_redirect(monkeypatch) -> None:
    monkeypatch.setenv("MINERU_API_TRUSTED_HOSTS", "mineru.net, results.mineru.net")
    config = MinerUServiceConfig.from_environment()
    adapter = MinerUParser()
    expected = _FakeResponse(200, payload={"status": "completed"})
    client = _RedirectClient(
        [
            _FakeResponse(302, headers={"location": "https://results.mineru.net/tasks/task-1"}),
            expected,
        ]
    )

    response = adapter._get_with_trusted_redirects(
        client,
        url="https://mineru.net/api/v4/tasks/task-1",
        headers={"Authorization": "Bearer service-token", "Accept": "application/json"},
        service_config=config,
        kind="status",
    )

    assert response is expected
    assert client.calls[0][1]["Authorization"] == "Bearer service-token"
    assert "Authorization" not in client.calls[1][1]
    assert client.calls[1][1]["Accept"] == "application/json"

def test_mineru_service_config_disables_cloud_by_default(monkeypatch) -> None:
    monkeypatch.setenv("MINERU_API_BASE_URL", "https://mineru.net/api/v4")
    monkeypatch.delenv("DOCUMENT_PARSER_ALLOW_CLOUD", raising=False)

    config = MinerUServiceConfig.from_environment()

    assert config.allow_cloud is False

