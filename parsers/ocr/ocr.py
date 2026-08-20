"""OCR 解析器骨架。"""

from __future__ import annotations

import hashlib
import json
import time
from importlib.util import find_spec
from typing import Any

from ...core.contracts import DocumentSignals, ParseRequest, ParserNativeResult
from ...normalizers import ParserNormalizationBundle, make_stable_document_id
from ..base import BaseParserAdapter


class OcrParser(BaseParserAdapter):
    """OCR 的预留入口。"""

    PARSER_ID = "ocr"
    PROVIDER = "document_parser"
    DISPLAY_NAME = "OCR 解析器"
    NATIVE_FORMATS = {".pdf", ".jpg", ".jpeg", ".png"}
    MODEL_VERSIONS = ["ocr"]
    DEFAULT_MODEL_VERSION = "ocr"
    UNAVAILABLE_REASON = "OCR 适配器骨架已创建，尚未接入实际实现。"

    def build_native_result(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNativeResult:
        sidecar_result = self._build_native_result_from_options(request, signals)
        if sidecar_result is not None:
            return sidecar_result
        if signals.extension in {".jpg", ".jpeg", ".png"} and find_spec("rapidocr") is not None:
            return self._build_with_rapidocr(request, signals)
        return self._build_placeholder_native_result(request, signals)

    def _build_with_rapidocr(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNativeResult:
        """调用 RapidOCR 解析图片，并保留 OCR 原生结果。"""

        from PIL import Image
        from rapidocr import RapidOCR

        started = time.perf_counter()
        source_sha256 = hashlib.sha256(request.content).hexdigest()
        parser_version = self._installed_version("rapidocr", self.DEFAULT_MODEL_VERSION)
        document_id = make_stable_document_id(
            source_sha256=source_sha256,
            parser_id=self.PARSER_ID,
            parser_version=parser_version,
        )
        result = RapidOCR()(request.content)
        raw_items = result.to_json()
        width, height = Image.open(__import__("io").BytesIO(request.content)).size

        blocks: list[dict[str, Any]] = []
        ocr_spans: list[dict[str, Any]] = []
        lines: list[str] = []
        for index, item in enumerate(raw_items):
            text = str(item.get("txt") or "").strip()
            bbox = self._rect_from_polygon(item.get("box"))
            score = item.get("score")
            if not text or bbox is None:
                continue
            lines.append(text)
            block = {
                "id": f"rapidocr-line-{index:04d}",
                "type": "ocr_line",
                "text": text,
                "page_number": 1,
                "bbox": bbox,
                "page_width": width,
                "page_height": height,
                "coordinate_system": "top_left_pixel",
                "bbox_granularity": "line",
                "provenance_status": "available",
            }
            blocks.append(block)
            ocr_spans.append(
                {
                    "level": "line",
                    "text": text,
                    "bbox": bbox,
                    "confidence": score if isinstance(score, (int, float)) else None,
                    "page_number": 1,
                }
            )

        markdown = "\n".join(lines)
        payload = {
            "blocks": blocks,
            "ocr_spans": ocr_spans,
            "raw": raw_items,
            "image": {
                "width": width,
                "height": height,
                "coordinate_system": "top_left_pixel",
            },
        }
        native_files = {
            "native/ocr_result.json": json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                default=str,
            ).encode("utf-8"),
            "native/full.md": markdown.encode("utf-8"),
        }
        native_artifacts = [
            self._native_artifact(
                path=path,
                content=content,
                artifact_type=self._artifact_type_for_path(path),
                file_type=self._file_type_for_path(path),
                required_for_quality=path.endswith(".json"),
            )
            for path, content in native_files.items()
        ]

        return ParserNativeResult(
            document_id=document_id,
            parser_id=self.PARSER_ID,
            parser_version=parser_version,
            filename=request.filename,
            file_type=request.file_type,
            source_size_bytes=len(request.content),
            source_sha256=source_sha256,
            options=request.options,
            markdown=markdown,
            payload=payload,
            native_artifacts=native_artifacts,
            native_files=native_files,
            warnings=[
                f"RapidOCR 实际调用完成，识别 {len(ocr_spans)} 个文本行，耗时 {int((time.perf_counter() - started) * 1000)} ms。"
            ],
        )

    def _rect_from_polygon(self, value: Any) -> list[float] | None:
        if not isinstance(value, list) or not value:
            return None
        points: list[tuple[float, float]] = []
        for point in value:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                return None
            try:
                points.append((float(point[0]), float(point[1])))
            except (TypeError, ValueError):
                return None
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return [min(xs), min(ys), max(xs), max(ys)]

    def normalize(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNormalizationBundle:
        """返回统一占位包；真实 OCR spans 和置信度映射会在这里接入。"""

        return self.normalize_native_result(
            self.build_native_result(request, signals),
            request,
            signals,
        )
