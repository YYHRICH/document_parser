import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser import (  # noqa: E402
    DocumentParserGateway,
    ParseConfidence,
    ParsedDocument,
    ParseRequest,
    ParserProvenance,
)
from document_parser.core.contracts import (  # noqa: E402
    DocumentSignals,
    ParserCapability,
    RoutingDecision,
    RoutingMode,
)
from document_parser.core import write_document_package  # noqa: E402
from document_parser.composition.gateway import GatewayParseError  # noqa: E402
from document_parser.routing import (  # noqa: E402
    CapabilityRegistry,
    CloudParserForbiddenError,
    ModelRouter,
    RoutingSettings,
)

from document_parser.parsers.registry import build_parser_registry, get_parser  # noqa: E402


def test_gateway_lists_registered_parsers() -> None:
    gateway = DocumentParserGateway.from_environment()

    parser_ids = {capability.parser_id for capability in gateway.list_parsers()}

    assert {"microsoft.markitdown", "docling", "mineru", "ocr"}.issubset(parser_ids)


def test_gateway_can_dispatch_to_docling_adapter() -> None:
    gateway = DocumentParserGateway.from_environment()
    request = ParseRequest(
        filename="sample.md",
        file_type="text/markdown",
        content=b"# Title\n\nBody.",
        parser_id="docling",
        options={},
    )

    parsed = gateway.parse(request)

    assert parsed.provenance.parser_id == "docling"
    assert parsed.routing_decision is not None
    assert parsed.routing_decision.selected_parser_id == "docling"
    assert parsed.markdown == "# Title\n\nBody."
    assert parsed.blocks[0].kind.value == "heading"


def test_gateway_preserves_markitdown_native_sidecars_for_durable_package(tmp_path: Path) -> None:
    pytest.importorskip("markitdown")
    gateway = DocumentParserGateway.from_environment()
    request = ParseRequest(
        filename="sidecar.md",
        file_type="text/markdown",
        content=b"# Sidecar\n\nBody.",
        parser_id="microsoft.markitdown",
        options={},
    )

    result = gateway.parse_for_package(request)

    assert "native/full.md" in result.native_files
    assert any(item.path == "native/full.md" for item in result.document.native_artifacts)
    write_document_package(
        result.document,
        tmp_path / "package",
        native_files=result.native_files,
    )
    assert (tmp_path / "package" / "native" / "full.md").is_file()


def test_parser_registry_resolves_known_adapters() -> None:
    registry = build_parser_registry()

    assert set(registry) == {"microsoft.markitdown", "anydoc", "docling", "mineru", "ocr"}
    assert get_parser("docling", registry).PARSER_ID == "docling"


def test_gateway_consumes_external_routing_decision() -> None:
    class FakeRouter:
        def route_request(self, request: ParseRequest) -> RoutingDecision:
            signals = DocumentSignals(
                extension=".md",
                size_bytes=len(request.content),
                has_text_layer=True,
            )
            return RoutingDecision(
                mode=RoutingMode.AUTO,
                selected_parser_id="docling",
                reason="test route",
                signals=signals,
                parser_options={"route_profile": "quality_first", "allow_cloud": True},
            )

    gateway = DocumentParserGateway(router=FakeRouter())
    request = ParseRequest(
        filename="sample.md",
        file_type="text/markdown",
        content=b"# Title\n\nBody.",
        parser_id=None,
        options={},
    )

    parsed = gateway.parse(request)

    assert parsed.provenance.parser_id == "docling"
    assert parsed.provenance.routing_mode == RoutingMode.AUTO
    assert parsed.provenance.requested_parser_id is None
    assert parsed.provenance.parameters["route_profile"] == "quality_first"


class _FixedRouter:
    def __init__(self, decision: RoutingDecision) -> None:
        self.decision = decision
        self.calls = 0

    def route_request(self, request: ParseRequest) -> RoutingDecision:
        self.calls += 1
        return self.decision


