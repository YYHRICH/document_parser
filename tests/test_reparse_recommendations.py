"""Independent regression tests for pure reparse recommendation."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.core.contracts import ParserCapability  # noqa: E402
from document_parser.routing import (  # noqa: E402
    ReparseContext,
    ReparseRecommendationPolicy,
    ReparseSignal,
    ReparseSignalSource,
    recommend_reparse,
)


def _capability(
    parser_id: str,
    *,
    formats: set[str] | None = None,
    available: bool = True,
    requires_network: bool = False,
    unavailable_reason: str | None = None,
) -> ParserCapability:
    return ParserCapability(
        parser_id=parser_id,
        provider="fixture",
        display_name=parser_id,
        formats=formats or {".pdf"},
        available=available,
        requires_network=requires_network,
        unavailable_reason=unavailable_reason,
    )


def _quality_signal() -> ReparseSignal:
    return ReparseSignal(
        source=ReparseSignalSource.QUALITY,
        code="table-evidence-missing",
        message="Required table evidence is incomplete.",
    )


def test_recommendation_is_stable_and_only_executable_candidates_get_auto_options() -> None:
    capabilities = [
        _capability("unsupported-parser", formats={".docx"}),
        _capability("cloud-parser", requires_network=True),
        _capability(
            "unavailable-parser",
            available=False,
            unavailable_reason="Required runtime is not installed.",
        ),
        _capability("prior-parser"),
        _capability("old-parser"),
        _capability("local-parser", formats={"PDF"}),
        _capability("policy-blocked-parser"),
    ]
    context = ReparseContext(
        parent_parse_id="parent-001",
        source_extension="PDF",
        current_parser_id="old-parser",
        attempted_parser_ids=("old-parser", "prior-parser"),
    )
    policy = ReparseRecommendationPolicy(
        allow_cloud=False,
        allowed_parser_ids=(
            "local-parser",
            "cloud-parser",
            "unavailable-parser",
            "unsupported-parser",
            "prior-parser",
            "old-parser",
        ),
        priority_parser_ids=("local-parser", "cloud-parser", "old-parser", "prior-parser"),
        common_auto_options={"route_profile": "quality_first"},
        auto_options_by_parser={"local-parser": {"tables": True}},
    )

    result = recommend_reparse(
        context,
        reversed(capabilities),
        [_quality_signal()],
        policy,
    )

    assert result.context.source_extension == ".pdf"
    assert result.candidates[0].parser_id == "local-parser"
    assert result.automatic is not None
    assert result.automatic.parser_id == "local-parser"
    assert result.automatic.options == {
        "route_profile": "quality_first",
        "tables": True,
        "reparse": True,
    }

    candidates = {candidate.parser_id: candidate for candidate in result.candidates}
    local = candidates["local-parser"]
    assert local.executable is True
    assert local.replaces_current_parser is True
    assert local.requires_cloud is False
    assert local.auto_options == result.automatic.options

    cloud = candidates["cloud-parser"]
    assert cloud.executable is False
    assert cloud.requires_cloud is True
    assert cloud.auto_options == {}
    assert "cloud policy" in cloud.reason.lower()

    unavailable = candidates["unavailable-parser"]
    assert unavailable.executable is False
    assert unavailable.auto_options == {}
    assert "not installed" in unavailable.reason.lower()

    unsupported = candidates["unsupported-parser"]
    assert unsupported.executable is False
    assert unsupported.auto_options == {}
    assert "does not support .pdf" in unsupported.reason.lower()

    prior = candidates["prior-parser"]
    assert prior.executable is False
    assert "already attempted" in prior.reason.lower()

    current = candidates["old-parser"]
    assert current.executable is False
    assert current.replaces_current_parser is False
    assert "current parser" in current.reason.lower()

    blocked = candidates["policy-blocked-parser"]
    assert blocked.executable is False
    assert "effective reparse policy" in blocked.reason.lower()


def test_same_parser_retry_requires_retryable_failure_and_explicit_policy() -> None:
    capability = _capability("current-parser")
    context = ReparseContext(
        source_extension=".pdf",
        current_parser_id="current-parser",
        attempted_parser_ids=("current-parser",),
    )
    retryable_failure = ReparseSignal(
        source=ReparseSignalSource.FAILURE,
        code="transient-timeout",
        message="The parser timed out temporarily.",
        retryable=True,
    )

    default_result = recommend_reparse(context, [capability], [retryable_failure])
    assert default_result.automatic is None
    assert default_result.candidates[0].executable is False

    enabled_result = recommend_reparse(
        context,
        [capability],
        [retryable_failure],
        ReparseRecommendationPolicy(allow_current_parser_retry=True),
    )
    candidate = enabled_result.candidates[0]
    assert candidate.executable is True
    assert candidate.replaces_current_parser is False
    assert candidate.auto_options == {"reparse": True}
    assert enabled_result.automatic is not None
    assert enabled_result.automatic.parser_id == "current-parser"

    quality_only_result = recommend_reparse(
        context,
        [capability],
        [_quality_signal()],
        ReparseRecommendationPolicy(allow_current_parser_retry=True),
    )
    assert quality_only_result.automatic is None
    assert quality_only_result.candidates[0].executable is False


def test_cloud_candidate_requires_effective_cloud_permission_and_priority_drives_auto_choice() -> None:
    capabilities = [
        _capability("local-parser"),
        _capability("cloud-parser", requires_network=True),
    ]
    context = ReparseContext(source_extension=".pdf", current_parser_id="old-parser")
    policy = ReparseRecommendationPolicy(
        allow_cloud=True,
        priority_parser_ids=("cloud-parser", "local-parser"),
        auto_options_by_parser={"cloud-parser": {"region": "approved"}},
    )

    result = recommend_reparse(context, capabilities, [_quality_signal()], policy)

    assert [candidate.parser_id for candidate in result.candidates] == [
        "cloud-parser",
        "local-parser",
    ]
    assert all(candidate.executable for candidate in result.candidates)
    assert result.automatic is not None
    assert result.automatic.parser_id == "cloud-parser"
    assert result.automatic.requires_cloud is True
    assert result.automatic.options == {"region": "approved", "reparse": True}


def test_empty_signals_and_duplicate_snapshot_are_rejected() -> None:
    context = ReparseContext(source_extension=".pdf")
    capability = _capability("parser-a")

    with pytest.raises(ValueError, match="At least one quality or failure signal"):
        recommend_reparse(context, [capability], [])

    with pytest.raises(ValueError, match="Duplicate parser ID"):
        recommend_reparse(context, [capability, capability.model_copy(deep=True)], [_quality_signal()])


def test_recommendation_module_has_no_runtime_dependency_on_parser_quality_or_web_layers() -> None:
    module_path = PROJECT_ROOT / "routing" / "recommendations.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(module_path))
    forbidden = {"backend", "fastapi", "frontend", "orchestration", "parsers", "quality", "storage"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module_parts = set((node.module or "").split("."))
            assert not (module_parts & forbidden), node.module
        elif isinstance(node, ast.Import):
            for imported in node.names:
                module_parts = set(imported.name.split("."))
                assert not (module_parts & forbidden), imported.name

    command = (
        "import sys; import document_parser.routing.recommendations; "
        "forbidden=('document_parser.backend', 'document_parser.frontend', "
        "'document_parser.orchestration', 'document_parser.parsers', 'quality'); "
        "assert not any(name == item or name.startswith(item + '.') "
        "for name in sys.modules for item in forbidden)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=PROJECT_ROOT.parent,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
