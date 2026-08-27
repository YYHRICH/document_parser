"""Fast safety checks for the real-parser E2E evidence predicate."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = PROJECT_ROOT / "scripts" / "run_real_parser_e2e.py"
MODULE_NAME = "_document_parser_real_e2e_runner_test_module"


def _runner_module():
    module = sys.modules.get(MODULE_NAME)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(MODULE_NAME, RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def _mineru_plan():
    runner = _runner_module()
    return runner.ParserPlan(
        parser_id="mineru",
        mode="local",
        options={"mineru_force_local": True},
        runtime={},
    )


def test_mineru_completion_marker_and_generated_result_alone_are_not_success() -> None:
    runner = _runner_module()
    bundle = SimpleNamespace(
        native_files={"native/mineru_result.json": b"{}"},
        warnings=["MinerU CLI run completed in 1 ms."],
        markdown="",
    )

    actual, engine, reason = runner._actual_execution_evidence(_mineru_plan(), bundle)

    assert actual is False
    assert engine is None
    assert "content evidence is missing" in reason


def test_mineru_requires_both_native_markdown_and_structured_sidecars() -> None:
    runner = _runner_module()
    incomplete_bundle = SimpleNamespace(
        native_files={
            "native/mineru_result.json": b"{}",
            "native/error.json": b'{"error":"not parser content"}',
            "native/full.md": b"verified",
        },
        warnings=["MinerU CLI run completed in 1 ms."],
        markdown="verified",
    )

    actual, engine, reason = runner._actual_execution_evidence(
        _mineru_plan(), incomplete_bundle
    )

    assert actual is False
    assert engine is None
    assert "structured JSON sidecar" in reason


def test_mineru_requires_content_sidecars_and_normalized_markdown() -> None:
    runner = _runner_module()
    bundle = SimpleNamespace(
        native_files={
            "native/mineru_result.json": b"{}",
            "native/content_list.json": b'[{"type":"text","text":"verified"}]',
            "native/full.md": b"verified",
        },
        warnings=["MinerU CLI run completed in 1 ms."],
        markdown="verified",
    )

    actual, engine, reason = runner._actual_execution_evidence(_mineru_plan(), bundle)

    assert actual is True
    assert engine == "mineru_cli"
    assert "Markdown sidecars" in reason


def test_runner_redacts_environment_token_from_persisted_adapter_warnings(monkeypatch) -> None:
    runner = _runner_module()
    token = "test-token-for-redaction"
    monkeypatch.setenv("MINERU_API_TOKEN", token)
    document = SimpleNamespace(
        model_dump=lambda **_: {
            "markdown": "safe parsed body",
            "warnings": [f"request used Bearer {token}", f"raw {token}"],
        }
    )

    payload = runner._public_document_payload(document)

    assert token not in repr(payload)
    assert payload["markdown"] == "safe parsed body"
    assert payload["warnings"] == [
        "request used Bearer <redacted>",
        "raw <redacted>",
    ]


def test_runner_redacts_generic_credentials_and_truncates_diagnostics(monkeypatch) -> None:
    runner = _runner_module()
    monkeypatch.delenv("MINERU_API_TOKEN", raising=False)
    raw = (
        "api_key=other-secret https://example.test/x?signature=url-secret "
        "Authorization: Bearer bearer-secret "
        + "x" * (runner.MAX_PUBLIC_DIAGNOSTIC_CHARACTERS + 20)
    )

    redacted = runner._redact(raw)

    assert "other-secret" not in redacted
    assert "url-secret" not in redacted
    assert "bearer-secret" not in redacted
    assert redacted.endswith("…<diagnostic truncated>")


def test_runner_preserves_portable_failure_metadata_without_importing_a_plugin() -> None:
    runner = _runner_module()
    error = RuntimeError("safe failure")
    error.failure_kind = "transient"  # type: ignore[attr-defined]
    error.retryable = True  # type: ignore[attr-defined]

    metadata = runner._failure_metadata(error)

    assert metadata == {"failure_kind": "transient", "retryable": True}

def test_local_e2e_policy_forces_docling_and_mineru_offline_sources(monkeypatch) -> None:
    runner = _runner_module()
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "0")
    monkeypatch.setenv("HF_DATASETS_OFFLINE", "0")
    monkeypatch.setenv("MINERU_MODEL_SOURCE", "modelscope")

    runner._configure_local_runtime_network_policy(allow_model_download=False)

    for name, value in runner.LOCAL_RUNTIME_OFFLINE_ENVIRONMENT.items():
        assert os.environ[name] == value


def test_explicit_model_download_opt_in_does_not_force_offline_sources(monkeypatch) -> None:
    runner = _runner_module()
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("MINERU_MODEL_SOURCE", "modelscope")

    runner._configure_local_runtime_network_policy(allow_model_download=True)

    assert os.environ["HF_HUB_OFFLINE"] == "0"
    assert os.environ["MINERU_MODEL_SOURCE"] == "modelscope"


def test_local_mineru_missing_artifacts_fails_before_parser_execution(monkeypatch, tmp_path: Path) -> None:
    runner = _runner_module()
    monkeypatch.setenv("MINERU_TOOLS_CONFIG_JSON", str(tmp_path / "missing-mineru.json"))
    monkeypatch.setattr(
        runner,
        "_module_available",
        lambda name: name == "mineru.cli.client",
    )

    plan = runner._build_plan(
        "mineru",
        mineru_mode="local",
        allow_model_download=False,
    )
    record = runner._preflight_failed_record(plan, {"filename": "fixture.pdf"})

    assert plan.options == {"mineru_force_local": True}
    assert plan.preflight_failure_reason is not None
    assert "downloads are disabled" in plan.preflight_failure_reason
    assert record["outcome"] == "failed"
    assert record["failure_kind"] == "unavailable"
    assert record["actual_execution"] is False
    assert runner._planned_record(plan, {"filename": "fixture.pdf"})["preflight_reason"] == (
        plan.preflight_failure_reason
    )


def test_explicit_model_download_opt_in_bypasses_mineru_local_artifact_preflight(
    monkeypatch, tmp_path: Path
) -> None:
    runner = _runner_module()
    monkeypatch.setenv("MINERU_TOOLS_CONFIG_JSON", str(tmp_path / "missing-mineru.json"))
    monkeypatch.setattr(
        runner,
        "_module_available",
        lambda name: name == "mineru.cli.client",
    )

    plan = runner._build_plan(
        "mineru",
        mineru_mode="local",
        allow_model_download=True,
    )

    assert plan.preflight_failure_reason is None
    assert plan.runtime["model_download_policy"] == "downloads_allowed"

def test_strict_local_mode_rejects_legacy_magic_pdf_before_execution(monkeypatch) -> None:
    runner = _runner_module()
    monkeypatch.setattr(runner, "_module_available", lambda name: name == "magic_pdf")

    plan = runner._build_plan(
        "mineru",
        mineru_mode="local",
        allow_model_download=False,
    )

    assert plan.preflight_failure_reason is not None
    assert "magic_pdf" in plan.preflight_failure_reason

