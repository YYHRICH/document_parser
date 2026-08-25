"""稳定端口：infra 适配器实现的接口（Ports & Adapters）。

端口只声明契约，不包含实现；实现位于 ``infra``。领域依赖端口，
端口定义放在领域层，实现方向由 ``infra`` 指向 ``domain``。
编排（路由 + fallback + 转换）属于应用层用例职责，见 ``app/orchestration.py``。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .model.contracts import (
    DocumentSignals,
    ParsedDocument,
    ParseRequest,
    ParserCapability,
    QualityPackage,
)
from .normalization import ParserNormalizationBundle


@dataclass(frozen=True)
class ConversionOutcome:
    """一次格式转换的结果（端口返回值；``infra.converter`` 实现返回此形状）。"""

    content: bytes
    extension: str
    converter_id: str
    duration_ms: int


class ParserOutcome(Protocol):
    """一次解析编排的结果形状（``app`` 层编排服务的返回值结构性满足）。"""

    document: ParsedDocument
    native_files: dict[str, bytes]


class ParserPort(Protocol):
    """解析器适配器端口：由 ``infra`` 的各个解析器适配器实现。

    ``normalize`` 是可选能力：能产出 ``ParserNormalizationBundle`` 的适配器
    优先走归一化路径（可携带原生旁路字节）；其余适配器实现 ``parse`` 即可。
    """

    PARSER_ID: str

    @property
    def capability(self) -> ParserCapability: ...

    def parse(self, request: ParseRequest, signals: DocumentSignals) -> ParsedDocument: ...

    def normalize(self, request: ParseRequest, signals: DocumentSignals) -> ParserNormalizationBundle: ...


class ConverterPort(Protocol):
    """格式转换端口：由 ``infra.converter`` 的转换器实现。"""

    @property
    def source_formats(self) -> frozenset[str]: ...

    def convert(self, content: bytes, extension: str) -> ConversionOutcome: ...


class EventPublisherPort(Protocol):
    """事件发布端口（占位，阶段 4 待接入）：用例向消息总线发布领域事件。

    后续接入 MQ 触发层时，由 ``infra`` 实现（如 RabbitMQ/Kafka/SNS 适配器）。
    """

    def publish(self, topic: str, payload: dict[str, object]) -> None: ...


class StoragePort(Protocol):
    """存储端口：由 infra 的文件系统/S3 适配器实现。"""

    def new_parse_id(self) -> str: ...

    def write_parse_package(
        self,
        *,
        parse_id: str,
        document: ParsedDocument,
        source_filename: str,
        source_content: bytes,
        native_files: dict[str, bytes],
    ) -> Path: ...

    def write_quality_package(self, parse_id: str, quality_package: QualityPackage) -> Path: ...

    def package_root(self, parse_id: str) -> Path: ...

    def load_document(self, parse_id: str) -> ParsedDocument: ...

    def load_quality_package(self, parse_id: str) -> QualityPackage: ...