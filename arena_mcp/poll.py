"""arena_mcp/poll.py – Polling loop: get_task → solve → submit_task, repeat.

Runs until interrupted (Ctrl-C) or a FINISH signal file is detected.
Uses ProviderRegistry for provider selection and cooldown management.
Uses TaskClassifier and PromptBuilder for task-type-aware prompts.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

import config
from arena_mcp.client import TaskPayload, get_task, register_agent, skip_task, submit_task
from prompts import PromptBuilder, TaskClassifier
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


def _safe_slug(slug: str) -> str:
    """Convert a task slug into a filesystem-safe directory name."""
    safe = _INVALID_PATH_CHARS.sub("_", slug)
    return safe.strip("_ ")


def _create_default_registry() -> ProviderRegistry:
    """Fallback registry setup if none is passed to run_loop or solve_task."""
    from agent import runner, session_service
    from providers import GeminiProvider, NVIDIAProvider

    return ProviderRegistry([
        GeminiProvider(runner=runner, session_service=session_service),
        NVIDIAProvider(),
    ])


# ── solve_task ──────────────────────────────────────────────────────────────

async def solve_task(task: TaskPayload, registry: ProviderRegistry | None = None) -> Path:
    """Solve a single Arena task and write the result to a submission file.

    Picks the first available provider from the registry. If a provider returns
    a 429, it is put into cooldown and the next provider is tried.

    Args:
        task: The task payload from the Arena MCP server.
        registry: ProviderRegistry instance managing available LLM providers.

    Returns:
        Path to the generated submission file.

    Raises:
        RuntimeError: If all providers fail.
    """
    if registry is None:
        registry = _create_default_registry()

    # Log task details
    logger.info(
        "Task payload: task_id=%s slug=%s prompt_len=%d metadata=%r",
        task.task_id, task.slug, len(task.prompt), task.metadata,
    )
    logger.debug("Full task prompt:\n%s", task.prompt)

    # Classify task & build prompts
    classifier = TaskClassifier()
    builder = PromptBuilder()

    task_type = classifier.classify(task)
    user_prompt = builder.build_prompt(task, task_type)
    system_prompt = builder.build_system_prompt(task_type)

    last_exc: Exception | None = None
    tried: set[str] = set()
    raw_solution: str | None = None

    while True:
        provider = registry.get_ready_provider()
        if provider is None:
            provider = await registry.wait_for_any_provider()

        if provider.name in tried:
            break

        logger.info(
            "Sending task %s (%s) to %s (type=%s)...",
            task.task_id, task.slug, provider.name.upper(), task_type.name,
        )

        try:
            raw_solution = await provider.solve(user_prompt, system_prompt)
            break  # success
        except Exception as exc:
            last_exc = exc
            tried.add(provider.name)
            if AbstractProvider.is_429_error(exc):
                provider.mark_rate_limited()
                continue  # try next provider

            logger.error("Provider %s failed with non-429 error: %s", provider.name, exc)
            other_ready = [p for p in registry.get_all() if p.name not in tried and p.check_ready()]
            if other_ready:
                continue
            break

    if raw_solution is None:
        raise RuntimeError("All providers failed") from last_exc

    # Strip code fences
    solution = _strip_code_fences(raw_solution)

    # Log preview
    preview = solution[:200].replace("\n", "\\n")
    logger.info(
        "Solution for %s (%d chars): %s%s",
        task.slug, len(solution), preview, "..." if len(solution) > 200 else "",
    )

    # Write submission file
    slug_safe = _safe_slug(task.slug)
    task_dir = CONTENT_DIR / slug_safe
    task_dir.mkdir(parents=True, exist_ok=True)
    submission_path = task_dir / "submission.md"
    submission_path.write_text(solution, encoding="utf-8")
    logger.info("Wrote submission to %s", submission_path)

    return submission_path


# ── Main loop ──────────────────────────────────────────────────────────────

async def run_loop(registry: ProviderRegistry | None = None) -> None:
    """Poll for tasks, solve them, submit results. Repeat until stopped.

    Args:
        registry: Optional ProviderRegistry instance. If None, default registry is constructed.
    """
    if registry is None:
        registry = _create_default_registry()

    consecutive_errors = 0
    logger.info(
        "Agent Arena poll loop starting (agent_id=%s, registered_providers=%s)",
        config.AGENT_ID, [p.name for p in registry.get_all()],
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

                # 2. Solve task using provider registry
                submission_path = await solve_task(task, registry=registry)

                # 3. Submit solution
                response = await submit_task(config.AGENT_ID, task.task_id, submission_path)

                # 4. Score evaluation
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
        logger.info("Poll loop stopped.")
