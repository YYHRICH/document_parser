import ast
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.core.contracts import (  # noqa: E402
    DocumentSignals,
    ParseConfidence,
    ParsedDocument,
    ParserNativeResult,
)
from document_parser.normalizers import (  # noqa: E402
    NativeResultNormalizer,
    NormalizationContext,
    NormalizationFacade,
    ParserNormalizationBundle,
    normalize_native_result,
    normalize_to_parsed_document,
)
from document_parser.parsers.base import BaseParserAdapter  # noqa: E402


FIXTURE = (
    PROJECT_ROOT / "tests" / "fixtures" / "normalizers" / "native-result-minimal.json"
)


class _FixtureAdapter(BaseParserAdapter):
    PARSER_ID = "fixture-adapter"
    DISPLAY_NAME = "Fixture Adapter"
    NATIVE_FORMATS = {".md"}


class _ProtocolOnlyNormalizer:
    """A normalizer implementation with no parser, Gateway, or route dependency."""

    def normalize_native(
        self,
        native_result: ParserNativeResult,
        context: NormalizationContext,
    ) -> ParserNormalizationBundle:
        return ParserNormalizationBundle.from_minimal_markdown(
            document_id=native_result.document_id,
            filename=native_result.filename,
            file_type=native_result.file_type,
            markdown=native_result.markdown or "",
            parser_id=native_result.parser_id,
            parser_version=native_result.parser_version,
            parser_parameters=context.parser_options,
            source_size_bytes=native_result.source_size_bytes,
            source_sha256=native_result.source_sha256,
            confidence=ParseConfidence(),
        )


def _native_fixture() -> ParserNativeResult:
    return ParserNativeResult.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def test_normalization_facade_runs_native_fixture_without_gateway_or_quality() -> None:
    native_result = _native_fixture()
    adapter = _FixtureAdapter()
    context = NormalizationContext.for_native_result(native_result)

    assert isinstance(adapter, NativeResultNormalizer)
    bundle = NormalizationFacade(adapter).normalize(native_result, context)
    parsed = normalize_to_parsed_document(
        native_result,
        normalizer=adapter,
        context=context,
    )

    assert bundle.document_id == native_result.document_id
    assert bundle.native_files == {}
    assert parsed.document_id == native_result.document_id
    assert parsed.provenance.parser_id == "fixture-adapter"
    assert parsed.routing_decision is not None
    assert parsed.routing_decision.selected_parser_id == "fixture-adapter"
    assert [block.source_block_id for block in parsed.blocks] == [
        "fixture-heading",
        "fixture-body",
    ]
    assert parsed.provenance.parameters["source"] == "offline-fixture"


def test_normalization_facade_accepts_protocol_only_implementation() -> None:
    native_result = _native_fixture()
    normalizer = _ProtocolOnlyNormalizer()

    assert isinstance(normalizer, NativeResultNormalizer)
    bundle = normalize_native_result(native_result, normalizer=normalizer)
    parsed = NormalizationFacade(normalizer).normalize_document(native_result)

    assert bundle.markdown == "# Fixture Title\n\nFixture body."
    assert bundle.provenance.parameters["source"] == "offline-fixture"
    assert isinstance(parsed, ParsedDocument)
    assert parsed.provenance.parser_id == "fixture-adapter"


def test_context_adapts_legacy_request_without_importing_a_router() -> None:
    native_result = _native_fixture()
    request_options = {"language": "en", "route_profile": "quality_first"}
    context = NormalizationContext.from_parse_request(
        request=native_result_to_request(native_result, request_options),
        signals=DocumentSignals(
            extension=".md",
            size_bytes=native_result.source_size_bytes or 0,
            has_text_layer=True,
        ),
    )

    assert context.requested_parser_id == "fixture-adapter"
    assert context.parser_options == request_options
    assert context.signals.has_text_layer is True


def native_result_to_request(
    native_result: ParserNativeResult,
    options: dict[str, object],
):
    """Keep the fixture smoke test explicit about its legacy bridge input."""

    from document_parser.core.contracts import ParseRequest

    return ParseRequest(
        filename=native_result.filename,
        file_type=native_result.file_type,
        content=b"fixture input is not required for normalization",
        parser_id=native_result.parser_id,
        options=options,
    )


def test_normalizer_package_has_no_feature_module_imports() -> None:
    """Guard the standalone boundary without importing Gateway or feature layers."""

    prohibited_roots = {"backend", "parsers", "quality", "routing"}
    prohibited_names = {"gateway", "storage"}
    normalizer_root = PROJECT_ROOT / "normalizers"

    for source_path in normalizer_root.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                modules = [module, *(alias.name for alias in node.names)]
            else:
                continue
            for module in modules:
                root_name = module.lstrip(".").split(".", 1)[0]
                assert root_name not in prohibited_roots, (
                    f"{source_path.name} imports prohibited feature module {module!r}"
                )
                assert module not in prohibited_names, (
                    f"{source_path.name} imports prohibited composition dependency {module!r}"
                )
