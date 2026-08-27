"""MinerU parser adapter."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from html.parser import HTMLParser
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from ...core.contracts import (
    AssetKind,
    DocumentAsset,
    DocumentSignals,
    ParseRequest,
    ParserCapability,
    ParserNativeResult,
)
from ...normalizers import (
    ParserNormalizationBundle,
    make_stable_document_id,
    partial_capability,
    unavailable_capability,
)
from ..base import BaseParserAdapter
from ..ports import ParserExecutionError
from ...common.url_security import same_url_origin
from .security import (
    MinerUConfigurationError,
    MinerUSecurityError,
    MinerUServiceConfig,
    MinerUUntrustedUrlError,
    reject_sensitive_request_options,
)


_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})


class _MinerULegacyApiRequired(RuntimeError):
    """The deployed MinerU endpoint uses the v4 batch workflow."""


class MinerUParser(BaseParserAdapter):
    """Adapter for MinerU cloud tasks, native sidecars and local compatibility runs."""

    PARSER_ID = "mineru"
    PROVIDER = "opendatalab"
    DISPLAY_NAME = "MinerU parser"
    NATIVE_FORMATS = {".pdf", ".jpg", ".jpeg", ".png"}
    MODEL_VERSIONS = ["mineru"]
    DEFAULT_MODEL_VERSION = "mineru"
    REQUIRES_NETWORK = True
    REQUIRES_GPU = False
    UNAVAILABLE_REASON = (
        "MinerU adapter is present, but no server-side cloud token or local "
        "MinerU runtime is available."
    )

    @property
    def capability(self) -> ParserCapability:
        dependency_available = (
            self._has_cloud_token()
            or find_spec("magic_pdf") is not None
            or find_spec("mineru.cli.client") is not None
        )
        return ParserCapability(
            parser_id=self.PARSER_ID,
            provider=self.PROVIDER,
            display_name=self.DISPLAY_NAME,
            formats=self.NATIVE_FORMATS,
            model_versions=self.MODEL_VERSIONS,
            default_model_version=self.DEFAULT_MODEL_VERSION,
            requires_network=self.REQUIRES_NETWORK,
            requires_gpu=self.REQUIRES_GPU,
            available=dependency_available,
            unavailable_reason=None if dependency_available else self.UNAVAILABLE_REASON,
        )

    def build_native_result(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNativeResult:
        reject_sensitive_request_options(request.options)
        sidecar_result = self._build_native_result_from_options(request, signals)
        if sidecar_result is not None:
            return self._with_mineru_payload(
                sidecar_result,
                warning="MinerU native sidecar was loaded from parser options.",
            )
        if self._should_use_cloud_path(request):
            cloud_result = self._build_with_mineru_cloud(request, signals)
            if cloud_result is not None:
                return cloud_result
        if signals.extension not in self.NATIVE_FORMATS:
            return self._build_placeholder_native_result(
                request,
                signals,
                warnings=[f"MinerU does not support direct parsing for {signals.extension}."],
            )
        if find_spec("magic_pdf") is not None:
            return self._build_with_magic_pdf(request, signals)
        if find_spec("mineru.cli.client") is not None:
            return self._build_with_mineru_cli(request, signals)
        return self._build_placeholder_native_result(
            request,
            signals,
            warnings=[self.UNAVAILABLE_REASON],
        )

    def _should_use_cloud_path(self, request: ParseRequest) -> bool:
        if request.options.get("mineru_force_local") is True:
            return False
        service_config = self._service_config()
        if not service_config.allow_cloud or _is_explicit_false(request.options.get("allow_cloud")):
            return False
        if service_config.api_token:
            return True
        return request.options.get("api_mode") in {"precise", "cloud"}

    def _has_cloud_token(self) -> bool:
        token = os.getenv("MINERU_API_TOKEN")
        return bool(token and token.strip())

    def _service_config(self) -> MinerUServiceConfig:
        return MinerUServiceConfig.from_environment()

    def _resolved_mineru_api_base_url(self, request: ParseRequest) -> str:
        del request
        return self._service_config().api_base_url

    def _resolved_mineru_api_token(self, request: ParseRequest) -> str | None:
        del request
        return self._service_config().api_token

    def _build_with_mineru_cloud(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNativeResult | None:
        """Submit the document to MinerU's task API and normalize the returned ZIP."""

        if signals.extension not in self.NATIVE_FORMATS:
            return None

        started = time.perf_counter()
        parser_version = self._installed_version("mineru", self.DEFAULT_MODEL_VERSION)
        service_config = self._service_config()
        base_url = service_config.api_base_url
        token = service_config.api_token
        try:
            api_client = import_module("mineru.cli.api_client")
            httpx = import_module("httpx")
        except Exception as error:
            raise self._execution_error_from_exception(
                phase="cloud client initialization",
                error=error,
                default_kind="unavailable",
                default_retryable=False,
            ) from error

        with tempfile.TemporaryDirectory(prefix="mineru-cloud-run-") as temporary:
            work_dir = Path(temporary)
            source_path = work_dir / f"source{signals.extension or Path(request.filename).suffix}"
            output_dir = work_dir / "output"
            source_path.write_bytes(request.content)
            try:
                route_options = self._mineru_route_options(
                    request, signals, service_config=service_config
                )
                form_data = api_client.build_parse_request_form_data(
                    lang_list=[route_options["lang"]],
                    backend=route_options["backend"],
                    parse_method=route_options["method"],
                    formula_enable=route_options["formula_enable"],
                    table_enable=route_options["table_enable"],
                    server_url=route_options["server_url"],
                    start_page_id=route_options["start_page_id"],
                    end_page_id=route_options["end_page_id"],
                    effort=route_options["effort"],
                    image_analysis=route_options["image_analysis"],
                    return_md=True,
                    return_middle_json=True,
                    return_model_output=True,
                    return_content_list=True,
                    return_images=True,
                    response_format_zip=True,
                    return_original_file=True,
                    client_side_output_generation=False,
                )
                headers = {
                    "Accept": "application/json",
                    "User-Agent": "document_parser/parse-integration",
                }
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                task_info = self._submit_mineru_task(
                    httpx=httpx,
                    base_url=base_url,
                    source_path=source_path,
                    form_data=form_data,
                    headers=headers,
                )
                task_info = self._validated_task_info(
                    task_info,
                    service_config=service_config,
                )
                self._wait_for_mineru_task(
                    httpx=httpx,
                    task_info=task_info,
                    headers=headers,
                    timeout_seconds=float(route_options["timeout_seconds"]),
                )
                zip_path = self._download_mineru_result(
                    httpx=httpx,
                    task_info=task_info,
                    headers=headers,
                    timeout_seconds=float(route_options["download_timeout_seconds"]),
                )
                try:
                    api_client.safe_extract_zip(zip_path, output_dir)
                finally:
                    zip_path.unlink(missing_ok=True)
                native_result = self._build_native_result_from_output_dir(
                    request,
                    signals,
                    output_dir,
                    parser_version=parser_version,
                )
                self._require_real_mineru_output(
                    native_result,
                    execution_name="cloud task",
                )
            except _MinerULegacyApiRequired:
                # MinerU's current public v4 service exposes the batch upload
                # workflow, while some deployments still answer the older
                # /tasks endpoint with 405.  Reuse the repository's verified
                # v4 compatibility client and convert its result into the
                # same native contract used by the modern adapter.
                native_result = self._build_native_result_from_legacy_cloud(
                    request,
                    signals,
                    source_path,
                    service_config=service_config,
                )
                self._require_real_mineru_output(
                    native_result,
                    execution_name="cloud batch task",
                )
            except MinerUSecurityError:
                # Security policy failures already have safe, actionable types and
                # must not be downgraded into a placeholder result.
                raise
            except ParserExecutionError:
                raise
            except Exception as error:
                raise self._execution_error_from_exception(
                    phase="cloud task",
                    error=error,
                ) from error

        return self._with_mineru_payload(
            native_result,
            warning=(
                "MinerU cloud task completed in "
                f"{int((time.perf_counter() - started) * 1000)} ms."
            ),
        )

    def _build_native_result_from_legacy_cloud(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
        source_path: Path,
        *,
        service_config: MinerUServiceConfig,
    ) -> ParserNativeResult:
        """Run the verified v4 batch client and adapt its document result.

        The compatibility client owns the upload-url, polling and signed-zip
        details.  This method only translates its already parsed result into
        ``ParserNativeResult`` so the normal quality and storage pipeline remains
        unchanged.
        """

        try:
            from .cloud_client import parse_pdf
        except Exception as error:
            raise self._execution_error_from_exception(
                phase="cloud batch client initialization",
                error=error,
                default_kind="unavailable",
                default_retryable=False,
            ) from error

        try:
            parsed = parse_pdf(
                source_path,
                api_key=service_config.api_token,
                is_ocr=signals.extension in {".jpg", ".jpeg", ".png"}
                or signals.has_text_layer is False,
                model_version="pipeline",
                enable_formula=bool(request.options.get("enable_formula", True)),
                enable_table=bool(request.options.get("enable_table", True)),
                work_dir=source_path.parent / "mineru-batch-output",
            )
        except Exception as error:
            raise self._execution_error_from_exception(
                phase="cloud batch task",
                error=error,
            ) from error

        source_sha256 = hashlib.sha256(request.content).hexdigest()
        content_items = [
            {
                **block.model_dump(mode="json"),
                "id": block.source_block_id or f"mineru-{index:04d}",
                "type": (
                    "title"
                    if block.heading_level
                    else "text"
                ),
                "text_level": block.heading_level,
                "text": block.text or block.markdown,
                "bbox": list(block.anchor.bbox) if block.anchor.bbox else None,
                "page_idx": (
                    block.anchor.page_number - 1
                    if block.anchor.page_number is not None
                    else None
                ),
            }
            for index, block in enumerate(parsed.blocks)
            if block.kind.value != "table"
        ]
        table_items = [
            {
                **table.model_dump(mode="json"),
                # The compatibility client exposes table image names but not
                # asset objects.  Keep the image in native_files below, while
                # leaving the public table reference unset until it is linked
                # as a first-class package asset.
                "image_path": None,
            }
            for table in parsed.tables
        ]
        payload = {
            "content_list": content_items,
            "tables": table_items,
        }
        native_files: dict[str, bytes] = {
            "native/full.md": parsed.markdown.encode("utf-8"),
            "native/content_list.json": json.dumps(
                content_items,
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
        }
        extracted_root = source_path.parent / "mineru-batch-output" / "mineru_output"
        if extracted_root.is_dir():
            for file_path in extracted_root.rglob("*"):
                if file_path.is_file():
                    relative = file_path.relative_to(extracted_root).as_posix()
                    native_files[f"native/{relative}"] = file_path.read_bytes()
        artifacts = [
            self._native_artifact(
                path=path,
                content=content,
                artifact_type=self._artifact_type_for_path(path),
                required_for_quality=path.endswith(".json"),
            )
            for path, content in native_files.items()
        ]

        return ParserNativeResult(
            document_id=make_stable_document_id(
                source_sha256=source_sha256,
                parser_id=self.PARSER_ID,
                parser_version="v4",
            ),
            parser_id=self.PARSER_ID,
            parser_version="v4",
            filename=request.filename,
            file_type=request.file_type,
            source_size_bytes=len(request.content),
            source_sha256=source_sha256,
            options=self._public_options(request.options),
            markdown=parsed.markdown,
            payload=payload,
            native_artifacts=artifacts,
            native_files=native_files,
            warnings=list(parsed.warnings),
            capabilities=self._default_capabilities(
                missing_reason="MinerU cloud batch output did not provide this evidence.",
                text_available=bool(parsed.markdown.strip()),
            ),
        )

    def _mineru_route_options(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
        *,
        service_config: MinerUServiceConfig | None = None,
    ) -> dict[str, Any]:
        options = request.options
        config = service_config or self._service_config()
        needs_ocr = (
            signals.extension in {".jpg", ".jpeg", ".png"}
            or signals.has_text_layer is False
        )
        backend = str(
            options.get("mineru_backend") or options.get("backend") or "pipeline"
        )
        method = str(
            options.get("mineru_parse_method")
            or options.get("parse_method")
            or ("ocr" if needs_ocr else "auto")
        )
        effort = str(options.get("mineru_effort") or options.get("effort") or "medium")
        lang = str(
            options.get("language")
            or options.get("mineru_language")
            or _mineru_language(signals.language_hint)
        )

        def as_bool(value: Any, default: bool) -> bool:
            if value is None:
                return default
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"1", "true", "yes", "on"}:
                    return True
                if normalized in {"0", "false", "no", "off"}:
                    return False
            return default

        def as_int(value: Any, default: int) -> int:
            if value is None:
                return default
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        return {
            "backend": backend,
            "method": method,
            "effort": effort,
            "lang": lang,
            "server_url": None,
            "formula_enable": as_bool(options.get("enable_formula"), True),
            "table_enable": as_bool(options.get("enable_table"), True),
            "image_analysis": as_bool(options.get("image_analysis"), True),
            "start_page_id": as_int(options.get("start_page_id"), 0),
            "end_page_id": as_int(options.get("end_page_id"), 99999)
            if options.get("end_page_id") is not None
            else None,
            "timeout_seconds": config.task_timeout_seconds,
            "download_timeout_seconds": config.download_timeout_seconds,
        }

    def _validated_task_info(
        self,
        task_info: dict[str, Any],
        *,
        service_config: MinerUServiceConfig,
    ) -> dict[str, str]:
        task_id = task_info.get("task_id")
        status_url = task_info.get("status_url")
        result_url = task_info.get("result_url")
        if not all(
            isinstance(value, str) and value
            for value in (task_id, status_url, result_url)
        ):
            raise RuntimeError("MinerU API returned an invalid task payload")
        return {
            "task_id": task_id,
            "status_url": service_config.validate_callback_url(
                status_url,
                kind="status",
            ),
            "result_url": service_config.validate_callback_url(
                result_url,
                kind="result",
            ),
        }

    def _submit_mineru_task(
        self,
        *,
        httpx: Any,
        base_url: str,
        source_path: Path,
        form_data: dict[str, str | list[str]],
        headers: dict[str, str],
    ) -> dict[str, str]:
        service_config = self._service_config()
        if base_url != service_config.api_base_url:
            raise MinerUConfigurationError(
                "MinerU task submission must use the configured server API base URL."
            )
        task_url = service_config.validate_callback_url(
            f"{base_url}/tasks",
            kind="task submission",
        )
        mime_type = (
            "application/pdf"
            if source_path.suffix.lower() == ".pdf"
            else "application/octet-stream"
        )
        with httpx.Client(timeout=60.0, follow_redirects=False) as client:
            with source_path.open("rb") as handle:
                response = client.post(
                    task_url,
                    data=form_data,
                    files=[("files", (source_path.name, handle, mime_type))],
                    headers=headers,
                )
        self._reject_submission_redirect(
            response,
            current_url=task_url,
            service_config=service_config,
        )
        if response.status_code == 405:
            raise _MinerULegacyApiRequired()
        if response.status_code != 202:
            raise RuntimeError(
                f"MinerU task submission failed: {response.status_code} {response.text.strip()}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("MinerU API returned an invalid task payload")
        return self._validated_task_info(payload, service_config=service_config)

    def _wait_for_mineru_task(
        self,
        *,
        httpx: Any,
        task_info: dict[str, str],
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> None:
        service_config = self._service_config()
        task_info = self._validated_task_info(task_info, service_config=service_config)
        deadline = time.perf_counter() + timeout_seconds
        with httpx.Client(timeout=30.0, follow_redirects=False) as client:
            while time.perf_counter() < deadline:
                response = self._get_with_trusted_redirects(
                    client,
                    url=task_info["status_url"],
                    headers=headers,
                    service_config=service_config,
                    kind="status",
                )
                if response.status_code != 200:
                    raise RuntimeError(
                        "MinerU task status query failed: "
                        f"{response.status_code} {response.text.strip()}"
                    )
                payload = response.json()
                status = payload.get("status")
                if status in {"pending", "processing"}:
                    time.sleep(1.0)
                    continue
                if status == "completed":
                    return
                raise RuntimeError(
                    f"MinerU task {task_info['task_id']} failed: "
                    f"{json.dumps(payload, ensure_ascii=False)}"
                )
        raise RuntimeError(f"Timed out waiting for MinerU task {task_info['task_id']}")

    def _download_mineru_result(
        self,
        *,
        httpx: Any,
        task_info: dict[str, str],
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> Path:
        service_config = self._service_config()
        task_info = self._validated_task_info(task_info, service_config=service_config)
        result_fd, result_file = tempfile.mkstemp(suffix=".zip", prefix="mineru_result_")
        os.close(result_fd)
        result_path = Path(result_file)
        original_url = task_info["result_url"]
        current_url = original_url
        try:
            with httpx.Client(timeout=timeout_seconds, follow_redirects=False) as client:
                for redirect_count in range(service_config.max_redirects + 1):
                    with client.stream(
                        "GET",
                        current_url,
                        headers=self._headers_for_url(
                            headers,
                            original_url=original_url,
                            current_url=current_url,
                        ),
                    ) as response:
                        if response.status_code in _REDIRECT_STATUS_CODES:
                            if redirect_count >= service_config.max_redirects:
                                raise MinerUUntrustedUrlError(
                                    "MinerU result download exceeded the trusted redirect limit."
                                )
                            current_url = service_config.resolve_redirect_url(
                                current_url,
                                response.headers.get("location", ""),
                            )
                            continue
                        if response.status_code != 200:
                            raise RuntimeError(
                                "MinerU result download failed: "
                                f"{response.status_code} {response.text.strip()}"
                            )
                        content_type = response.headers.get("content-type", "").lower()
                        if "application/zip" not in content_type:
                            raise RuntimeError(
                                f"MinerU result was not a zip archive: {content_type or 'unknown'}"
                            )
                        with result_path.open("wb") as handle:
                            for chunk in response.iter_bytes():
                                handle.write(chunk)
                        return result_path
            raise MinerUUntrustedUrlError(
                "MinerU result download exceeded the trusted redirect limit."
            )
        except Exception:
            result_path.unlink(missing_ok=True)
            raise

    def _reject_submission_redirect(
        self,
        response: Any,
        *,
        current_url: str,
        service_config: MinerUServiceConfig,
    ) -> None:
        if response.status_code not in _REDIRECT_STATUS_CODES:
            return
        target = service_config.resolve_redirect_url(
            current_url,
            response.headers.get("location", ""),
        )
        raise MinerUUntrustedUrlError(
            "MinerU task submission redirects are not accepted after validation: "
            f"{target}"
        )

    def _get_with_trusted_redirects(
        self,
        client: Any,
        *,
        url: str,
        headers: dict[str, str],
        service_config: MinerUServiceConfig,
        kind: str,
    ) -> Any:
        original_url = service_config.validate_callback_url(url, kind=kind)
        current_url = original_url
        for redirect_count in range(service_config.max_redirects + 1):
            response = client.get(
                current_url,
                headers=self._headers_for_url(
                    headers,
                    original_url=original_url,
                    current_url=current_url,
                ),
            )
            if response.status_code not in _REDIRECT_STATUS_CODES:
                return response
            if redirect_count >= service_config.max_redirects:
                raise MinerUUntrustedUrlError(
                    f"MinerU {kind} request exceeded the trusted redirect limit."
                )
            current_url = service_config.resolve_redirect_url(
                current_url,
                response.headers.get("location", ""),
            )
            close = getattr(response, "close", None)
            if callable(close):
                close()
        raise AssertionError("Trusted redirect loop must either return or raise.")

    @staticmethod
    def _headers_for_url(
        headers: dict[str, str],
        *,
        original_url: str,
        current_url: str,
    ) -> dict[str, str]:
        request_headers = dict(headers)
        if not same_url_origin(original_url, current_url):
            request_headers.pop("Authorization", None)
        return request_headers

    def _build_with_mineru_cli(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNativeResult:
        """Run the current MinerU CLI and read the generated sidecars."""

        started = time.perf_counter()
        parser_version = self._installed_version("mineru", self.DEFAULT_MODEL_VERSION)
        try:
            with tempfile.TemporaryDirectory(prefix="mineru-cli-run-") as temporary:
                work_dir = Path(temporary)
                source_path = work_dir / f"source{signals.extension or Path(request.filename).suffix}"
                output_dir = work_dir / "output"
                source_path.write_bytes(request.content)
                command = [
                    sys.executable,
                    "-m",
                    "mineru.cli.client",
                    "-p",
                    str(source_path),
                    "-o",
                    str(output_dir),
                    "-b",
                    str(request.options.get("mineru_backend", "pipeline")),
                ]
                completed = subprocess.run(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=int(request.options.get("mineru_timeout_seconds", 900)),
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    check=False,
                )
                if completed.returncode != 0:
                    raise self.execution_error(
                        failure_kind="parser",
                        retryable=False,
                        safe_message=(
                            "MinerU CLI exited with a non-zero status "
                            f"({completed.returncode})."
                        ),
                    )
                native_result = self._build_native_result_from_output_dir(
                    request,
                    signals,
                    output_dir,
                    parser_version=parser_version,
                )
                self._require_real_mineru_output(
                    native_result,
                    execution_name="CLI",
                )
        except ParserExecutionError:
            raise
        except Exception as error:
            raise self._execution_error_from_exception(
                phase="CLI execution",
                error=error,
            ) from error
        return self._with_mineru_payload(
            native_result,
            warning=f"MinerU CLI run completed in {int((time.perf_counter() - started) * 1000)} ms.",
        )

    def normalize(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNormalizationBundle:
        """Execute through the plugin port, then add MinerU-specific evidence."""

        native_result = self.execute(request, signals)
        try:
            return self._normalize_mineru_native_result(native_result, request, signals)
        except ParserExecutionError:
            raise
        except Exception as error:
            raise self.diagnose(error, request=request, signals=signals) from error

    def _normalize_mineru_native_result(
        self,
        native_result: ParserNativeResult,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNormalizationBundle:
        bundle = self.normalize_native_result(native_result, request, signals)
        assets = self._assets_from_native_files(native_result, bundle)
        capabilities = dict(bundle.capabilities)
        if assets:
            capabilities["assets"] = partial_capability(
                "MinerU image files were preserved as package assets; block-to-asset linkage depends on native image paths.",
                granularity="asset",
                evidence={"asset_count": len(assets)},
            )
        if bundle.tables and any(table.cells for table in bundle.tables):
            cell_count = sum(len(table.cells) for table in bundle.tables)
            cells_with_bbox = sum(
                1 for table in bundle.tables for cell in table.cells if cell.bbox is not None
            )
            if cells_with_bbox < cell_count:
                capabilities["table_cells"] = partial_capability(
                    "MinerU provided table grid cells, but not every cell has a real bbox.",
                    granularity="cell",
                    evidence={
                        "table_count": len(bundle.tables),
                        "cell_count": cell_count,
                        "cells_with_bbox": cells_with_bbox,
                    },
                )
        return bundle.model_copy(update={"assets": assets, "capabilities": capabilities})

    def _build_with_magic_pdf(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNativeResult:
        """Run an installed MinerU/magic-pdf pipeline and read its sidecars."""

        if signals.extension != ".pdf":
            return self._build_placeholder_native_result(
                request,
                signals,
                warnings=["Local magic-pdf integration currently runs PDF inputs only."],
            )

        started = time.perf_counter()
        try:
            with tempfile.TemporaryDirectory(prefix="mineru-run-") as temporary:
                output_dir = Path(temporary) / "output"
                output_dir.mkdir(parents=True, exist_ok=True)
                self._run_magic_pdf_pipeline(request.content, output_dir)
                native_result = self._build_native_result_from_output_dir(
                    request,
                    signals,
                    output_dir,
                    parser_version=self._installed_version(
                        "magic-pdf", self.DEFAULT_MODEL_VERSION
                    ),
                )
                self._require_real_mineru_output(
                    native_result,
                    execution_name="local magic-pdf",
                )
        except ParserExecutionError:
            raise
        except Exception as error:
            raise self._execution_error_from_exception(
                phase="local magic-pdf execution",
                error=error,
            ) from error
        return self._with_mineru_payload(
            native_result,
            warning=f"MinerU local magic-pdf run completed in {int((time.perf_counter() - started) * 1000)} ms.",
        )

    def _run_magic_pdf_pipeline(self, content: bytes, output_dir: Path) -> None:
        """Use the common MinerU 1.x Python API when it is installed."""

        SupportedPdfParseMethod = import_module("magic_pdf.config.enums").SupportedPdfParseMethod
        FileBasedDataWriter = import_module("magic_pdf.data.data_reader_writer").FileBasedDataWriter
        PymuDocDataset = import_module("magic_pdf.data.dataset").PymuDocDataset
        doc_analyze = import_module("magic_pdf.model.doc_analyze_by_custom_model").doc_analyze

        image_dir_name = "images"
        image_dir = output_dir / image_dir_name
        image_dir.mkdir(parents=True, exist_ok=True)
        image_writer = FileBasedDataWriter(str(image_dir))
        markdown_writer = FileBasedDataWriter(str(output_dir))
        dataset = PymuDocDataset(content)
        if dataset.classify() == SupportedPdfParseMethod.OCR:
            infer_result = dataset.apply(doc_analyze, ocr=True)
            pipe_result = infer_result.pipe_ocr_mode(image_writer)
        else:
            infer_result = dataset.apply(doc_analyze, ocr=False)
            pipe_result = infer_result.pipe_txt_mode(image_writer)
        pipe_result.dump_md(markdown_writer, "full.md", image_dir_name)
        pipe_result.dump_content_list(markdown_writer, "content_list.json", image_dir_name)
        pipe_result.dump_middle_json(markdown_writer, "middle.json")

    def _require_real_mineru_output(
        self,
        native_result: ParserNativeResult,
        *,
        execution_name: str,
    ) -> None:
        """Reject a zero-exit runtime that emitted no actual parser content."""

        native_files = native_result.native_files
        has_markdown = bool(
            isinstance(native_result.markdown, str) and native_result.markdown.strip()
        ) and any(
            Path(file_path).suffix.lower() in {".md", ".markdown"}
            and self._nonempty_native_content(content)
            for file_path, content in native_files.items()
        )
        has_structured_output = any(
            self._is_mineru_structured_sidecar(file_path, content)
            for file_path, content in native_files.items()
        )
        if has_markdown and has_structured_output:
            return
        raise self.execution_error(
            failure_kind="parser",
            retryable=False,
            safe_message=(
                f"MinerU {execution_name} completed without required Markdown "
                "and structured parser sidecars."
            ),
        )

    @staticmethod
    def _nonempty_native_content(value: Any) -> bool:
        if isinstance(value, bytes):
            return bool(value.strip())
        if isinstance(value, str):
            return bool(value.strip())
        return bool(value)

    @classmethod
    def _is_mineru_structured_sidecar(cls, file_path: str, content: Any) -> bool:
        """Accept expected parse content, not generic JSON diagnostics."""

        name = Path(file_path).name.lower()
        is_content_list = "content_list" in name and name.endswith(".json")
        is_middle = name == "middle.json" or name.endswith("_middle.json")
        if not (is_content_list or is_middle) or not cls._nonempty_native_content(content):
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

    def _execution_error_from_exception(
        self,
        *,
        phase: str,
        error: Exception,
        default_kind: str = "parser",
        default_retryable: bool = False,
    ) -> ParserExecutionError:
        """Convert third-party runtime details to a bounded, portable error."""

        detail = f"{type(error).__name__} {error}".lower()
        if isinstance(error, (TimeoutError, subprocess.TimeoutExpired)) or "timeout" in detail:
            return self.execution_error(
                failure_kind="transient",
                retryable=True,
                safe_message=f"MinerU {phase} timed out (transient timeout).",
            )
        if any(marker in detail for marker in ("connection", "temporar", "rate limit")):
            return self.execution_error(
                failure_kind="transient",
                retryable=True,
                safe_message=f"MinerU {phase} encountered a transient connection failure.",
            )
        if any(marker in detail for marker in ("not installed", "modulenotfound", "no module named")):
            return self.execution_error(
                failure_kind="unavailable",
                retryable=False,
                safe_message=f"MinerU {phase} dependency is unavailable.",
            )
        return self.execution_error(
            failure_kind=default_kind,
            retryable=default_retryable,
            safe_message=f"MinerU {phase} failed.",
        )


    def _with_mineru_payload(
        self,
        native_result: ParserNativeResult,
        *,
        warning: str,
    ) -> ParserNativeResult:
        payload = self._canonical_mineru_payload(
            native_result.payload,
            native_files=native_result.native_files,
        )
        markdown = native_result.markdown or self._markdown_from_payload(payload)
        native_files = dict(native_result.native_files)
        artifacts = list(native_result.native_artifacts)
        result_path = "native/mineru_result.json"
        result_bytes = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        native_files[result_path] = result_bytes
        artifacts = [artifact for artifact in artifacts if artifact.path != result_path]
        artifacts.append(
            self._native_artifact(
                path=result_path,
                content=result_bytes,
                artifact_type="structured_content",
                file_type="application/json",
                required_for_quality=True,
            )
        )
        return native_result.model_copy(
            update={
                "markdown": markdown,
                "payload": payload,
                "native_files": native_files,
                "native_artifacts": artifacts,
                "warnings": [warning, *native_result.warnings],
            }
        )

    def _canonical_mineru_payload(
        self,
        payload: dict[str, Any],
        *,
        native_files: dict[str, bytes],
    ) -> dict[str, Any]:
        items = self._mineru_items(payload)
        raw_tables = self._mineru_tables(payload)
        if not items and not raw_tables:
            return payload
        blocks: list[dict[str, Any]] = []
        normalized_tables: list[dict[str, Any]] = []
        for index, raw in enumerate(items):
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            native_type = str(item.get("type") or item.get("category") or "text")
            kind = self._mineru_kind(item)
            source_block_id = str(item.get("id") or item.get("source_block_id") or f"mineru-{index:04d}")
            normalized = {
                **item,
                "id": source_block_id,
                "source_block_id": source_block_id,
                "order_index": index,
                "native_type": native_type,
                "type": kind,
            }
            text = self._mineru_text(item, kind=kind)
            if text:
                normalized["text"] = text
            if "page_idx" in item:
                normalized["page_idx"] = item["page_idx"]
            asset_path = self._asset_path_for_reference(item, native_files=native_files)
            if asset_path:
                normalized["asset_path"] = asset_path
                normalized["image_path"] = f"assets/{asset_path}"
            if kind == "table":
                self._populate_table_fields(normalized, item)
                normalized_tables.append(normalized)
            elif kind == "image" and asset_path:
                caption = text or "MinerU image"
                normalized["markdown"] = f"![{caption}](assets/{asset_path})"
            elif kind == "formula" and text:
                normalized["markdown"] = f"$$\n{text}\n$$"
            blocks.append(normalized)
        for index, raw in enumerate(raw_tables):
            if not isinstance(raw, dict):
                continue
            table = dict(raw)
            source_block_id = str(table.get("id") or table.get("source_block_id") or f"mineru-table-{index:04d}")
            normalized = {
                **table,
                "id": source_block_id,
                "source_block_id": source_block_id,
                "order_index": table.get("order_index", len(blocks) + index),
                "native_type": str(table.get("type") or "table"),
                "type": "table",
            }
            text = self._mineru_text(table, kind="table")
            if text:
                normalized["text"] = text
            self._populate_table_fields(normalized, table)
            blocks.append(normalized)
            normalized_tables.append(normalized)
        return {
            **payload,
            "blocks": blocks,
            "tables": normalized_tables,
            "content_list": items,
        }

    def _mineru_items(self, payload: dict[str, Any]) -> list[Any]:
        for key in ("content_list", "items", "content"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        blocks = payload.get("blocks")
        if isinstance(blocks, list):
            return [
                item
                for item in blocks
                if isinstance(item, dict) and self._mineru_kind(item) != "table"
            ]
        tables = payload.get("tables")
        if isinstance(tables, list):
            return []
        return []

    def _mineru_tables(self, payload: dict[str, Any]) -> list[Any]:
        tables = payload.get("tables")
        if isinstance(tables, list):
            return tables
        blocks = payload.get("blocks")
        if isinstance(blocks, list):
            return [
                item
                for item in blocks
                if isinstance(item, dict) and self._mineru_kind(item) == "table"
            ]
        return []

    def _mineru_kind(self, item: dict[str, Any]) -> str:
        raw = str(item.get("type") or item.get("category") or "").lower()
        if "table" in raw:
            return "table"
        if "image" in raw or "figure" in raw:
            return "image"
        if "equation" in raw or "formula" in raw:
            return "formula"
        if raw in {"title", "heading"} or isinstance(item.get("text_level"), int):
            return "title"
        if "list" in raw:
            return "list"
        return "text"

    def _mineru_text(self, item: dict[str, Any], *, kind: str) -> str:
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        if kind == "table":
            caption = self._join_mineru_text(item.get("table_caption"))
            footnote = self._join_mineru_text(item.get("table_footnote"))
            return "\n".join(part for part in (caption, footnote) if part).strip()
        if kind == "image":
            caption = self._join_mineru_text(item.get("image_caption"))
            footnote = self._join_mineru_text(item.get("image_footnote"))
            return "\n".join(part for part in (caption, footnote) if part).strip()
        for key in ("latex", "equation", "content"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _join_mineru_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            return " ".join(str(item).strip() for item in value if str(item).strip())
        return ""

    def _populate_table_fields(self, normalized: dict[str, Any], item: dict[str, Any]) -> None:
        html = item.get("table_body") or item.get("html")
        if isinstance(html, str) and html.strip():
            normalized["html"] = html.strip()
            normalized["markdown"] = html.strip()
            cells = _parse_html_table_cells(html)
            if cells:
                normalized["cells"] = cells
                normalized["num_rows"] = max(cell["start_row"] + cell["row_span"] for cell in cells)
                normalized["num_cols"] = max(cell["start_col"] + cell["col_span"] for cell in cells)
        caption = self._join_mineru_text(item.get("table_caption"))
        if caption:
            normalized["caption"] = caption

    def _asset_path_for_reference(
        self,
        item: dict[str, Any],
        *,
        native_files: dict[str, bytes],
    ) -> str | None:
        for key in ("img_path", "image_path", "table_img_path"):
            value = item.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            normalized = value.replace("\\", "/").lstrip("/")
            candidates = [
                f"native/{normalized}",
                f"native/images/{Path(normalized).name}",
                f"native/{Path(normalized).name}",
            ]
            for candidate in candidates:
                if candidate in native_files:
                    return f"mineru/{candidate.removeprefix('native/')}"
        return None

    def _assets_from_native_files(
        self,
        native_result: ParserNativeResult,
        bundle: ParserNormalizationBundle,
    ) -> list[DocumentAsset]:
        referenced_by_asset_path: dict[str, list[str]] = {}
        for block in bundle.blocks:
            asset_path = block.metadata.get("asset_path")
            if isinstance(asset_path, str):
                referenced_by_asset_path.setdefault(asset_path, []).append(str(block.id))

        assets: list[DocumentAsset] = []
        for native_path, content in native_result.native_files.items():
            suffix = Path(native_path).suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            relative = native_path.replace("\\", "/").removeprefix("native/")
            asset_path = f"mineru/{relative}"
            assets.append(
                DocumentAsset(
                    path=asset_path,
                    kind=AssetKind.IMAGE,
                    file_type=self._file_type_for_path(native_path),
                    content=content,
                    sha256=hashlib.sha256(content).hexdigest(),
                    referenced_by_block_ids=referenced_by_asset_path.get(asset_path, []),
                    metadata={"native_path": native_path},
                )
            )
        return assets

    def _markdown_from_payload(self, payload: dict[str, Any]) -> str:
        parts: list[str] = []
        for item in payload.get("blocks", []):
            if not isinstance(item, dict):
                continue
            markdown = item.get("markdown")
            if isinstance(markdown, str) and markdown.strip():
                parts.append(markdown.strip())
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                if item.get("type") == "title":
                    level = item.get("text_level") if isinstance(item.get("text_level"), int) else 1
                    parts.append(f"{'#' * max(1, level)} {text.strip()}")
                else:
                    parts.append(text.strip())
        return "\n\n".join(parts)


class _HtmlTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.cells: list[dict[str, Any]] = []
        self._row = -1
        self._col = 0
        self._active: dict[str, Any] | None = None
        self._text: list[str] = []
        self._occupied: dict[int, set[int]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row += 1
            self._col = 0
            return
        if tag not in {"td", "th"} or self._row < 0:
            return
        occupied = self._occupied.setdefault(self._row, set())
        while self._col in occupied:
            self._col += 1
        attr_map = {name.lower(): value for name, value in attrs}
        row_span = _positive_int(attr_map.get("rowspan"), default=1)
        col_span = _positive_int(attr_map.get("colspan"), default=1)
        self._active = {
            "start_row": self._row,
            "start_col": self._col,
            "row_span": row_span,
            "col_span": col_span,
            "column_header": tag == "th" or self._row == 0,
            "row_header": tag == "th" and self._col == 0,
        }
        self._text = []
        for row in range(self._row, self._row + row_span):
            row_occupied = self._occupied.setdefault(row, set())
            for col in range(self._col, self._col + col_span):
                row_occupied.add(col)

    def handle_data(self, data: str) -> None:
        if self._active is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag not in {"td", "th"} or self._active is None:
            return
        text = re.sub(r"\s+", " ", "".join(self._text)).strip()
        self.cells.append({**self._active, "text": text})
        self._col = self._active["start_col"] + self._active["col_span"]
        self._active = None
        self._text = []


def _parse_html_table_cells(html: str) -> list[dict[str, Any]]:
    parser = _HtmlTableParser()
    parser.feed(html)
    return parser.cells


def _is_explicit_false(value: object) -> bool:
    if value is False:
        return True
    if isinstance(value, int) and not isinstance(value, bool):
        return value == 0
    if isinstance(value, str):
        return value.strip().lower() in {"0", "false", "no", "off"}
    return False


def _positive_int(value: str | None, *, default: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _mineru_language(language_hint: str | None) -> str:
    if not language_hint:
        return "ch"
    normalized = language_hint.lower()
    if normalized.startswith(("zh", "ch")):
        return "ch"
    if normalized.startswith("en"):
        return "en"
    return "latin"