class _RecordingParser:
    def __init__(
        self,
        parser_id: str,
        calls: list[str],
        *,
        error: Exception | None = None,
    ) -> None:
        self.PARSER_ID = parser_id
        self._calls = calls
        self._error = error

    def parse(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParsedDocument:
        self._calls.append(self.PARSER_ID)
        if self._error is not None:
            raise self._error
        return ParsedDocument(
            filename=request.filename,
            file_type=request.file_type,
            markdown=f"# {self.PARSER_ID}",
            blocks=[],
            confidence=ParseConfidence(),
            provenance=ParserProvenance(parser_id=self.PARSER_ID),
        )


def _auto_decision(
    *,
    selected_parser_id: str,
    fallback_parser_ids: list[str],
    allow_automatic_fallback: bool = True,
) -> RoutingDecision:
    return RoutingDecision(
        mode=RoutingMode.AUTO,
        selected_parser_id=selected_parser_id,
        reason="test route",
        signals=DocumentSignals(
            extension=".md",
            size_bytes=12,
            has_text_layer=True,
        ),
        parser_options={"route_profile": "quality_first"},
        fallback_parser_ids=fallback_parser_ids,
        allow_automatic_fallback=allow_automatic_fallback,
    )


def test_gateway_executes_automatic_fallback_and_records_provenance() -> None:
    calls: list[str] = []
    router = _FixedRouter(
        _auto_decision(
            selected_parser_id="primary",
            fallback_parser_ids=["fallback", "unused"],
        )
    )
    gateway = DocumentParserGateway(router=router)
    gateway._adapters = {
        "primary": _RecordingParser(
            "primary",
            calls,
            error=TimeoutError("primary service timed out"),
        ),
        "fallback": _RecordingParser("fallback", calls),
        "unused": _RecordingParser("unused", calls),
    }

    parsed = gateway.parse(
        ParseRequest(
            filename="sample.md",
            file_type="text/markdown",
            content=b"# sample",
        )
    )

    assert calls == ["primary", "fallback"]
    assert router.calls == 1
    assert parsed.routing_decision is not None
    assert parsed.routing_decision.selected_parser_id == "primary"
    assert parsed.provenance.parser_id == "fallback"
    assert parsed.provenance.routing_mode == RoutingMode.AUTO
    assert parsed.provenance.requested_parser_id is None
    assert parsed.provenance.parameters["route_profile"] == "quality_first"
    assert len(parsed.provenance.fallback_history) == 1
    failed_attempt = parsed.provenance.fallback_history[0]
    assert failed_attempt.parser_id == "primary"
    assert failed_attempt.status == "failed"
    assert "TimeoutError" in failed_attempt.reason
    assert failed_attempt.duration_ms >= 0


def test_gateway_validates_explicit_parser_and_does_not_fallback() -> None:
    calls: list[str] = []
    router = ModelRouter(
        CapabilityRegistry.from_snapshot(
            [
                ParserCapability(
                    parser_id="primary",
                    provider="fixture",
                    display_name="Primary",
                    formats={".md"},
                ),
                ParserCapability(
                    parser_id="fallback",
                    provider="fixture",
                    display_name="Fallback",
                    formats={".md"},
                ),
            ]
        ),
        RoutingSettings(),
    )
    gateway = DocumentParserGateway(router=router)
    gateway._adapters = {
        "primary": _RecordingParser(
            "primary",
            calls,
            error=RuntimeError("explicit parser failed"),
        ),
        "fallback": _RecordingParser("fallback", calls),
    }

    with pytest.raises(RuntimeError, match="explicit parser failed"):
        gateway.parse(
            ParseRequest(
                filename="sample.md",
                file_type="text/markdown",
                content=b"# sample",
                parser_id="primary",
            )
        )

    assert calls == ["primary"]


def test_gateway_applies_policy_to_explicit_parser_request() -> None:
    calls: list[str] = []
    router = ModelRouter(
        CapabilityRegistry.from_snapshot(
            [
                ParserCapability(
                    parser_id="mineru",
                    provider="fixture",
                    display_name="Cloud parser",
                    formats={".pdf"},
                    requires_network=True,
                )
            ]
        ),
        RoutingSettings(allow_cloud=True),
    )
    gateway = DocumentParserGateway(router=router)
    gateway._adapters = {"mineru": _RecordingParser("mineru", calls)}

    with pytest.raises(CloudParserForbiddenError, match="mineru"):
        gateway.parse(
            ParseRequest(
                filename="sample.pdf",
                file_type="application/pdf",
                content=b"%PDF-fixture",
                parser_id="mineru",
                options={"allow_cloud": False},
            )
        )

    assert calls == []


def test_gateway_honors_disabled_automatic_fallback() -> None:
    calls: list[str] = []
    gateway = DocumentParserGateway(
        router=_FixedRouter(
            _auto_decision(
                selected_parser_id="primary",
                fallback_parser_ids=["fallback"],
                allow_automatic_fallback=False,
            )
        )
    )
    gateway._adapters = {
        "primary": _RecordingParser(
            "primary",
            calls,
            error=RuntimeError("primary failed"),
        ),
        "fallback": _RecordingParser("fallback", calls),
    }

    with pytest.raises(GatewayParseError) as captured:
        gateway.parse(
            ParseRequest(
                filename="sample.md",
                file_type="text/markdown",
                content=b"# sample",
            )
        )

    assert calls == ["primary"]
    assert [attempt.parser_id for attempt in captured.value.attempts] == ["primary"]
    assert isinstance(captured.value.__cause__, RuntimeError)


def test_gateway_reports_all_failed_automatic_attempts() -> None:
    calls: list[str] = []
    gateway = DocumentParserGateway(
        router=_FixedRouter(
            _auto_decision(
                selected_parser_id="primary",
                fallback_parser_ids=["fallback"],
            )
        )
    )
    gateway._adapters = {
        "primary": _RecordingParser(
            "primary",
            calls,
            error=RuntimeError("primary failed"),
        ),
        "fallback": _RecordingParser(
            "fallback",
            calls,
            error=ValueError("fallback failed"),
        ),
    }

    with pytest.raises(GatewayParseError, match="All routed parser attempts failed") as captured:
        gateway.parse(
            ParseRequest(
                filename="sample.md",
                file_type="text/markdown",
                content=b"# sample",
            )
        )

    assert calls == ["primary", "fallback"]
    assert [attempt.parser_id for attempt in captured.value.attempts] == [
        "primary",
        "fallback",
    ]
    assert all(attempt.status == "failed" for attempt in captured.value.attempts)
    assert len(captured.value.causes) == 2
    assert isinstance(captured.value.__cause__, ValueError)
