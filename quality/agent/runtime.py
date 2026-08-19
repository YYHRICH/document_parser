"""单文档质量修复 Agent 的外层事务循环和页面进度编排。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import uuid4

from document_parser.core.contracts import ParsedDocument, QualityPackage
from pydantic import ValidationError

from quality.agent.agno_adapter import CandidateSchemaError
from quality.agent.context import DocumentAgentContext, DocumentContextBuilder
from quality.agent.deterministic import build_deterministic_candidate
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
    # Production-safe default: keep context and candidate scope page-local.
    # Whole-document mode remains available as an explicit opt-in for tests
    # and specialized workflows.
    mode: Literal["document", "paged"] = "paged"
    max_pages: int | None = None
    progress_callback: ProgressCallback | None = None
    session_id: str | None = None
    enable_deterministic_prepass: bool = True


@dataclass(frozen=True)
class RepairExecution:
    package: QualityPackage
    attempts: tuple[CandidateValidation, ...]
    final_revision_id: str
    accepted: bool
    session_id: str
    repair_applied: bool = False


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
    session_id = runtime_config.session_id or uuid4().hex
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
            session_id,
        )
    return _run_document_repair(
        parsed_document,
        toolbox,
        agent,
        quality_config,
        runtime_config,
        session_id,
    )


def _run_document_repair(
    parsed_document: ParsedDocument,
    toolbox: QualityToolbox,
    agent: RepairAgent,
    quality_config: QualityConfig,
    runtime_config: RepairAgentConfig,
    session_id: str,
) -> RepairExecution:
    revision = toolbox.current_revision
    context_builder = DocumentContextBuilder()
    attempts: list[CandidateValidation] = []
    feedback: CandidateValidation | None = None
    accepted = False
    accepted_no_progress = False
    no_progress_manual_review = False
    repairable_issue_count = 0
    _emit(runtime_config, "document", "started", None, 0, 0, "开始整篇文档修复")

    for round_index in range(runtime_config.max_rounds):
        context = context_builder.build(
            revision,
            feedback,
            max_context_chars=runtime_config.max_context_chars,
            quality_diagnostics=toolbox.get_quality_diagnostics(),
        )
        try:
            candidate = agent.run(context, feedback=feedback)
        except CandidateSchemaError as exc:
            validation = _candidate_schema_error_validation(revision, exc)
            attempts.append(validation)
            toolbox.rollback_revision(validation.message)
            feedback = validation
            if round_index + 1 < runtime_config.max_rounds:
                continue
            break
        except Exception as exc:
            validation = _agent_error_validation(revision, exc)
            attempts.append(validation)
            toolbox.rollback_revision(validation.message)
            break

        try:
            candidate = RepairedDocumentCandidate.model_validate(candidate)
        except ValidationError as exc:
            validation = _candidate_schema_error_validation(revision, exc)
            attempts.append(validation)
            toolbox.rollback_revision(validation.message)
            feedback = validation
            if round_index + 1 < runtime_config.max_rounds:
                continue
            break
        try:
            validation = CandidateValidation.model_validate(
                toolbox.validate_candidate(candidate)
            )
        except Exception as exc:
            validation = _validator_error_validation(revision, exc)
            attempts.append(validation)
            toolbox.rollback_revision(validation.message)
            break
        attempts.append(validation)
        if validation.accepted:
            if validation.no_progress:
                repairable_issue_count = toolbox.repairable_issue_count()
                if repairable_issue_count:
                    if round_index + 1 < runtime_config.max_rounds:
                        feedback = _no_progress_feedback(
                            validation, repairable_issue_count
                        )
                        continue
                    no_progress_manual_review = True
                    break
                accepted = True
                accepted_no_progress = True
                break
            accepted = True
            toolbox.commit_revision(candidate)
            revision = toolbox.current_revision
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
        (
            "整篇文档检查完成，无需修改"
            if accepted_no_progress
            else "整篇文档修复完成" if accepted else "整篇文档转人工复核"
        ),
    )
    return _finish_execution(
        parsed_document,
        toolbox,
        quality_config,
        attempts,
        accepted,
        session_id,
        {
            "attempt_count": len(attempts),
            "mode": "document",
            "stop_reason": (
                "no_progress_manual_review"
                if no_progress_manual_review
                else
                "no_progress"
                if accepted_no_progress
                else "committed" if accepted else "manual_review"
            ),
            "repairable_issue_count": repairable_issue_count,
        },
    )


def _run_paged_repair(
    parsed_document: ParsedDocument,
    toolbox: QualityToolbox,
    agent: RepairAgent,
    quality_config: QualityConfig,
    runtime_config: RepairAgentConfig,
    session_id: str,
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
            session_id,
        )

    context_builder = DocumentContextBuilder()
    attempts: list[CandidateValidation] = []
    completed = 0
    successful_pages = 0
    deterministic_repairs = 0
    deterministic_attempts = 0
    llm_calls = 0

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
        if runtime_config.enable_deterministic_prepass:
            revision = toolbox.current_revision
            rule_candidate = build_deterministic_candidate(revision, page_number)
            if rule_candidate is not None:
                deterministic_attempts += 1
                try:
                    rule_validation = CandidateValidation.model_validate(
                        toolbox.validate_candidate_for_page(rule_candidate, page_number)
                    )
                except Exception as exc:
                    rule_validation = _validator_error_validation(revision, exc)
                    toolbox.rollback_revision(rule_validation.message)
                attempts.append(rule_validation)
                if rule_validation.accepted and not rule_validation.no_progress:
                    toolbox.commit_revision(rule_candidate)
                    deterministic_repairs += 1
                    page_accepted = (
                        toolbox.repairable_issue_count(page_number) == 0
                    )

        # Parser-limited/manual-review issues on this page do not benefit from
        # an LLM. If no deterministic repair remains applicable, finish the
        # page as a safe no-op instead of spending a model call.
        if not page_accepted and toolbox.repairable_issue_count(page_number) == 0:
            page_accepted = True

        if not page_accepted:
            for round_index in range(runtime_config.max_rounds):
                llm_calls += 1
                revision = toolbox.current_revision
                context = context_builder.build_page(
                    revision,
                    page_number,
                    feedback,
                    max_context_chars=runtime_config.max_context_chars,
                    quality_diagnostics=toolbox.get_quality_diagnostics(),
                )
                try:
                    candidate = agent.run(context, feedback=feedback)
                except CandidateSchemaError as exc:
                    validation = _candidate_schema_error_validation(revision, exc)
                    attempts.append(validation)
                    toolbox.rollback_revision(validation.message)
                    feedback = validation
                    if round_index + 1 < runtime_config.max_rounds:
                        continue
                    break
                except Exception as exc:
                    validation = _agent_error_validation(revision, exc)
                    attempts.append(validation)
                    toolbox.rollback_revision(validation.message)
                    break

                try:
                    candidate = RepairedDocumentCandidate.model_validate(candidate)
                except ValidationError as exc:
                    validation = _candidate_schema_error_validation(revision, exc)
                    attempts.append(validation)
                    toolbox.rollback_revision(validation.message)
                    feedback = validation
                    if round_index + 1 < runtime_config.max_rounds:
                        continue
                    break
                try:
                    validation = CandidateValidation.model_validate(
                        toolbox.validate_candidate_for_page(candidate, page_number)
                    )
                except Exception as exc:
                    validation = _validator_error_validation(revision, exc)
                    attempts.append(validation)
                    toolbox.rollback_revision(validation.message)
                    break
                attempts.append(validation)
                if validation.accepted:
                    if validation.no_progress:
                        repairable_issue_count = toolbox.repairable_issue_count(page_number)
                        if repairable_issue_count:
                            if round_index + 1 < runtime_config.max_rounds:
                                feedback = _no_progress_feedback(
                                    validation, repairable_issue_count
                                )
                                continue
                            break
                        page_accepted = True
                        break
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
        session_id,
        {
            "attempt_count": len(attempts),
            "mode": "paged",
            "total_pages": total_pages,
            "completed_pages": completed,
            "successful_pages": successful_pages,
            "deterministic_attempts": deterministic_attempts,
            "deterministic_repairs": deterministic_repairs,
            "llm_call_count": llm_calls,
        },
    )


def _finish_execution(
    parsed_document: ParsedDocument,
    toolbox: QualityToolbox,
    quality_config: QualityConfig,
    attempts: list[CandidateValidation],
    accepted: bool,
    session_id: str,
    agent_metrics: Mapping[str, Any],
) -> RepairExecution:
    revision = toolbox.current_revision
    metrics: Mapping[str, Any] = {
        "agent": {
            **dict(agent_metrics),
            "session_id": session_id,
            "accepted": accepted,
            "repair_applied": any(
                attempt.accepted and not attempt.no_progress
                for attempt in attempts
            ),
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
        session_id=session_id,
        repair_applied=bool(
            any(attempt.accepted and not attempt.no_progress for attempt in attempts)
        ),
    )


def _no_progress_feedback(
    validation: CandidateValidation,
    repairable_issue_count: int,
) -> CandidateValidation:
    """把合法但无变化的候选转成下一轮的明确重试反馈。"""

    return validation.model_copy(
        update={
            "accepted": False,
            "code": "no_progress_with_repairable_issues",
            "message": (
                "候选 Schema 合法，但没有产生任何结构变化；"
                f"当前仍有 {repairable_issue_count} 个可尝试修复的问题。"
                "请只针对有证据的问题提交最小 operations，"
                "不要再次返回空 operations。"
            ),
            "errors": ["no_progress_with_repairable_issues"],
            "no_progress": True,
        }
    )


def _agent_error_validation(revision, exc: Exception) -> CandidateValidation:
    code, message = _classify_agent_error(exc)
    return _failure_validation(revision, exc, code=code, message=message)


def _candidate_schema_error_validation(revision, exc: Exception) -> CandidateValidation:
    return _failure_validation(
        revision,
        exc,
        code="candidate_schema_error",
        message="Agent 输出不符合候选 Schema，保留原 revision 并转人工复核。",
        no_progress=False,
    )


def _validator_error_validation(revision, exc: Exception) -> CandidateValidation:
    return _failure_validation(
        revision,
        exc,
        code="validator_error",
        message="确定性 Validator 执行失败，保留原 revision 并转人工复核。",
    )


def _failure_validation(
    revision,
    exc: Exception,
    *,
    code: str,
    message: str,
    no_progress: bool = True,
) -> CandidateValidation:
    exception_type = f"{type(exc).__module__}.{type(exc).__name__}"
    errors = [exception_type]
    if isinstance(exc, CandidateSchemaError):
        errors.append(f"reason={exc.reason}")
    return CandidateValidation(
        accepted=False,
        code=code,
        message=message,
        errors=errors,
        no_progress=no_progress,
        base_revision=revision.revision_id,
        source_content_fingerprint="",
        candidate_content_fingerprint="",
    )


def _classify_agent_error(exc: Exception) -> tuple[str, str]:
    """将模型侧异常归类并脱敏；不把 Provider 响应正文带入公共结果。"""

    exception_name = type(exc).__name__.lower()
    module_root = type(exc).__module__.split(".", 1)[0]
    if isinstance(exc, TimeoutError) or "timeout" in exception_name:
        return "agent_timeout", "Agent 调用超时，保留原 revision 并转人工复核。"
    if isinstance(exc, ValidationError):
        return (
            "candidate_schema_error",
            "Agent 输出不符合候选 Schema，保留原 revision 并转人工复核。",
        )
    if module_root in {"agno", "openai", "httpx", "httpcore"}:
        return (
            "provider_error",
            "模型 Provider 调用失败，保留原 revision 并转人工复核。",
        )
    return "agent_error", "Agent 调用失败，保留原 revision 并转人工复核。"


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

