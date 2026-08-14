"""metrics/collector.py – In-memory metrics engine for TARS."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TaskMetricRecord:
    """Individual record of a task solving attempt."""

    task_id: str
    slug: str
    provider: str
    model: str
    duration_ms: float
    score: int | float | None = None
    status: str = "attempted"  # "passed", "failed", "skipped", "error"
    timestamp: float = field(default_factory=time.time)


class MetricsCollector:
    """Collects and aggregates performance, timing, score, and error metrics."""

    def __init__(self) -> None:
        self.start_time: float = time.time()
        self.tasks_attempted: int = 0
        self.tasks_passed: int = 0
        self.tasks_skipped: int = 0
        self.tasks_failed: int = 0
        self.provider_calls: dict[str, int] = {}
        self.provider_errors: dict[str, int] = {}
        self.records: list[TaskMetricRecord] = []

    def record_task_attempt(
        self,
        task_id: str,
        slug: str,
        provider: str,
        model: str,
        duration_ms: float,
        score: int | float | None = None,
        status: str = "attempted",
    ) -> None:
        """Record task solving attempt metrics."""
        self.tasks_attempted += 1
        if status == "passed":
            self.tasks_passed += 1
        elif status == "skipped":
            self.tasks_skipped += 1
        elif status in ("failed", "error"):
            self.tasks_failed += 1

        rec = TaskMetricRecord(
            task_id=task_id,
            slug=slug,
            provider=provider,
            model=model,
            duration_ms=duration_ms,
            score=score,
            status=status,
        )
        self.records.append(rec)
        logger.debug("Recorded task metric: %s (%s) - %.1fms", slug, status, duration_ms)

    def record_provider_call(self, provider_name: str, duration_ms: float, is_error: bool = False) -> None:
        """Record individual LLM provider API call."""
        self.provider_calls[provider_name] = self.provider_calls.get(provider_name, 0) + 1
        if is_error:
            self.provider_errors[provider_name] = self.provider_errors.get(provider_name, 0) + 1

    @property
    def avg_solve_duration_ms(self) -> float:
        """Average duration in ms across all task attempts."""
        if not self.records:
            return 0.0
        return sum(r.duration_ms for r in self.records) / len(self.records)

    @property
    def avg_score(self) -> float:
        """Average score across evaluated tasks."""
        scored = [r.score for r in self.records if r.score is not None]
        if not scored:
            return 0.0
        return float(sum(scored)) / len(scored)

    def to_dict(self) -> dict[str, Any]:
        """Produce dictionary snapshot of current metrics."""
        uptime = time.time() - self.start_time
        return {
            "uptime_seconds": round(uptime, 2),
            "summary": {
                "tasks_attempted": self.tasks_attempted,
                "tasks_passed": self.tasks_passed,
                "tasks_skipped": self.tasks_skipped,
                "tasks_failed": self.tasks_failed,
                "avg_score": round(self.avg_score, 2),
                "avg_solve_duration_ms": round(self.avg_solve_duration_ms, 2),
            },
            "provider_calls": dict(self.provider_calls),
            "provider_errors": dict(self.provider_errors),
            "recent_records": [
                {
                    "task_id": r.task_id,
                    "slug": r.slug,
                    "provider": r.provider,
                    "model": r.model,
                    "duration_ms": round(r.duration_ms, 2),
                    "score": r.score,
                    "status": r.status,
                }
                for r in self.records[-20:]  # last 20 records
            ],
        }
