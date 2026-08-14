"""arena_mcp/poll.py – Polling loop: get_task → solve → submit_task, repeat.

Runs until interrupted (Ctrl-C) or a FINISH signal file is detected.
Uses Solver orchestrator, ProviderRegistry, Reviewer, and MetricsCollector.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

import config
from arena_mcp.client import TaskPayload, get_task, register_agent, skip_task, submit_task
from core import Solver
from metrics import MetricsCollector, export_json
from providers import AbstractProvider, ProviderRegistry

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────

BASE_POLL_INTERVAL: float = 5.0     # seconds between polls when a task was found
IDLE_POLL_INTERVAL: float = 30.0    # seconds between polls when queue is empty
MAX_BACKOFF: float = 120.0          # ceiling for exponential backoff on errors
PASS_SCORE_THRESHOLD: int = 70      # minimum score to consider a task passed

FINISH_SIGNAL_FILE: Path = Path("FINISH")  # touch this file to stop the loop

CONTENT_DIR: Path = Path("content/tasks")

# Regex to strip invalid filename chars on Windows (: * ? " < > |)
_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*]')


# ── Helpers ─────────────────────────────────────────────────────────────────

def _safe_slug(slug: str) -> str:
    """Convert a task slug into a filesystem-safe directory name."""
    safe = _INVALID_PATH_CHARS.sub("_", slug)
    return safe.strip("_ ")


def _create_default_solver(metrics: MetricsCollector | None = None) -> Solver:
    """Fallback solver setup if none is passed to run_loop or solve_task."""
    from agent import runner, session_service
    from providers import GeminiProvider, NVIDIAProvider

    registry = ProviderRegistry([
        GeminiProvider(runner=runner, session_service=session_service),
        NVIDIAProvider(),
    ])
    return Solver(provider_registry=registry, metrics_collector=metrics)


# ── solve_task ──────────────────────────────────────────────────────────────

async def solve_task(
    task: TaskPayload,
    registry: ProviderRegistry | None = None,
    solver: Solver | None = None,
) -> Path:
    """Solve a single Arena task using Solver orchestrator and write to submission.md.

    Args:
        task: The task payload from the Arena MCP server.
        registry: Optional ProviderRegistry instance.
        solver: Optional Solver instance.

    Returns:
        Path to the generated submission file.
    """
    if solver is None:
        if registry is not None:
            solver = Solver(provider_registry=registry)
        else:
            solver = _create_default_solver()

    solution = await solver.solve(task)

    # Write submission file
    slug_safe = _safe_slug(task.slug)
    task_dir = CONTENT_DIR / slug_safe
    task_dir.mkdir(parents=True, exist_ok=True)
    submission_path = task_dir / "submission.md"
    submission_path.write_text(solution.content, encoding="utf-8")
    logger.info("Wrote submission to %s", submission_path)

    return submission_path


# ── Main loop ──────────────────────────────────────────────────────────────

async def run_loop(
    registry: ProviderRegistry | None = None,
    solver: Solver | None = None,
    metrics: MetricsCollector | None = None,
) -> None:
    """Poll for tasks, solve them, submit results. Repeat until stopped.

    Args:
        registry: Optional ProviderRegistry instance.
        solver: Optional Solver instance.
        metrics: Optional MetricsCollector instance.
    """
    if metrics is None:
        metrics = MetricsCollector()

    if solver is None:
        if registry is not None:
            solver = Solver(provider_registry=registry, metrics_collector=metrics)
        else:
            solver = _create_default_solver(metrics=metrics)

    consecutive_errors = 0
    logger.info(
        "Agent Arena poll loop starting (agent_id=%s, solver_providers=%s)",
        config.AGENT_ID, [p.name for p in solver.registry.get_all()],
    )

    # ── Register agent once at startup ──────────────────────────────────
    try:
        reg_response = await register_agent(config.AGENT_ID)
        logger.info("Agent registered successfully: %s", reg_response)
    except Exception:
        logger.exception("Failed to register agent – continuing anyway")

    try:
        while True:
            if FINISH_SIGNAL_FILE.exists():
                logger.info("FINISH signal file detected – shutting down cleanly.")
                break

            try:
                # 1. Fetch task
                task = await get_task(config.AGENT_ID)

                if task is None:
                    logger.debug("No tasks available – idling for %.0fs", IDLE_POLL_INTERVAL)
                    await asyncio.sleep(IDLE_POLL_INTERVAL)
                    consecutive_errors = 0
                    continue

                logger.info("Got task %s (slug=%s)", task.task_id, task.slug)

                # 2. Solve task using Solver
                submission_path = await solve_task(task, solver=solver)

                # 3. Submit solution
                response = await submit_task(config.AGENT_ID, task.task_id, submission_path)

                # 4. Score evaluation & metrics export
                score = response.get("score", 0) if isinstance(response, dict) else 0
                logger.info(
                    "Task %s score: %s (threshold=%d) – response: %s",
                    task.task_id, score, PASS_SCORE_THRESHOLD, response,
                )

                if score < PASS_SCORE_THRESHOLD:
                    logger.warning(
                        "Score %s < %d for task %s – skipping to unlock next task",
                        score, PASS_SCORE_THRESHOLD, task.task_id,
                    )
                    try:
                        skip_response = await skip_task(config.AGENT_ID, task.task_id)
                        logger.info("Skip response for task %s: %s", task.task_id, skip_response)
                    except Exception:
                        logger.exception("Failed to skip task %s", task.task_id)
                else:
                    logger.info("Task %s PASSED with score %s ✓", task.task_id, score)

                # Export metrics snapshot
                export_json(metrics)

                consecutive_errors = 0
                await asyncio.sleep(BASE_POLL_INTERVAL)

            except Exception as exc:
                consecutive_errors += 1
                backoff = min(BASE_POLL_INTERVAL * (2 ** consecutive_errors), MAX_BACKOFF)

                logger.exception("Error in poll loop (attempt %d) – backing off %.0fs", consecutive_errors, backoff)
                await asyncio.sleep(backoff)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt – shutting down poll loop.")
    finally:
        export_json(metrics)
        logger.info("Poll loop stopped.")
