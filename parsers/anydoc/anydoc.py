"""AnyDoc parser adapter."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import time
from importlib.util import find_spec
from pathlib import Path

from ...core.contracts import DocumentSignals, ParseRequest, ParserCapability, ParserNativeResult
from ...normalizers import ParserNormalizationBundle, make_stable_document_id
from ..base import BaseParserAdapter


class AnyDocParser(BaseParserAdapter):
    """Adapter for AnyDoc native sidecars and command-line runs."""

    PARSER_ID = "anydoc"
    PROVIDER = "firecrawl"
    DISPLAY_NAME = "AnyDoc parser"
    NATIVE_FORMATS = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".csv"}
    MODEL_VERSIONS = ["0.1.6"]
    DEFAULT_MODEL_VERSION = "0.1.6"
    REQUIRES_NETWORK = False
    REQUIRES_GPU = False
    UNAVAILABLE_REASON = (
        "AnyDoc adapter is present, but no AnyDoc executable is available. "
        "Install @firecrawl/anydoc globally or set ANYDOC_EXECUTABLE."
    )

    @property
    def capability(self) -> ParserCapability:
        executable = self._resolve_executable()
        available = executable is not None
        return ParserCapability(
            parser_id=self.PARSER_ID,
            provider=self.PROVIDER,
            display_name=self.DISPLAY_NAME,
            formats=self.NATIVE_FORMATS,
            model_versions=self.MODEL_VERSIONS,
            default_model_version=self.DEFAULT_MODEL_VERSION,
            requires_network=self.REQUIRES_NETWORK,
            requires_gpu=self.REQUIRES_GPU,
            available=available,
            unavailable_reason=None if available else self.UNAVAILABLE_REASON,
        )

    def build_native_result(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNativeResult:
        sidecar_result = self._build_native_result_from_options(request, signals)
        if sidecar_result is not None:
            return sidecar_result
        if signals.extension not in self.NATIVE_FORMATS:
            return self._build_placeholder_native_result(
                request,
                signals,
                warnings=[f"AnyDoc does not support direct parsing for {signals.extension}."],
            )

        executable = self._resolve_executable()
        if executable is None:
            return self._build_placeholder_native_result(
                request,
                signals,
                warnings=[self.UNAVAILABLE_REASON],
            )
        return self._build_with_anydoc_cli(request, signals, executable)

    def _build_with_anydoc_cli(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
        executable: str,
    ) -> ParserNativeResult:
        started = time.perf_counter()
        parser_version = self._installed_version("anydoc", self.DEFAULT_MODEL_VERSION)
        with tempfile.TemporaryDirectory(prefix="anydoc-run-") as temporary:
            work_dir = Path(temporary)
            source_path = work_dir / f"source{signals.extension or Path(request.filename).suffix}"
            output_dir = work_dir / "output"
            source_path.write_bytes(request.content)
            output_dir.mkdir(parents=True, exist_ok=True)
            command = [executable, *self._anydoc_args(request), str(source_path)]
            completed = subprocess.run(
                command,
                cwd=output_dir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=int(request.options.get("anydoc_timeout_seconds", 600)),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                check=False,
            )
            if completed.returncode != 0:
                # stderr/stdout are untrusted backend diagnostics and can contain
                # paths or credentials.  The safe typed error still lets Gateway
                # advance to the configured fallback parser.
                raise self.execution_error(
                    failure_kind="parser",
                    safe_message="AnyDoc CLI execution failed.",
                )
            native_result = self._build_native_result_from_output_dir(
                request,
                signals,
                output_dir,
                parser_version=parser_version,
            )
            if not native_result.native_files:
                raise self.execution_error(
                    failure_kind="parser",
                    safe_message="AnyDoc CLI completed without native output.",
                )
        return self._augment_anydoc_result(
            native_result,
            warning=f"AnyDoc CLI run completed in {int((time.perf_counter() - started) * 1000)} ms.",
        )

    def normalize(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNormalizationBundle:
        """Execute through the plugin port before standalone normalization."""

        return super().normalize(request, signals)

    def _augment_anydoc_result(self, native_result: ParserNativeResult, *, warning: str) -> ParserNativeResult:
        return native_result.model_copy(update={"warnings": [*native_result.warnings, warning]})

    def _resolve_executable(self) -> str | None:
        configured = os.getenv("ANYDOC_EXECUTABLE")
        if configured:
            path = Path(configured).expanduser()
            if path.is_file():
                return str(path.resolve())
        return shutil.which("anydoc") or shutil.which("anydoc.cmd")

    def _anydoc_args(self, request: ParseRequest) -> list[str]:
        raw_args = request.options.get("anydoc_args")
        if isinstance(raw_args, list):
            return [str(item) for item in raw_args]
        if isinstance(raw_args, str) and raw_args.strip():
            return shlex.split(raw_args)
        return []
