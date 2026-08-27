"""可选的文档处理编排层。

路由、归一化与质量层均可独立运行；本包只负责在生产入口把它们装配成持久化任务。
"""

from .metrics import collect_job_metrics
from .models import JobConflictError, ParseAttemptRecord, ParseFailureKind, ParseJob, ParseJobEvent, ParseJobStatus
from .queue import InProcessTaskQueue
from .service import ParseJobOrchestrator

__all__ = [
    "collect_job_metrics",
    "InProcessTaskQueue",
    "JobConflictError",
    "ParseAttemptRecord",
    "ParseFailureKind",
    "ParseJob",
    "ParseJobEvent",
    "ParseJobOrchestrator",
    "ParseJobStatus",
]
