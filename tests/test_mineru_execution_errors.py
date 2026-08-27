"""MinerU real-runtime failures must surface as portable parser errors."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.core.contracts import DocumentSignals, ParseRequest  # noqa: E402
from document_parser.parsers.mineru import MinerUParser  # noqa: E402
from document_parser.parsers.mineru import mineru as mineru_module  # noqa: E402
from document_parser.parsers.ports import ParserExecutionError  # noqa: E402


def _request() -> ParseRequest:
    return ParseRequest(
        filename="paper.pdf",
        file_type="application/pdf",
        content=b"%PDF-1.7\nfixture",
        parser_id="mineru",
        options={},
    )


def _signals(request: ParseRequest) -> DocumentSignals:
    return DocumentSignals(
        extension=".pdf",
        size_bytes=len(request.content),
        has_text_layer=True,
    )


def test_cli_nonzero_exit_raises_safe_execution_error(monkeypatch) -> None:
    adapter = MinerUParser()
    completed = SimpleNamespace(
        returncode=17,
        stdout="api_key=cli-secret",
        stderr="Bearer cli-secret",
    )
    monkeypatch.setattr(mineru_module.subprocess, "run", lambda *args, **kwargs: completed)
    request = _request()

    with pytest.raises(ParserExecutionError) as captured:
        adapter._build_with_mineru_cli(request, _signals(request))

    error = captured.value
    assert error.parser_id == "mineru"
    assert error.failure_kind == "parser"
    assert error.retryable is False
    assert "17" in error.safe_message
    assert "cli-secret" not in str(error)


def test_cloud_client_import_failure_raises_safe_unavailable_error(monkeypatch) -> None:
    adapter = MinerUParser()

    def fail_import(_name: str):
        raise ModuleNotFoundError("cloud client api_key=cloud-secret")

    monkeypatch.setattr(mineru_module, "import_module", fail_import)
    request = _request()

    with pytest.raises(ParserExecutionError) as captured:
        adapter._build_with_mineru_cloud(request, _signals(request))

    error = captured.value
    assert error.failure_kind == "unavailable"
    assert error.retryable is False
    assert "cloud-secret" not in error.safe_message


def test_magic_pdf_timeout_raises_retryable_safe_execution_error(monkeypatch) -> None:
    adapter = MinerUParser()

    def timeout(*_args, **_kwargs):
        raise TimeoutError("Bearer magic-secret")

    monkeypatch.setattr(adapter, "_run_magic_pdf_pipeline", timeout)
    request = _request()

    with pytest.raises(ParserExecutionError) as captured:
        adapter._build_with_magic_pdf(request, _signals(request))

    error = captured.value
    assert error.failure_kind == "transient"
    assert error.retryable is True
    assert "magic-secret" not in error.safe_message


def test_zero_exit_without_mineru_sidecars_raises_parser_error(monkeypatch) -> None:
    adapter = MinerUParser()
    completed = SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(mineru_module.subprocess, "run", lambda *args, **kwargs: completed)
    request = _request()
    monkeypatch.setattr(
        adapter,
        "_build_native_result_from_output_dir",
        lambda *_args, **_kwargs: adapter._build_placeholder_native_result(
            request,
            _signals(request),
        ),
    )

    with pytest.raises(ParserExecutionError) as captured:
        adapter._build_with_mineru_cli(request, _signals(request))

    error = captured.value
    assert error.failure_kind == "parser"
    assert error.retryable is False
    assert "sidecars" in error.safe_message
