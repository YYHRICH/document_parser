"""单文档质量修复 Agent 的外层事务循环和页面进度编排。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from document_parser.core.contracts import ParsedDocument, QualityPackage

from quality.agent.context import DocumentAgentContext, DocumentContextBuilder
from quality.agent.index import DocumentIndex
from quality.agent.models import CandidateValidation, RepairedDocumentCandidate
from quality.agent.revision import document_digest
from quality.agent.tools import QualityToolbox
from quality.config import QualityConfig
from quality.pipeline import run_pipeline


class QualityAgentNotConfigured(RuntimeError):
    """正式 Agent 入口未提供 Agno/Fake Agent。"""


class RepairAgent(Protocol):
    def run(
        self,
        context: DocumentAgentContext,
        *,
        feedback: CandidateValidation | None = None,
    ) -> RepairedDocumentCandidate:
        ...


RepairAgentFactory = Callable[[QualityToolbox], RepairAgent]


@dataclass(frozen=True)
class RepairProgressEvent:
    """宿主层可消费的页面进度事件；不绑定 CLI 或 Web UI。"""

    stage: str
    status: Literal["started", "completed", "failed", "manual_review"]
    page_number: int | None
    completed_pages: int
    total_pages: int
    message: str = ""


ProgressCallback = Callable[[RepairProgressEvent], None]


@dataclass(frozen=True)
class RepairAgentConfig:
    max_rounds: int = 3
    max_context_chars: int = 12000
    mode: Literal["document", "paged"] = "document"
    max_pages: int | None = None
    progress_callback: ProgressCallback | None = None


@dataclass(frozen=True)
class RepairExecution:
    package: QualityPackage
    attempts: tuple[CandidateValidation, ...]
    final_revision_id: str
    accepted: bool


def run_repair(
    parsed_document: ParsedDocument,
    *,
    agent: RepairAgent | None = None,
    agent_factory: RepairAgentFactory | None = None,
    config: QualityConfig | None = None,
    agent_config: RepairAgentConfig | None = None,
) -> RepairExecution:
    """执行单文档 Agent；paged 模式按页提交局部 Patch。"""

    quality_config = config or QualityConfig()
    runtime_config = agent_config or RepairAgentConfig()
    toolbox = QualityToolbox.open(parsed_document, quality_config=quality_config)
    if agent is not None and agent_factory is not None:
        raise ValueError("agent 和 agent_factory 只能提供一个。")
    if agent is None:
        if agent_factory is None:
            raise QualityAgentNotConfigured(
                "run_quality_repair 必须提供 Agent 或 agent_factory；"
                "确定性维护路径请显式调用 run_quality。"
            )
        agent = agent_factory(toolbox)
        if agent is None:
            raise QualityAgentNotConfigured("agent_factory 返回了 None。")

    if runtime_config.mode == "paged":
        return _run_paged_repair(
            parsed_document,
            toolbox,
            agent,
            quality_config,
            runtime_config,
        )
    return _run_document_repair(
        parsed_document,
        toolbox,
        agent,
        quality_config,
        runtime_config,
    )


def _run_document_repair(
    parsed_document: ParsedDocument,
    toolbox: QualityToolbox,
    agent: RepairAgent,
    quality_config: QualityConfig,
    runtime_config: RepairAgentConfig,
) -> RepairExecution:
    revision = toolbox.current_revision
    context_builder = DocumentContextBuilder()
    attempts: list[CandidateValidation] = []
    feedback: CandidateValidation | None = None
    accepted = False
    _emit(runtime_config, "document", "started", None, 0, 0, "开始整篇文档修复")

    for _ in range(runtime_config.max_rounds):
        context = context_builder.build(
            revision,
            feedback,
            max_context_chars=runtime_config.max_context_chars,
        )
        try:
            candidate = agent.run(context, feedback=feedback)
        except Exception as exc:
            validation = _agent_error_validation(revision, exc)
            attempts.append(validation)
            toolbox.rollback_revision(validation.message)
            break

        validation = CandidateValidation.model_validate(
            toolbox.validate_candidate(candidate)
        )
        attempts.append(validation)
        if validation.accepted:
            toolbox.commit_revision(candidate)
            revision = toolbox.current_revision
            accepted = True
            break
        if validation.no_progress:
            break
        feedback = validation
        revision = toolbox.current_revision

    if not accepted and attempts:
        toolbox.rollback_revision(attempts[-1].message)
    _emit(
        runtime_config,
        "document",
        "completed" if accepted else "manual_review",
        None,
        0,
        0,
        "整篇文档修复完成" if accepted else "整篇文档转人工复核",
    )
    return _finish_execution(
        parsed_document,
        toolbox,
        quality_config,
        attempts,
        accepted,
        {"attempt_count": len(attempts), "mode": "document"},
    )


def _run_paged_repair(
    parsed_document: ParsedDocument,
    toolbox: QualityToolbox,
    agent: RepairAgent,
    quality_config: QualityConfig,
    runtime_config: RepairAgentConfig,
) -> RepairExecution:
    index = DocumentIndex.from_document(toolbox.current_revision.document)
    pages = [entry.page_number for entry in index.pages]
    if runtime_config.max_pages is not None:
        pages = pages[: max(runtime_config.max_pages, 0)]
    total_pages = len(pages)
    _emit(runtime_config, "overview", "started", None, 0, total_pages, "建立文档页索引")
    _emit(runtime_config, "overview", "completed", None, 0, total_pages, "文档索引完成")

    if not pages:
        return _run_document_repair(
            parsed_document,
            toolbox,
            agent,
            quality_config,
            runtime_config,
        )

    context_builder = DocumentContextBuilder()
    attempts: list[CandidateValidation] = []
    completed = 0
    successful_pages = 0

    for page_number in pages:
        feedback: CandidateValidation | None = None
        page_accepted = False
        _emit(
            runtime_config,
            "page",
            "started",
            page_number,
            completed,
            total_pages,
            f"开始处理第 {page_number} 页",
        )
        for _ in range(runtime_config.max_rounds):
            revision = toolbox.current_revision
            context = context_builder.build_page(
                revision,
                page_number,
                feedback,
                max_context_chars=runtime_config.max_context_chars,
            )
            try:
                candidate = agent.run(context, feedback=feedback)
            except Exception as exc:
                validation = _agent_error_validation(revision, exc)
                attempts.append(validation)
                toolbox.rollback_revision(validation.message)
                break

            validation = CandidateValidation.model_validate(
                toolbox.validate_candidate_for_page(candidate, page_number)
            )
            attempts.append(validation)
            if validation.accepted:
                if not validation.no_progress:
                    toolbox.commit_revision(candidate)
                page_accepted = True
                break
            if validation.no_progress:
                break
            feedback = validation

        completed += 1
        if page_accepted:
            successful_pages += 1
            _emit(
                runtime_config,
                "page",
                "completed",
                page_number,
                completed,
                total_pages,
                f"第 {page_number} 页完成",
            )
        else:
            toolbox.rollback_revision(f"第 {page_number} 页未通过验证。")
            _emit(
                runtime_config,
                "page",
                "manual_review",
                page_number,
                completed,
                total_pages,
                f"第 {page_number} 页转人工复核",
            )

    accepted = successful_pages == total_pages
    return _finish_execution(
        parsed_document,
        toolbox,
        quality_config,
        attempts,
        accepted,
        {
            "attempt_count": len(attempts),
            "mode": "paged",
            "total_pages": total_pages,
            "completed_pages": completed,
            "successful_pages": successful_pages,
        },
    )


def _finish_execution(
    parsed_document: ParsedDocument,
    toolbox: QualityToolbox,
    quality_config: QualityConfig,
    attempts: list[CandidateValidation],
    accepted: bool,
    agent_metrics: Mapping[str, Any],
) -> RepairExecution:
    revision = toolbox.current_revision
    metrics: Mapping[str, Any] = {
        "agent": {
            **dict(agent_metrics),
            "accepted": accepted,
            "final_revision_id": revision.revision_id,
            "last_code": attempts[-1].code if attempts else "not_run",
        }
    }
    final_package = run_pipeline(
        revision.document if accepted or revision.revision_id != document_digest(parsed_document)
        else parsed_document,
        config=quality_config,
        additional_metrics=metrics,
    )
    return RepairExecution(
        package=final_package,
        attempts=tuple(attempts),
        final_revision_id=revision.revision_id,
        accepted=accepted,
    )


def _agent_error_validation(revision, exc: Exception) -> CandidateValidation:
    return CandidateValidation(
        accepted=False,
        code="agent_error",
        message="Agent 调用失败，保留原 revision 并转人工复核。",
        errors=[f"{type(exc).__name__}: {exc}"],
        no_progress=True,
        base_revision=revision.revision_id,
        source_content_fingerprint="",
        candidate_content_fingerprint="",
    )


def _emit(
    runtime_config: RepairAgentConfig,
    stage: str,
    status: Literal["started", "completed", "failed", "manual_review"],
    page_number: int | None,
    completed_pages: int,
    total_pages: int,
    message: str,
) -> None:
    callback = runtime_config.progress_callback
    if callback is None:
        return
    try:
        callback(
            RepairProgressEvent(
                stage=stage,
                status=status,
                page_number=page_number,
                completed_pages=completed_pages,
                total_pages=total_pages,
                message=message,
            )
        )
    except Exception:
        # UI/CLI 进度回调故障不能破坏质量事务。
        return

