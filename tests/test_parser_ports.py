from __future__ import annotations

from enum import Enum
from types import SimpleNamespace

import pytest

from document_parser.core.contracts import (
    DocumentSignals,
    ParseRequest,
    ParserCapability,
    RoutingDecision,
    RoutingMode,
)
from document_parser.composition.gateway import DocumentParserGateway
from document_parser.normalizers import NormalizationContext
from document_parser.parsers.anydoc import AnyDocParser
from document_parser.parsers.base import BaseParserAdapter
from document_parser.parsers.docling import DoclingParser
from document_parser.parsers.markitdown import MarkItDownParser
from document_parser.parsers.ocr import OcrParser
from document_parser.parsers.ports import (
    ParserBoundaryError,
    ParserExecutionError,
    ParserFailureKind,
    ParserPluginPort,
    normalize_failure_kind,
)
from document_parser.parsers.registry import build_capability_snapshot


class _PortAdapter(BaseParserAdapter):
    PARSER_ID = "port-fixture"
    DISPLAY_NAME = "Port fixture"
    NATIVE_FORMATS = {".md"}

    @property
    def capability(self) -> ParserCapability:
        return ParserCapability(
            parser_id=self.PARSER_ID,
            provider="tests",
            display_name=self.DISPLAY_NAME,
            formats=self.NATIVE_FORMATS,
            available=True,
        )

    def build_native_result(self, request: ParseRequest, signals: DocumentSignals):
        return self._build_placeholder_native_result(request, signals, parser_version="fixture")


class _FailingAdapter(_PortAdapter):
    PARSER_ID = "failing-plugin"
    DISPLAY_NAME = "Failing plugin"

    def build_native_result(self, request: ParseRequest, signals: DocumentSignals):
        raise RuntimeError("raw backend token=do-not-serialize")


class _FallbackAdapter(_PortAdapter):
    PARSER_ID = "fallback-plugin"
    DISPLAY_NAME = "Fallback plugin"


class _RejectedAdapter(_PortAdapter):
    PARSER_ID = "rejected-plugin"
    DISPLAY_NAME = "Rejected plugin"

    def build_native_result(self, request: ParseRequest, signals: DocumentSignals):
        raise ParserBoundaryError("request violates a parser security policy")


class _ExternalFailureKind(str, Enum):
    TRANSIENT = "transient"


def _request(*, extension: str = ".md", options: dict | None = None) -> ParseRequest:
    return ParseRequest(
        filename=f"fixture{extension}",
        file_type="text/markdown" if extension == ".md" else "application/octet-stream",
        content=b"# Fixture\n\nBody.",
        parser_id=None,
        options=options or {},
    )


def _signals(request: ParseRequest, extension: str = ".md") -> DocumentSignals:
    return DocumentSignals(extension=extension, size_bytes=len(request.content), has_text_layer=True)


def test_base_adapter_implements_all_plugin_ports_and_normalizes_independently() -> None:
    adapter = _PortAdapter()
    request = _request()
    signals = _signals(request)

    assert isinstance(adapter, ParserPluginPort)
    probe = adapter.probe(request, signals)
    assert probe.parser_id == adapter.PARSER_ID
    assert probe.supported is True
    assert probe.executable is True

    native = adapter.execute(request, signals)
    bundle = adapter.normalize_native(
        native,
        NormalizationContext.from_parse_request(request, signals),
    )
    assert bundle.provenance.parser_id == adapter.PARSER_ID
    assert bundle.markdown == "# Fixture\n\nBody."


def test_probe_snapshot_is_detached_from_plugin_instances() -> None:
    adapter = _PortAdapter()
    snapshot = build_capability_snapshot({adapter.PARSER_ID: adapter})

    assert len(snapshot) == 1
    snapshot[0].formats.add(".pdf")
    fresh = adapter.capability_snapshot()
    assert ".pdf" not in fresh.formats


def test_execution_error_accepts_strings_and_foreign_string_enums() -> None:
    assert normalize_failure_kind("transient") == "transient"
    assert normalize_failure_kind(_ExternalFailureKind.TRANSIENT) == "transient"

    error = ParserExecutionError(
        parser_id="fixture",
        failure_kind=ParserFailureKind.TRANSIENT,
        retryable=True,
        safe_message="Temporary parser failure",
    )
    assert error.failure_kind == "transient"
    assert error.retryable is True
    assert str(error) == "Temporary parser failure"


