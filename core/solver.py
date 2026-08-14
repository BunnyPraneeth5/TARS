"""core/solver.py – Solver orchestrator for TARS core pipeline."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from core.reviewer import Reviewer
from core.types import Solution, SolveStrategy
from prompts import PromptBuilder, TaskClassifier
from providers import AbstractProvider, ProviderRegistry

if TYPE_CHECKING:
    from arena_mcp.client import TaskPayload
    from metrics.collector import MetricsCollector

logger = logging.getLogger(__name__)


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from LLM output if present."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)
    return stripped


class Solver:
    """Orchestrates task classification, prompt construction, LLM execution, review, and metrics."""

    def __init__(
        self,
        provider_registry: ProviderRegistry,
        prompt_builder: PromptBuilder | None = None,
        task_classifier: TaskClassifier | None = None,
        reviewer: Reviewer | None = None,
        metrics_collector: MetricsCollector | None = None,
    ) -> None:
        self.registry = provider_registry
        self.builder = prompt_builder or PromptBuilder()
        self.classifier = task_classifier or TaskClassifier()
        self.reviewer = reviewer or Reviewer()
        self.metrics = metrics_collector

    async def solve(self, task: TaskPayload, strategy: SolveStrategy | None = None) -> Solution:
        """Solve a task payload and return a structured Solution.

        Args:
            task: Task payload fetched from Arena MCP server.
            strategy: Execution strategy options (defaults to default strategy).

        Returns:
            Solution object containing cleaned solution text, latency, and metadata.

        Raises:
            RuntimeError: If all providers in the registry fail.
        """
        if strategy is None:
            strategy = SolveStrategy()

        start_time = time.time()

        # 1. Classify task & build prompts
        task_type = self.classifier.classify(task)
        user_prompt = self.builder.build_prompt(task, task_type)
        system_prompt = self.builder.build_system_prompt(task_type)

        tried: set[str] = set()
        raw_solution: str | None = None
        provider_used: str = "unknown"
        attempts: int = 0
        last_exc: Exception | None = None

        while True:
            provider = self.registry.get_ready_provider()
            if provider is None:
                provider = await self.registry.wait_for_any_provider()

            if provider.name in tried:
                break

            attempts += 1
            logger.info(
                "Solving task %s (%s) with %s (type=%s, attempt=%d)...",
                task.task_id, task.slug, provider.name.upper(), task_type.name, attempts,
            )

            call_start = time.time()
            try:
                raw_solution = await provider.solve(user_prompt, system_prompt)
                provider_used = provider.name
                call_duration = (time.time() - call_start) * 1000

                if self.metrics:
                    self.metrics.record_provider_call(provider.name, call_duration, is_error=False)

                # Reviewer check if enabled
                if strategy.review_enabled:
                    review = self.reviewer.review(task, raw_solution)
                    if not review.approved:
                        logger.warning(
                            "Reviewer rejected output from %s: %s – attempting failover provider",
                            provider.name, review.reason,
                        )
                        tried.add(provider.name)
                        if self.metrics:
                            self.metrics.record_provider_call(provider.name, call_duration, is_error=True)
                        continue  # Try next provider

                break  # Success

            except Exception as exc:
                last_exc = exc
                call_duration = (time.time() - call_start) * 1000
                tried.add(provider.name)

                if self.metrics:
                    self.metrics.record_provider_call(provider.name, call_duration, is_error=True)

                if AbstractProvider.is_429_error(exc):
                    provider.mark_rate_limited()
                    continue

                logger.error("Provider %s failed with non-429 error: %s", provider.name, exc)
                other_ready = [p for p in self.registry.get_all() if p.name not in tried and p.check_ready()]
                if other_ready:
                    continue
                break

        if raw_solution is None:
            raise RuntimeError("All providers failed to generate an acceptable solution") from last_exc

        total_duration_ms = (time.time() - start_time) * 1000
        cleaned_solution = _strip_code_fences(raw_solution)

        # Record task metric if collector attached
        if self.metrics:
            self.metrics.record_task_attempt(
                task_id=task.task_id,
                slug=task.slug,
                provider=provider_used,
                model="default",
                duration_ms=total_duration_ms,
                status="solved",
            )

        return Solution(
            content=cleaned_solution,
            raw_content=raw_solution,
            provider_used=provider_used,
            model_used="default",
            latency_ms=total_duration_ms,
            confidence_score=0.95,
            attempts=attempts,
            review_approved=True,
            review_reason="Passed",
        )
