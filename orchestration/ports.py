"""编排层依赖的最小端口。具体 Backend/文件系统实现不应反向泄漏。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol

from ..core.contracts import ParseRequest, ParsedDocument, QualityPackage
from .models import ParseJob


class GatewayResult(Protocol):
    document: ParsedDocument
    native_files: dict[str, bytes]


class ParsingGateway(Protocol):
    def parse_for_package(self, request: ParseRequest) -> GatewayResult: ...


class JobRepository(Protocol):
    def load_job(self, parse_id: str) -> ParseJob: ...

    def save_job(self, job: ParseJob) -> ParseJob: ...

    def load_request(self, parse_id: str) -> ParseRequest: ...

    def commit_completed_job(
        self,
        *,
        job: ParseJob,
        document: ParsedDocument,
        quality_package: QualityPackage,
        native_files: dict[str, bytes],
    ) -> str: ...

    def iter_recoverable_jobs(self) -> Iterable[ParseJob]: ...


QualityRunner = Callable[[ParsedDocument], QualityPackage]
