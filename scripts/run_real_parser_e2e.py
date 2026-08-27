"""Run real Docling/MinerU parsing plus deterministic quality on one PDF.

This is an opt-in operational runner, not a unit-test fixture generator.  It never
uses synthetic sidecars and treats an adapter placeholder as a failed execution.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import mimetypes
import os
import re
import shutil
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.util import find_spec
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Source-tree execution needs both import roots: document_parser lives below
# the project parent, while the independently runnable quality package lives
# directly below PROJECT_ROOT.
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT.parent))


DEFAULT_SOURCE = (
    PROJECT_ROOT
    / "datasets"
    / "shared-dev-v1"
    / "files"
    / "procurement_table_positive.pdf"
)
MAX_PUBLIC_DIAGNOSTIC_CHARACTERS = 4096

# These settings apply only to the runner process (and its local child
# processes). They deliberately override inherited remote model preferences
# without modifying the user's MinerU configuration file.
LOCAL_RUNTIME_OFFLINE_ENVIRONMENT = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    # MinerU 3.x can otherwise probe Hugging Face and fall back to ModelScope.
    "MINERU_MODEL_SOURCE": "local",
}
MINERU_PIPELINE_REQUIRED_ARTIFACTS = (
    "models/Layout/PP-DocLayoutV2",
    "models/OCR/paddleocr_torch",
    "models/TabRec/SlanetPlus/slanet-plus.onnx",
    "models/TabRec/UnetStructure/unet.onnx",
    "models/TabCls/paddle_table_cls/PP-LCNet_x1_0_table_cls.onnx",
)
MINERU_PIPELINE_FORMULA_ARTIFACTS = (
    "models/MFR/unimernet_hf_small_2503",
    "models/MFR/pp_formulanet_plus_m",
)


@dataclass(frozen=True)
class ParserPlan:
    parser_id: str
    mode: str
    options: dict[str, Any]
    runtime: dict[str, Any]
    skip_reason: str | None = None
    preflight_failure_reason: str | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a real Docling/MinerU PDF parse, require execution evidence, "
            "then write ParsedDocument and QualityPackage artifacts."
        )
    )
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE,
        help="PDF source. Defaults to the checked-in table fixture PDF.",
    )
    parser.add_argument(
        "--parser",
        choices=("all", "docling", "mineru"),
        default="all",
        help="Parser(s) to execute.",
    )
    parser.add_argument(
        "--mineru-mode",
        choices=("local", "cloud", "auto"),
        default="local",
        help=(
            "MinerU execution mode. local is the default and never falls back to cloud; "
            "cloud requires MINERU_API_TOKEN; auto prefers local then cloud."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory. Defaults to outputs/e2e/<source-stem>.",
    )
    parser.add_argument(
        "--allow-model-download",
        action="store_true",
        help=(
            "Allow local runtimes to fetch missing model artifacts or configuration. "
            "Disabled by default."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write preflight evidence only; do not invoke a parser or quality layer.",
    )
    parser.add_argument(
        "--allow-skips",
        action="store_true",
        help="Return success when a requested parser is explicitly skipped by preflight.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source = args.source.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Source PDF does not exist: {source}")
    if source.suffix.lower() != ".pdf":
        raise SystemExit(f"Only PDF input is supported by this runner: {source}")

    output_dir = (args.output_dir or PROJECT_ROOT / "outputs" / "e2e" / source.stem)
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    _configure_local_runtime_network_policy(allow_model_download=args.allow_model_download)
    source_info = _source_info(source)
    requested_ids = ("docling", "mineru") if args.parser == "all" else (args.parser,)
    plans = [
        _build_plan(
            parser_id,
            mineru_mode=args.mineru_mode,
            allow_model_download=args.allow_model_download,
        )
        for parser_id in requested_ids
    ]

    records: list[dict[str, Any]] = []
    for plan in plans:
        if args.dry_run:
            record = _planned_record(plan, source_info)
        elif plan.preflight_failure_reason is not None:
            record = _preflight_failed_record(plan, source_info)
        elif plan.skip_reason is not None:
            record = _skipped_record(plan, source_info)
        else:
            record = _run_plan(plan, source, source_info, output_dir)
        records.append(record)
        _write_json(output_dir / plan.parser_id / "execution-evidence.json", record)
        print(_console_line(record))

    summary = {
        "schema_name": "RealParserE2ERun",
        "schema_version": "1.0",
        "created_at": _utc_now(),
        "source": source_info,
        "dry_run": args.dry_run,
        "allow_model_download": args.allow_model_download,
        "records": records,
    }
    summary["outcome_counts"] = dict(Counter(record["outcome"] for record in records))
    _write_json(output_dir / "run-summary.json", summary)
    print(f"[e2e] summary: {output_dir / 'run-summary.json'}")

    if args.dry_run:
        return 0
    if any(record["outcome"] == "failed" for record in records):
        return 1
    if any(record["outcome"] == "skipped" for record in records) and not args.allow_skips:
        return 2
    return 0


def _build_plan(
    parser_id: str,
    *,
    mineru_mode: str,
    allow_model_download: bool,
) -> ParserPlan:
    model_download_policy = (
        "downloads_allowed" if allow_model_download else "local_artifacts_only"
    )
    if parser_id == "docling":
        runtime = {
            "model_download_policy": model_download_policy,
            "docling_package_available": _module_available("docling"),
            "docling_converter_available": _module_available(
                "docling.document_converter"
            ),
            "distribution_version": _distribution_version("docling"),
        }
        reason = None
        if not runtime["docling_converter_available"]:
            reason = (
                "Docling's document_converter runtime is not installed; "
                "no parser invocation was attempted."
            )
        return ParserPlan(
            parser_id="docling",
            mode="local",
            options={},
            runtime=runtime,
            skip_reason=reason,
        )

    if parser_id != "mineru":
        raise AssertionError(f"Unsupported E2E parser: {parser_id}")

    local_runtime = {
        "magic_pdf_module_available": _module_available("magic_pdf"),
        "mineru_module_available": _module_available("mineru"),
        # The adapter invokes this exact module through the active Python,
        # rather than an arbitrary executable found on PATH.
        "mineru_cli_module_available": _module_available("mineru.cli.client"),
        "mineru_command_on_path": shutil.which("mineru") is not None,
        "distribution_version": _distribution_version("mineru"),
    }
    local_available = any(
        (
            local_runtime["magic_pdf_module_available"],
            local_runtime["mineru_cli_module_available"],
        )
    )
    cloud_token_configured = bool((os.getenv("MINERU_API_TOKEN") or "").strip())
    cloud_allowed = _environment_bool("DOCUMENT_PARSER_ALLOW_CLOUD", default=False)
    runtime = {
        **local_runtime,
        "model_download_policy": model_download_policy,
        "local_runtime_available": local_available,
        "cloud_token_configured": cloud_token_configured,
        "cloud_allowed_by_server_policy": cloud_allowed,
    }
    local_model_preflight_failure = None
    if local_available and not allow_model_download:
        # The adapter prefers magic_pdf when present. Its legacy model loading
        # contract has no supported strict-offline switch, so do not invoke it
        # under this runner's no-download guarantee.
        if local_runtime["magic_pdf_module_available"]:
            local_model_preflight_failure = (
                "MinerU legacy magic_pdf runtime is not permitted while downloads are "
                "disabled. Use the modern local MinerU CLI with pre-downloaded artifacts, "
                "or rerun with --allow-model-download."
            )
        else:
            local_model_preflight_failure = _mineru_local_model_preflight_failure()

    if mineru_mode == "local":
        return ParserPlan(
            parser_id="mineru",
            mode="local",
            options={"mineru_force_local": True},
            runtime=runtime,
            skip_reason=(
                None
                if local_available
                else "No local MinerU runtime is installed; cloud was not attempted in local mode."
            ),
            preflight_failure_reason=local_model_preflight_failure,
        )
    if mineru_mode == "cloud":
        skip_reason = None
        if not cloud_token_configured:
            skip_reason = (
                "MINERU_API_TOKEN is not configured; MinerU cloud execution was skipped "
                "instead of returning placeholder output."
            )
        elif not cloud_allowed:
            skip_reason = "DOCUMENT_PARSER_ALLOW_CLOUD=false forbids MinerU cloud execution."
        return ParserPlan(
            parser_id="mineru",
            mode="cloud",
            options={"api_mode": "cloud"},
            runtime=runtime,
            skip_reason=skip_reason,
        )

    if local_available:
        return ParserPlan(
            parser_id="mineru",
            mode="local",
            options={"mineru_force_local": True},
            runtime=runtime,
            preflight_failure_reason=local_model_preflight_failure,
        )
    if cloud_token_configured and cloud_allowed:
        return ParserPlan(
            parser_id="mineru",
            mode="cloud",
            options={"api_mode": "cloud"},
            runtime=runtime,
        )
    reason = (
        "No local MinerU runtime and no usable cloud token are available; no parser "
        "invocation was attempted."
    )
    if cloud_token_configured and not cloud_allowed:
        reason = "No local MinerU runtime and DOCUMENT_PARSER_ALLOW_CLOUD=false forbids cloud execution."
    return ParserPlan(
        parser_id="mineru",
        mode="auto",
        options={},
        runtime=runtime,
        skip_reason=reason,
    )


def _run_plan(
    plan: ParserPlan,
    source: Path,
    source_info: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    started_at = _utc_now()
    started = time.perf_counter()
    parser_dir = output_dir / plan.parser_id
    try:
        from document_parser.core.contracts import ParseRequest
        from document_parser.core.inspector import SimpleSourceInspector
        from document_parser.parsers.docling import DoclingParser
        from document_parser.parsers.mineru import MinerUParser

        adapter = DoclingParser() if plan.parser_id == "docling" else MinerUParser()
        request = ParseRequest(
            filename=source.name,
            file_type=mimetypes.guess_type(source.name)[0] or "application/pdf",
            content=source.read_bytes(),
            parser_id=plan.parser_id,
            options=plan.options,
        )
        signals = SimpleSourceInspector().inspect(request)
        bundle = adapter.normalize(request, signals)
        document = bundle.to_parsed_document()
        actual, engine, execution_reason = _actual_execution_evidence(plan, bundle)
        document_path = parser_dir / "parsed_document.json"
        _write_json(document_path, _public_document_payload(document))
        native_manifest_path = parser_dir / "native-artifacts.json"
        _write_json(native_manifest_path, _native_manifest(bundle))

        record: dict[str, Any] = {
            "schema_name": "ParserE2EExecutionEvidence",
            "schema_version": "1.0",
            "parser_id": plan.parser_id,
            "requested_mode": plan.mode,
            "outcome": "succeeded" if actual else "failed",
            "actual_execution": actual,
            "execution_engine": engine,
            "execution_reason": execution_reason,
            "started_at": started_at,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "source": source_info,
            "runtime": plan.runtime,
            "parser_options": _public_options(plan.options),
            "warnings": [_redact(str(item)) for item in bundle.warnings],
            "native_artifacts_path": str(native_manifest_path),
            "parsed_document_path": str(document_path),
            "parsed_document_summary": _document_summary(document),
        }
        if not actual:
            record["failure_reason"] = (
                "The adapter returned no approved real-execution evidence. "
                "A placeholder result is intentionally not reported as an E2E success."
            )
            return record

        from quality import run_quality

        package = run_quality(document)
        package_path = parser_dir / "quality_package.json"
        _write_json(package_path, package.model_dump(mode="json"))
        record["quality_package_path"] = str(package_path)
        record["quality_package_summary"] = _quality_summary(package)
        return record
    except Exception as error:
        return {
            "schema_name": "ParserE2EExecutionEvidence",
            "schema_version": "1.0",
            "parser_id": plan.parser_id,
            "requested_mode": plan.mode,
            "outcome": "failed",
            "actual_execution": False,
            "execution_engine": None,
            "started_at": started_at,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "source": source_info,
            "runtime": plan.runtime,
            "parser_options": _public_options(plan.options),
            "error_type": type(error).__name__,
            "failure_reason": _failure_reason(plan, error),
            **_failure_metadata(error),
        }


def _failure_reason(plan: ParserPlan, error: Exception) -> str:
    reason = _redact(str(error))
    if plan.runtime.get("model_download_policy") == "local_artifacts_only":
        return (
            f"{reason} Model and configuration downloads are disabled for this "
            "local E2E run; verify local artifacts, or rerun with "
            "--allow-model-download."
        )
    return reason


def _failure_metadata(error: Exception) -> dict[str, Any]:
    """Persist the portable parser-error classification without importing a plugin."""

    failure_kind = getattr(error, "failure_kind", "parser")
    if not isinstance(failure_kind, str) or not failure_kind.strip():
        failure_kind = "parser"
    return {
        "failure_kind": failure_kind.strip().lower(),
        "retryable": bool(getattr(error, "retryable", False)),
    }


def _actual_execution_evidence(plan: ParserPlan, bundle: Any) -> tuple[bool, str | None, str]:
    native_files = dict(bundle.native_files)
    native_paths = set(native_files)
    warnings = "\n".join(str(item) for item in bundle.warnings)
    normalized_warnings = warnings.lower()
    if plan.parser_id == "docling":
        required = {"native/docling_document.json", "native/full.md"}
        missing = sorted(required - native_paths)
        if not missing:
            return True, "docling_local", "Docling native JSON and Markdown sidecars were emitted."
        return False, None, f"Missing Docling native execution sidecars: {missing}"

    # _with_mineru_payload() always adds the canonical result JSON after a
    # successful adapter path.  That artifact and its warning alone do not
    # prove that a CLI/cloud invocation emitted parse content: a zero-exit
    # runtime with an empty output directory would otherwise look successful.
    mineru_markdown_paths = sorted(
        path
        for path, content in native_files.items()
        if path.startswith("native/")
        and Path(path).suffix.lower() in {".md", ".markdown"}
        and _nonempty_native_content(content)
    )
    mineru_structured_paths = sorted(
        path
        for path, content in native_files.items()
        if path != "native/mineru_result.json"
        and _is_mineru_structured_sidecar(path, content)
    )
    has_markdown = isinstance(bundle.markdown, str) and bool(bundle.markdown.strip())
    mineru_engines = {
        "mineru cloud task completed": "mineru_cloud",
        "mineru cli run completed": "mineru_cli",
        "mineru local magic-pdf run completed": "mineru_magic_pdf",
    }
    for marker, engine in mineru_engines.items():
        if marker not in normalized_warnings:
            continue
        missing: list[str] = []
        if "native/mineru_result.json" not in native_paths:
            missing.append("native/mineru_result.json")
        if not has_markdown:
            missing.append("non-empty normalized Markdown")
        if not mineru_markdown_paths:
            missing.append("non-empty parser-generated Markdown sidecar")
        if not mineru_structured_paths:
            missing.append("non-empty parser-generated structured JSON sidecar")
        if not missing:
            return (
                True,
                engine,
                (
                    f"Observed adapter completion marker: {marker}; "
                    f"Markdown sidecars: {mineru_markdown_paths}; "
                    f"structured sidecars: {mineru_structured_paths}."
                ),
            )
        return (
            False,
            None,
            f"MinerU completion marker was observed but execution content evidence is missing: {missing}.",
        )
    return (
        False,
        None,
        "MinerU completion marker was not observed; canonical sidecars alone are insufficient.",
    )


def _nonempty_native_content(value: Any) -> bool:
    if isinstance(value, bytes):
        return bool(value.strip())
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def _is_mineru_structured_sidecar(path: str, content: Any) -> bool:
    """Accept only expected, non-empty MinerU JSON output sidecars.

    CLI output may be nested below the input stem, so matching is by basename.
    Generic JSON such as a runtime error or a metadata dump is deliberately not
    accepted as proof that MinerU produced parser content.
    """

    name = Path(path).name.lower()
    is_content_list = "content_list" in name and name.endswith(".json")
    is_middle = name == "middle.json" or name.endswith("_middle.json")
    if not (is_content_list or is_middle) or not _nonempty_native_content(content):
        return False
    try:
        raw = content.decode("utf-8") if isinstance(content, bytes) else str(content)
        payload = json.loads(raw)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if is_content_list:
        return isinstance(payload, list) and bool(payload)
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("pdf_info"), list)
        and bool(payload["pdf_info"])
    )


def _native_manifest(bundle: Any) -> dict[str, Any]:
    return {
        "native_file_paths": sorted(bundle.native_files),
        "native_file_count": len(bundle.native_files),
        "native_artifacts": [
            artifact.model_dump(mode="json") for artifact in bundle.native_artifacts
        ],
    }


def _document_summary(document: Any) -> dict[str, Any]:
    return {
        "document_id": str(document.document_id),
        "schema_version": document.schema_version,
        "parser_id": document.provenance.parser_id,
        "parser_version": document.provenance.version,
        "markdown_characters": len(document.markdown),
        "block_count": len(document.blocks),
        "table_count": len(document.tables),
        "asset_count": len(document.assets),
        "ocr_span_count": len(document.ocr_spans),
        "native_artifact_count": len(document.native_artifacts),
        "capabilities": {
            name: capability.state.value
            for name, capability in document.capabilities.items()
        },
    }


def _quality_summary(package: Any) -> dict[str, Any]:
    report = package.quality_report
    return {
        "document_id": str(package.document_id),
        "state": report.state.value,
        "issue_count": len(report.issues),
        "issues_by_severity": dict(
            Counter(issue.severity.value for issue in report.issues)
        ),
        "applied_repair_count": len(report.applied_repairs),
        "gate_summary": report.gate_summary.model_dump(mode="json"),
        "reparse_recommendation": (
            report.reparse_recommendation.model_dump(mode="json")
            if report.reparse_recommendation is not None
            else None
        ),
        "artifact_hashes": dict(report.artifacts),
    }


def _planned_record(plan: ParserPlan, source_info: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_name": "ParserE2EExecutionEvidence",
        "schema_version": "1.0",
        "parser_id": plan.parser_id,
        "requested_mode": plan.mode,
        "outcome": "planned",
        "actual_execution": False,
        "execution_engine": None,
        "source": source_info,
        "runtime": plan.runtime,
        "parser_options": _public_options(plan.options),
        "preflight_reason": plan.preflight_failure_reason or plan.skip_reason,
    }


def _skipped_record(plan: ParserPlan, source_info: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_name": "ParserE2EExecutionEvidence",
        "schema_version": "1.0",
        "parser_id": plan.parser_id,
        "requested_mode": plan.mode,
        "outcome": "skipped",
        "actual_execution": False,
        "execution_engine": None,
        "source": source_info,
        "runtime": plan.runtime,
        "parser_options": _public_options(plan.options),
        "skip_reason": plan.skip_reason,
    }


def _preflight_failed_record(
    plan: ParserPlan, source_info: dict[str, Any]
) -> dict[str, Any]:
    assert plan.preflight_failure_reason is not None
    return {
        "schema_name": "ParserE2EExecutionEvidence",
        "schema_version": "1.0",
        "parser_id": plan.parser_id,
        "requested_mode": plan.mode,
        "outcome": "failed",
        "actual_execution": False,
        "execution_engine": None,
        "source": source_info,
        "runtime": plan.runtime,
        "parser_options": _public_options(plan.options),
        "failure_kind": "unavailable",
        "retryable": False,
        "failure_reason": plan.preflight_failure_reason,
    }


def _source_info(source: Path) -> dict[str, Any]:
    content = source.read_bytes()
    return {
        "path": str(source),
        "filename": source.name,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _mineru_tools_config_path() -> Path:
    configured = os.getenv("MINERU_TOOLS_CONFIG_JSON", "mineru.json")
    path = Path(configured).expanduser()
    return path if path.is_absolute() else Path.home() / path


def _mineru_local_model_preflight_failure() -> str | None:
    """Return a safe failure instead of letting MinerU fetch missing local models."""

    config_path = _mineru_tools_config_path()
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return (
            "MinerU local model configuration is missing while downloads are disabled. "
            "Configure mineru.json models-dir.pipeline with pre-downloaded artifacts, "
            "or rerun with --allow-model-download."
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return (
            "MinerU local model configuration cannot be read while downloads are disabled. "
            "Configure mineru.json models-dir.pipeline with pre-downloaded artifacts, "
            "or rerun with --allow-model-download."
        )

    model_dirs = config.get("models-dir") if isinstance(config, dict) else None
    pipeline_root = model_dirs.get("pipeline") if isinstance(model_dirs, dict) else None
    if not isinstance(pipeline_root, str) or not pipeline_root.strip():
        return (
            "MinerU local pipeline models are not configured while downloads are disabled. "
            "Set models-dir.pipeline in mineru.json, or rerun with --allow-model-download."
        )

    root = Path(pipeline_root).expanduser()
    if not root.is_dir():
        return (
            "MinerU local pipeline model directory is unavailable while downloads are disabled. "
            "Restore the configured local artifacts, or rerun with --allow-model-download."
        )
    required_paths = (*MINERU_PIPELINE_REQUIRED_ARTIFACTS,)
    has_formula_model = any(
        (root / relative_path).exists()
        for relative_path in MINERU_PIPELINE_FORMULA_ARTIFACTS
    )
    if any(not (root / relative_path).exists() for relative_path in required_paths) or not has_formula_model:
        return (
            "MinerU local pipeline model artifacts are incomplete while downloads are disabled. "
            "Pre-download the required pipeline artifacts, or rerun with --allow-model-download."
        )
    return None


def _configure_local_runtime_network_policy(*, allow_model_download: bool) -> None:
    if allow_model_download:
        return
    # Docling's Hugging Face model lookup honors these flags. MinerU needs the
    # explicit local model source as it otherwise falls back to ModelScope and
    # may persist a remotely resolved source/configuration.
    os.environ.update(LOCAL_RUNTIME_OFFLINE_ENVIRONMENT)
    os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")


def _environment_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _module_available(name: str) -> bool:
    try:
        return find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _public_options(options: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in options.items()
        if "token" not in key.lower() and "authorization" not in key.lower()
    }


def _public_document_payload(document: Any) -> dict[str, Any]:
    """Serialize ParsedDocument without persisting adapter errors containing a token."""

    payload = document.model_dump(mode="json")
    warnings = payload.get("warnings")
    if isinstance(warnings, list):
        payload["warnings"] = [_redact(str(item)) for item in warnings]
    return payload


def _redact(value: str) -> str:
    """Make parser diagnostics safe to persist and keep their size bounded."""

    redacted = str(value)
    token = os.getenv("MINERU_API_TOKEN")
    if token:
        redacted = redacted.replace(token, "<redacted>")
    redacted = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1<redacted>", redacted)
    redacted = re.sub(
        r"(?i)([?&](?:access[_-]?token|api[_-]?key|api[_-]?token|"
        r"authorization|signature|sig|x-amz-signature)=)[^&#\s]+",
        r"\1<redacted>",
        redacted,
    )
    redacted = re.sub(
        r"(?i)([\"']?(?:x[-_]?api[-_]?key|api[_-]?key|api[_-]?token|"
        r"access[_-]?token|authorization|signature|sig)[\"']?\s*[:=]\s*[\"']?)"
        r"[^\"'\s,}&]+",
        r"\1<redacted>",
        redacted,
    )
    if len(redacted) > MAX_PUBLIC_DIAGNOSTIC_CHARACTERS:
        return (
            redacted[:MAX_PUBLIC_DIAGNOSTIC_CHARACTERS]
            + " …<diagnostic truncated>"
        )
    return redacted


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _console_line(record: dict[str, Any]) -> str:
    parser_id = record["parser_id"]
    outcome = record["outcome"]
    detail = (
        record.get("execution_reason")
        or record.get("skip_reason")
        or record.get("failure_reason")
        or record.get("preflight_reason")
        or ""
    )
    return f"[e2e] {parser_id}: {outcome} {detail}".rstrip()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
