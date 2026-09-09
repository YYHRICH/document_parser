"""MinerU parser adapter."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from html.parser import HTMLParser
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from ....domain.model.contracts import (
    AssetKind,
    DocumentAsset,
    DocumentSignals,
    ParseRequest,
    ParserCapability,
    ParserNativeResult,
)
from ....domain.normalization import (
    ParserNormalizationBundle,
    make_stable_document_id,
    partial_capability,
    unavailable_capability,
)
from ....domain.routing.ids import MINERU_ID
from ..base import BaseParserAdapter


class MinerUParser(BaseParserAdapter):
    """Adapter for MinerU cloud tasks, native sidecars and local compatibility runs."""

    PARSER_ID = MINERU_ID
    PROVIDER = "opendatalab"
    DISPLAY_NAME = "MinerU parser"
    NATIVE_FORMATS = {".pdf", ".jpg", ".jpeg", ".png"}
    MODEL_VERSIONS = ["mineru"]
    DEFAULT_MODEL_VERSION = "mineru"
    REQUIRES_NETWORK = True
    REQUIRES_GPU = False
    UNAVAILABLE_REASON = (
        "MinerU adapter is present, but no cloud token or local MinerU runtime is available. "
        "Pass options.native_output_dir to normalize an existing MinerU output directory."
    )

    @property
    def capability(self) -> ParserCapability:
        local_runtime_available = (
            find_spec("mineru") is not None
            or find_spec("magic_pdf") is not None
            or shutil.which("mineru") is not None
            or shutil.which("mineru.cmd") is not None
        )
        dependency_available = self._has_cloud_token() or local_runtime_available
        return ParserCapability(
            parser_id=self.PARSER_ID,
            provider=self.PROVIDER,
            display_name=self.DISPLAY_NAME,
            formats=self.NATIVE_FORMATS,
            model_versions=self.MODEL_VERSIONS,
            default_model_version=self.DEFAULT_MODEL_VERSION,
            requires_network=not local_runtime_available,
            requires_gpu=self.REQUIRES_GPU,
            available=dependency_available,
            unavailable_reason=None if dependency_available else self.UNAVAILABLE_REASON,
        )

    def build_native_result(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNativeResult:
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
        if find_spec("mineru") is not None or shutil.which("mineru") is not None:
            return self._build_with_mineru_cli(request, signals)
        return self._build_placeholder_native_result(
            request,
            signals,
            warnings=[self.UNAVAILABLE_REASON],
        )

    def _should_use_cloud_path(self, request: ParseRequest) -> bool:
        if request.options.get("mineru_force_local") is True:
            return False
        if self._has_cloud_token() or bool(request.options.get("mineru_api_token")):
            return True
        return request.options.get("api_mode") in {"precise", "cloud"}

    def _has_cloud_token(self) -> bool:
        token = os.getenv("MINERU_API_TOKEN")
        return bool(token and token.strip())

    def _resolved_mineru_api_base_url(self, request: ParseRequest) -> str:
        raw = request.options.get("mineru_api_base_url") or os.getenv(
            "MINERU_API_BASE_URL", "https://mineru.net/api/v4"
        )
        return str(raw).rstrip("/")

    def _resolved_mineru_api_token(self, request: ParseRequest) -> str | None:
        value = request.options.get("mineru_api_token") or os.getenv("MINERU_API_TOKEN")
        if isinstance(value, str):
            token = value.strip()
            return token or None
        return None

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
        base_url = self._resolved_mineru_api_base_url(request)
        token = self._resolved_mineru_api_token(request)
        try:
            try:
                api_client = import_module("mineru.cli.api_client")
            except Exception:
                api_client = None
            httpx = import_module("httpx")
        except Exception as error:
            return self._build_placeholder_native_result(
                request,
                signals,
                parser_version=parser_version,
                warnings=[f"MinerU cloud client could not be loaded: {error}"],
            )

        with tempfile.TemporaryDirectory(prefix="mineru-cloud-run-") as temporary:
            work_dir = Path(temporary)
            source_path = work_dir / f"source{signals.extension or Path(request.filename).suffix}"
            output_dir = work_dir / "output"
            source_path.write_bytes(request.content)

            route_options = self._mineru_route_options(request, signals)
            headers = {
                "Accept": "application/json",
                "User-Agent": "document_parser/parse-integration",
            }
            if token:
                headers["Authorization"] = f"Bearer {token}"

            try:
                task_info = self._submit_mineru_batch_task(
                    httpx=httpx,
                    base_url=base_url,
                    source_path=source_path,
                    route_options=route_options,
                    headers=headers,
                )
                result_url = self._wait_for_mineru_batch_result(
                    httpx=httpx,
                    task_info=task_info,
                    headers=headers,
                    timeout_seconds=float(route_options["timeout_seconds"]),
                )
                zip_path = self._download_mineru_result(
                    httpx=httpx,
                    result_url=result_url,
                    headers=headers,
                    timeout_seconds=float(route_options["download_timeout_seconds"]),
                )
                try:
                    if api_client is not None and hasattr(api_client, "safe_extract_zip"):
                        api_client.safe_extract_zip(zip_path, output_dir)
                    else:
                        shutil.unpack_archive(zip_path, output_dir, "zip")
                finally:
                    zip_path.unlink(missing_ok=True)
                native_result = self._build_native_result_from_output_dir(
                    request,
                    signals,
                    output_dir,
                    parser_version=parser_version,
                )
            except Exception as error:
                return self._build_placeholder_native_result(
                    request,
                    signals,
                    parser_version=parser_version,
                    warnings=[f"MinerU cloud task failed: {error}"],
                )

        return self._with_mineru_payload(
            native_result,
            warning=(
                "MinerU cloud task completed in "
                f"{int((time.perf_counter() - started) * 1000)} ms."
            ),
        )

    def _mineru_route_options(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> dict[str, Any]:
        options = request.options
        needs_ocr = signals.extension in {".jpg", ".jpeg", ".png"} or signals.has_text_layer is False
        backend = str(options.get("mineru_backend") or options.get("backend") or "pipeline")
        method = str(options.get("mineru_parse_method") or options.get("parse_method") or ("ocr" if needs_ocr else "auto"))
        effort = str(options.get("mineru_effort") or options.get("effort") or "medium")
        lang = str(options.get("language") or options.get("mineru_language") or _mineru_language(signals.language_hint))
        server_url = options.get("mineru_server_url") or options.get("server_url")
        if not isinstance(server_url, str):
            server_url = None

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

        def as_float(value: Any, default: float) -> float:
            if value is None:
                return default
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        is_ocr = as_bool(
            options.get("is_ocr", options.get("mineru_is_ocr")),
            needs_ocr or method.lower() == "ocr",
        )

        return {
            "backend": backend,
            "method": method,
            "is_ocr": is_ocr,
            "effort": effort,
            "lang": lang,
            "model_version": str(options.get("model_version") or options.get("mineru_model_version") or "vlm"),
            "server_url": server_url,
            "formula_enable": as_bool(options.get("enable_formula"), True),
            "table_enable": as_bool(options.get("enable_table"), True),
            "image_analysis": as_bool(options.get("image_analysis"), True),
            "start_page_id": as_int(options.get("start_page_id"), 0),
            "end_page_id": as_int(options.get("end_page_id"), 99999)
            if options.get("end_page_id") is not None
            else None,
            "timeout_seconds": as_float(options.get("mineru_timeout_seconds"), 900.0),
            "download_timeout_seconds": as_float(
                options.get("mineru_download_timeout_seconds"),
                600.0,
            ),
        }

    def _submit_mineru_batch_task(
        self,
        *,
        httpx: Any,
        base_url: str,
        source_path: Path,
        route_options: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, str]:
        task_url = f"{base_url}/file-urls/batch"
        body = {
            "enable_formula": bool(route_options["formula_enable"]),
            "enable_table": bool(route_options["table_enable"]),
            "language": route_options["lang"],
            "model_version": route_options["model_version"],
            "files": [
                {
                    "name": source_path.name,
                    "is_ocr": bool(route_options["is_ocr"]),
                    "data_id": hashlib.sha256(source_path.read_bytes()).hexdigest()[:16],
                }
            ],
        }
        with httpx.Client(timeout=60.0, follow_redirects=True, headers=headers) as client:
            response = client.post(task_url, json=body)
            payload = self._mineru_json_payload(response, context="create upload URL")
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                raise RuntimeError("MinerU API returned an invalid upload URL payload")
            batch_id = data.get("batch_id")
            file_urls = data.get("file_urls")
            if not isinstance(batch_id, str) or not batch_id:
                raise RuntimeError("MinerU API did not return batch_id")
            if (
                not isinstance(file_urls, list)
                or not file_urls
                or not isinstance(file_urls[0], str)
            ):
                raise RuntimeError("MinerU API did not return a file upload URL")
        with httpx.Client(timeout=60.0, follow_redirects=True) as upload_client:
            upload_response = upload_client.put(file_urls[0], content=source_path.read_bytes())
            if upload_response.status_code not in {200, 201, 204}:
                raise RuntimeError(
                    "MinerU file upload failed: "
                    f"{upload_response.status_code} {upload_response.text.strip()}"
                )
        return {
            "task_id": batch_id,
            "status_url": f"{base_url}/extract-results/batch/{batch_id}",
        }

    def _wait_for_mineru_batch_result(
        self,
        *,
        httpx: Any,
        task_info: dict[str, str],
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> str:
        deadline = time.perf_counter() + timeout_seconds
        with httpx.Client(timeout=30.0, follow_redirects=True, headers=headers) as client:
            while time.perf_counter() < deadline:
                response = client.get(task_info["status_url"])
                payload = self._mineru_json_payload(response, context="query batch result")
                data = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(data, dict):
                    raise RuntimeError("MinerU API returned an invalid batch result payload")
                results = data.get("extract_result") or data.get("extract_results")
                if not isinstance(results, list) or not results:
                    time.sleep(1.0)
                    continue
                first = results[0]
                if not isinstance(first, dict):
                    raise RuntimeError("MinerU API returned an invalid file result payload")
                status = str(first.get("state") or first.get("status") or "").lower()
                if status in {
                    "waiting-file",
                    "pending",
                    "running",
                    "processing",
                    "waiting",
                    "queued",
                    "converting",
                }:
                    time.sleep(1.0)
                    continue
                if status in {"done", "completed", "success"}:
                    result_url = first.get("full_zip_url") or first.get("zip_url") or first.get("result_url")
                    if not isinstance(result_url, str) or not result_url:
                        raise RuntimeError("MinerU batch completed without full_zip_url")
                    return result_url
                raise RuntimeError(
                    f"MinerU task {task_info['task_id']} failed: {json.dumps(first, ensure_ascii=False)}"
                )
        raise RuntimeError(f"Timed out waiting for MinerU task {task_info['task_id']}")

    def _download_mineru_result(
        self,
        *,
        httpx: Any,
        result_url: str,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> Path:
        result_fd, result_file = tempfile.mkstemp(suffix=".zip", prefix="mineru_result_")
        os.close(result_fd)
        result_path = Path(result_file)
        try:
            with httpx.Client(timeout=timeout_seconds, follow_redirects=True, headers=headers) as client:
                with client.stream("GET", result_url) as response:
                    if response.status_code != 200:
                        raise RuntimeError(
                            f"MinerU result download failed: {response.status_code} {response.text.strip()}"
                        )
                    content_type = response.headers.get("content-type", "")
                    if "application/zip" not in content_type:
                        raise RuntimeError(f"MinerU result was not a zip archive: {content_type or 'unknown'}")
                    with result_path.open("wb") as handle:
                        for chunk in response.iter_bytes():
                            handle.write(chunk)
        except Exception:
            result_path.unlink(missing_ok=True)
            raise
        return result_path

    def _mineru_json_payload(self, response: Any, *, context: str) -> dict[str, Any]:
        if response.status_code != 200:
            raise RuntimeError(
                f"MinerU {context} failed: {response.status_code} {response.text.strip()}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"MinerU {context} returned a non-object payload")
        code = payload.get("code")
        if code not in {None, 0, "0", 200, "200"}:
            message = payload.get("msg") or payload.get("message") or payload
            raise RuntimeError(f"MinerU {context} failed: {message}")
        return payload

    def _build_with_mineru_cli(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNativeResult:
        """Run the current MinerU CLI and read the generated sidecars."""

        started = time.perf_counter()
        parser_version = self._installed_version("mineru", self.DEFAULT_MODEL_VERSION)
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
                message = (completed.stderr or completed.stdout).strip()
                return self._build_placeholder_native_result(
                    request,
                    signals,
                    parser_version=parser_version,
                    warnings=[f"MinerU CLI failed with exit code {completed.returncode}: {message}"],
                )
            native_result = self._build_native_result_from_output_dir(
                request,
                signals,
                output_dir,
                parser_version=parser_version,
            )
        return self._with_mineru_payload(
            native_result,
            warning=f"MinerU CLI run completed in {int((time.perf_counter() - started) * 1000)} ms.",
        )

    def normalize(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNormalizationBundle:
        native_result = self.build_native_result(request, signals)
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
        with tempfile.TemporaryDirectory(prefix="mineru-run-") as temporary:
            output_dir = Path(temporary) / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            self._run_magic_pdf_pipeline(request.content, output_dir)
            native_result = self._build_native_result_from_output_dir(
                request,
                signals,
                output_dir,
                parser_version=self._installed_version("magic-pdf", self.DEFAULT_MODEL_VERSION),
            )
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
        table_positions: dict[str, tuple[int, int]] = {}
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
                table_positions[source_block_id] = (
                    len(blocks),
                    len(normalized_tables),
                )
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
            existing_position = table_positions.get(source_block_id)
            if existing_position is not None:
                block_index, table_index = existing_position
                # Canonical MinerU sidecars may expose the same table through
                # both content_list/items and tables. Merge the richer explicit
                # table entry into the existing object so normalization remains
                # idempotent and table IDs stay unique.
                merged = {**blocks[block_index], **normalized}
                blocks[block_index] = merged
                normalized_tables[table_index] = merged
                continue
            table_positions[source_block_id] = (
                len(blocks),
                len(normalized_tables),
            )
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
