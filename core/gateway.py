"""MarkItDown 文档解析门面；业务代码不直接依赖解析器实现。"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from .contracts import ParsedDocument, ParseRequest, ParserCapability
from .converter import DocumentConverter, LegacyOfficeConverter
from .inspector import SimpleSourceInspector
from ..parsers.markitdown import MarkItDownParser


class DocumentParserGateway:
    """知识中心唯一文档解析入口，固定使用 Microsoft MarkItDown。"""

    PARSER_ID = MarkItDownParser.PARSER_ID

    def __init__(
        self,
        parser: MarkItDownParser | None = None,
        converters: tuple[DocumentConverter, ...] | None = None,
    ) -> None:
        # 解析器和格式转换器都可注入；业务入口不依赖任何具体实现类。
        self._parser = parser or MarkItDownParser()
        self._converters = converters or (LegacyOfficeConverter(),)
        self._inspector = SimpleSourceInspector()

    @classmethod
    def from_environment(cls) -> "DocumentParserGateway":
        """保留统一构造方式，后续升级解析器时编排层无需修改。"""

        return cls()

    def list_parsers(self) -> list[ParserCapability]:
        """返回唯一解析能力，供健康检查和 OpenAPI 使用。"""

        capability = self._parser.capability
        converted_formats = {
            extension
            for converter in self._converters
            for extension in converter.source_formats
        }
        return [
            capability.model_copy(
                update={"formats": capability.formats | converted_formats}
            )
        ]

    def parse(self, request: ParseRequest) -> ParsedDocument:
        """先统一输入格式，再调用 MarkItDown，最后恢复原文件信息。"""

        if request.parser_id not in (None, self.PARSER_ID):
            raise ValueError(f"当前仅支持解析器：{self.PARSER_ID}")
        original_signals = self._inspector.inspect(request)
        if original_signals.extension in self._parser.capability.formats:
            return self._parser.parse(request, original_signals)

        converter = next(
            (
                item
                for item in self._converters
                if original_signals.extension in item.source_formats
            ),
            None,
        )
        if converter is None:
            raise ValueError(f"当前不支持文件格式：{original_signals.extension}")

        # core 转换层只改变交给解析器的内容和扩展名；最终协议仍描述原始文件。
        converted = converter.convert(request.content, original_signals.extension)
        converted_filename = str(
            Path(request.filename).with_suffix(converted.extension)
        )
        converted_request = request.model_copy(
            update={
                "filename": converted_filename,
                "file_type": mimetypes.guess_type(converted_filename)[0]
                or "application/octet-stream",
                "content": converted.content,
            }
        )
        parsed = self._parser.parse(
            converted_request,
            self._inspector.inspect(converted_request),
        )

        # 分项耗时写入 provenance；parse_duration_ms 始终表示完整解析总耗时。
        parameters = {
            **parsed.provenance.parameters,
            "input_extension": original_signals.extension,
            "converted_extension": converted.extension,
            "format_converter": converted.converter_id,
        }
        provenance = parsed.provenance.model_copy(
            update={
                "parameters": parameters,
                "format_conversion_duration_ms": converted.duration_ms,
                "parse_duration_ms": (
                    converted.duration_ms
                    + parsed.provenance.markitdown_duration_ms
                ),
            }
        )
        return parsed.model_copy(
            update={
                "filename": request.filename,
                "file_type": request.file_type,
                "provenance": provenance,
            }
        )

    def parse_file(
        self,
        path: Path,
        *,
        filename: str | None = None,
        file_type: str = "application/octet-stream",
        options: dict[str, Any] | None = None,
    ) -> ParsedDocument:
        """面向编排层的文件快捷入口；原始协议仍由 ParseRequest 承载。"""
        # 文件读取集中在门面层，底层解析器始终只处理内存字节协议。
        return self.parse(
            ParseRequest(
                filename=filename or path.name,
                file_type=file_type,
                content=path.read_bytes(),
                parser_id=self.PARSER_ID,
                options=options or {},
            )
        )

    def close(self) -> None:
        """MarkItDown 当前无持久资源；保留生命周期接口供以后升级。"""