def test_unexpected_backend_error_is_typed_and_redacted() -> None:
    adapter = _FailingAdapter()
    request = _request()
    signals = _signals(request)

    with pytest.raises(ParserExecutionError) as captured:
        adapter.normalize(request, signals)

    error = captured.value
    assert error.parser_id == "failing-plugin"
    assert error.failure_kind == "parser"
    assert error.retryable is False
    assert "do-not-serialize" not in error.safe_message
    assert isinstance(error.__cause__, RuntimeError)


def test_expected_policy_boundary_error_is_not_reclassified_as_execution_failure() -> None:
    adapter = _RejectedAdapter()
    request = _request()
    signals = _signals(request)

    with pytest.raises(ParserBoundaryError, match="security policy"):
        adapter.execute(request, signals)


def test_docling_sidecar_stays_available_without_a_live_backend() -> None:
    adapter = DoclingParser()
    request = _request(
        extension=".pdf",
        options={
            "native_markdown": "# Sidecar\n\nBody.",
            "native_payload": {"blocks": [{"id": "title", "type": "title", "text": "Sidecar"}]},
        },
    )
    signals = _signals(request, ".pdf")

    bundle = adapter.normalize(request, signals)

    assert bundle.markdown == "# Sidecar\n\nBody."
    assert "native/full.md" in bundle.native_files
    assert "native/result.json" in bundle.native_files


def test_anydoc_nonzero_cli_exit_is_typed_and_does_not_expose_stderr(monkeypatch) -> None:
    adapter = AnyDocParser()
    request = _request(extension=".docx")
    signals = _signals(request, ".docx")

    monkeypatch.setattr(adapter, "_resolve_executable", lambda: "fake-anydoc")
    monkeypatch.setattr(
        "document_parser.parsers.anydoc.anydoc.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=2,
            stderr="api_token=secret-cli-output",
            stdout="",
        ),
    )

    with pytest.raises(ParserExecutionError) as captured:
        adapter.execute(request, signals)

    error = captured.value
    assert error.parser_id == "anydoc"
    assert error.failure_kind == "parser"
    assert "secret-cli-output" not in error.safe_message


def test_ocr_backend_failure_is_typed_and_pdf_is_not_advertised(monkeypatch) -> None:
    adapter = OcrParser()
    request = _request(extension=".png")
    signals = _signals(request, ".png")

    monkeypatch.setattr(
        "document_parser.parsers.ocr.ocr.find_spec",
        lambda _name: object(),
    )
    monkeypatch.setattr(
        adapter,
        "_build_with_rapidocr",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("credential=hidden")),
    )

    with pytest.raises(ParserExecutionError) as captured:
        adapter.execute(request, signals)

    assert captured.value.failure_kind == "parser"
    assert "hidden" not in captured.value.safe_message
    assert ".pdf" not in adapter.capability_snapshot().formats


def test_markitdown_exposes_the_same_plugin_port_surface() -> None:
    adapter = MarkItDownParser()

    assert isinstance(adapter, ParserPluginPort)
    assert adapter.probe().parser_id == "microsoft.markitdown"


class _AutoRouter:
    def route_request(self, request: ParseRequest) -> RoutingDecision:
        return RoutingDecision(
            mode=RoutingMode.AUTO,
            selected_parser_id="failing-plugin",
            fallback_parser_ids=["fallback-plugin"],
            allow_automatic_fallback=True,
            reason="plugin port fallback test",
            signals=DocumentSignals(extension=".md", size_bytes=len(request.content), has_text_layer=True),
        )


def test_typed_plugin_failure_reaches_gateway_fallback() -> None:
    gateway = DocumentParserGateway(router=_AutoRouter())
    gateway._adapters = {
        "failing-plugin": _FailingAdapter(),
        "fallback-plugin": _FallbackAdapter(),
    }

    parsed = gateway.parse(_request())

    assert parsed.provenance.parser_id == "fallback-plugin"
    assert len(parsed.provenance.fallback_history) == 1
    attempt = parsed.provenance.fallback_history[0]
    assert attempt.parser_id == "failing-plugin"
    assert attempt.failure_kind == "parser"
    assert attempt.retryable is False
