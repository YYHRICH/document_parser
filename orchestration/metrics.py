"""Deterministic job metrics aggregation with no backend or parser dependency."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

from .models import ParseJob


def collect_job_metrics(jobs: Iterable[ParseJob]) -> dict[str, object]:
    """Aggregate persisted jobs for diagnostics and route-policy evaluation."""
    job_list = list(jobs)
    status_counts = Counter(job.status.value for job in job_list)
    failure_counts = Counter(
        job.failure_kind.value for job in job_list if job.failure_kind is not None
    )
    quality_state_counts = Counter(
        job.quality_state for job in job_list if job.quality_state is not None
    )
    parser_attempts: dict[str, dict[str, object]] = defaultdict(
        lambda: {"attempt_count": 0, "success_count": 0, "failure_count": 0, "duration_ms_total": 0}
    )
    for job in job_list:
        for attempt in job.attempts:
            metric = parser_attempts[attempt.parser_id]
            metric["attempt_count"] = int(metric["attempt_count"]) + 1
            metric["duration_ms_total"] = int(metric["duration_ms_total"]) + attempt.duration_ms
            if attempt.status == "succeeded":
                metric["success_count"] = int(metric["success_count"]) + 1
            else:
                metric["failure_count"] = int(metric["failure_count"]) + 1
    parser_summary: dict[str, dict[str, object]] = {}
    for parser_id, metric in sorted(parser_attempts.items()):
        attempts = int(metric["attempt_count"])
        parser_summary[parser_id] = {
            **metric,
            "average_duration_ms": round(int(metric["duration_ms_total"]) / attempts, 2) if attempts else 0,
            "success_rate": round(int(metric["success_count"]) / attempts, 4) if attempts else None,
        }
    terminal_count = sum(count for name, count in status_counts.items() if name in {"succeeded", "failed", "cancelled", "needs_review"})
    return {
        "schema_name": "ParseJobMetrics",
        "schema_version": "1.0",
        "job_count": len(job_list),
        "terminal_job_count": terminal_count,
        "status_counts": dict(sorted(status_counts.items())),
        "failure_counts": dict(sorted(failure_counts.items())),
        "quality_state_counts": dict(sorted(quality_state_counts.items())),
        "parser_attempts": parser_summary,
    }
