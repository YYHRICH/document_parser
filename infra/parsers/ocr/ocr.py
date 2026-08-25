"""OCR 解析器骨架。"""

from __future__ import annotations

import hashlib
import io
import json
import time
from importlib.util import find_spec
from typing import Any

from ....domain.model.contracts import (
    DocumentSignals,
    ParseRequest,
    ParserCapability,
    ParserNativeResult,
)
from ....domain.normalization import ParserNormalizationBundle, make_stable_document_id
from ....domain.routing.ids import OCR_ID
from ..base import BaseParserAdapter


class OcrParser(BaseParserAdapter):
    """OCR 的预留入口。"""

    PARSER_ID = OCR_ID
    PROVIDER = "document_parser"
    DISPLAY_NAME = "OCR 解析器"
    NATIVE_FORMATS = {".pdf", ".jpg", ".jpeg", ".png"}
    MODEL_VERSIONS = ["ocr"]
    DEFAULT_MODEL_VERSION = "ocr"
    UNAVAILABLE_REASON = "OCR adapter requires RapidOCR for direct image parsing."

    @property
    def capability(self) -> ParserCapability:
        available = find_spec("rapidocr") is not None
        return ParserCapability(
            parser_id=self.PARSER_ID,
            provider=self.PROVIDER,
            display_name=self.DISPLAY_NAME,
            formats=self.NATIVE_FORMATS,
            model_versions=self.MODEL_VERSIONS,
            default_model_version=self.DEFAULT_MODEL_VERSION,
            requires_network=False,
            requires_gpu=False,
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
        if signals.extension in {".jpg", ".jpeg", ".png", ".pdf"} and find_spec("rapidocr") is not None:
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
        engine = RapidOCR()
        page_images = self._ocr_page_images(request, signals)

        blocks: list[dict[str, Any]] = []
        ocr_spans: list[dict[str, Any]] = []
        raw_pages: list[dict[str, Any]] = []
        pages: dict[str, dict[str, Any]] = {}
        lines: list[str] = []
        for page_number, image_bytes, width, height in page_images:
            result = engine(image_bytes)
            raw_items = result.to_json()
            if not isinstance(raw_items, list):
                raw_items = []
            pages[str(page_number)] = {
                "page_no": page_number,
                "size": {"width": width, "height": height},
            }
            raw_pages.append({"page_number": page_number, "items": raw_items})
            if lines:
                lines.append("")
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("txt") or item.get("text") or "").strip()
                bbox = self._rect_from_polygon(item.get("box") or item.get("bbox"))
                score = item.get("score") or item.get("confidence")
                if not text or bbox is None:
                    continue
                order_index = len(blocks)
                lines.append(text)
                block = {
                    "id": f"rapidocr-p{page_number:04d}-line-{order_index:04d}",
                    "type": "ocr_line",
                    "text": text,
                    "page_number": page_number,
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
                        "page_number": page_number,
                        "page_width": width,
                        "page_height": height,
                        "coordinate_system": "top_left_pixel",
                    }
                )

        markdown = "\n".join(lines)
        payload = {
            "blocks": blocks,
            "ocr_spans": ocr_spans,
            "raw_pages": raw_pages,
            "pages": pages,
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

    def _ocr_page_images(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> list[tuple[int, bytes, int, int]]:
        from PIL import Image

        if signals.extension == ".pdf":
            if find_spec("pypdfium2") is None:
                raise RuntimeError("PDF OCR requires pypdfium2 to render pages.")
            import pypdfium2 as pdfium

            scale = float(request.options.get("ocr_pdf_scale", 2.0))
            max_pages = int(request.options.get("ocr_max_pages", 20))
            document = pdfium.PdfDocument(request.content)
            page_images: list[tuple[int, bytes, int, int]] = []
            try:
                for page_index in range(min(len(document), max_pages)):
                    image = document[page_index].render(scale=scale).to_pil()
                    page_images.append(
                        (
                            page_index + 1,
                            self._image_to_png_bytes(image),
                            int(image.width),
                            int(image.height),
                        )
                    )
            finally:
                document.close()
            return page_images

        image = Image.open(io.BytesIO(request.content))
        return [(1, request.content, int(image.width), int(image.height))]

    def _image_to_png_bytes(self, image: Any) -> bytes:
        with io.BytesIO() as buffer:
            image.save(buffer, format="PNG")
            return buffer.getvalue()

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
