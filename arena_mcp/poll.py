"""
arena_mcp/poll.py – Polling loop: get_task → solve → submit_task, repeat.

Runs until interrupted (Ctrl-C) or a FINISH signal file is detected.
Supports Gemini (via ADK) and NVIDIA (via OpenAI-compatible API) as LLM providers.
Uses a provider pool with 429 cooldown to gracefully handle rate limits.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import config
from arena_mcp.client import TaskPayload, get_task, register_agent, skip_task, submit_task

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


# ── Provider pool ──────────────────────────────────────────────────────────

@dataclass
class Provider:
    """Represents an LLM provider with rate-limit cooldown tracking."""

    name: str
    available: bool = True
    last_429: float = 0.0
    cooldown: float = 300.0  # seconds to wait after a 429

    def mark_429(self) -> None:
        """Mark this provider as rate-limited right now."""
        self.last_429 = time.monotonic()
        self.available = False
        logger.warning("Provider %s hit 429 – cooling down for %.0fs", self.name, self.cooldown)

    def check_ready(self) -> bool:
        """Return True if the cooldown has elapsed (and flip available back)."""
        if self.available:
            return True
        if time.monotonic() - self.last_429 >= self.cooldown:
            self.available = True
            logger.info("Provider %s cooldown expired – available again", self.name)
            return True
        return False

    @property
    def seconds_until_ready(self) -> float:
        """Seconds remaining until this provider's cooldown expires."""
        if self.available:
            return 0.0
        remaining = self.cooldown - (time.monotonic() - self.last_429)
        return max(remaining, 0.0)


# Global pool – order determines priority
_provider_pool: list[Provider] = [
    Provider(name="gemini"),
    Provider(name="nvidia"),
]


def _get_ready_provider() -> Provider | None:
    """Return the first provider that is not in cooldown, or None."""
    for p in _provider_pool:
        if p.check_ready():
            return p
    return None


async def _wait_for_any_provider() -> Provider:
    """Sleep until the soonest provider recovers, then return it."""
    soonest = min(_provider_pool, key=lambda p: p.seconds_until_ready)
    wait = soonest.seconds_until_ready
    if wait > 0:
        logger.info(
            "All providers in cooldown – sleeping %.0fs until %s is ready",
            wait, soonest.name,
        )
        await asyncio.sleep(wait)
    soonest.available = True
    return soonest


def _is_429_error(exc: Exception) -> bool:
    """Detect HTTP 429 (rate limit) errors from various client libraries."""
    msg = str(exc).lower()
    if "429" in msg or "rate limit" in msg or "too many requests" in msg:
        return True
    # Check for status_code attribute (httpx / openai exceptions)
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    return status == 429


# ── Prompt builder ──────────────────────────────────────────────────────────

def _build_prompt(task: TaskPayload) -> str:
    """Build a task-aware system+user prompt for the LLM.

    Instead of assuming every task is Python code, the prompt describes
    the task's title and full description, and instructs the LLM that its
    response will be scored 0-100, needing ≥70 to advance.
    """
    return (
        f"# Task: {task.slug}\n\n"
        f"## Description\n{task.prompt}\n\n"
        "## Instructions\n"
        "Solve the task described above. Your submission will be automatically "
        "scored on a scale of 0-100. You need a score of 70 or higher to pass "
        "and level up to the next task.\n\n"
        "Provide ONLY the solution content — no explanations, no commentary, "
        "no markdown fences unless the task specifically requires markdown. "
        "Match the expected output format exactly."
    )


def _build_system_prompt() -> str:
    """Build the system prompt for the LLM provider."""
    return (
        "You are an expert problem solver competing in Agent Arena. "
        "You receive tasks that may involve code (in any language), analysis, "
        "writing, math, or other domains. Read the task description carefully "
        "and produce the highest-quality solution you can. Your response is "
        "scored 0-100 and you need ≥70 to advance. Return only the solution."
    )


# ── Helpers ─────────────────────────────────────────────────────────────────

def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from LLM output if present."""
    stripped = text.strip()
    # Handle ```python ... ``` or ``` ... ```
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        # Remove first line (```python or ```)
        lines = lines[1:]
        # Remove last line if it's ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)
    return stripped


def _safe_slug(slug: str) -> str:
    """Convert a task slug into a filesystem-safe directory name."""
    # Replace slashes with os separator, strip invalid chars
    safe = _INVALID_PATH_CHARS.sub("_", slug)
    return safe.strip("_ ")


# ── Gemini backend ──────────────────────────────────────────────────────────

async def _call_gemini_with_retry(
    runner_obj: Any,
    user_id: str,
    session_id: str,
    message: Any,
    max_attempts: int = 3,
) -> str:
    """Call Gemini via the ADK runner with exponential backoff on errors."""
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response_parts: list[str] = []
            async for event in runner_obj.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message,
            ):
                if event.is_final_response():
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if hasattr(part, "text") and part.text:
                                response_parts.append(part.text)

            if response_parts:
                return "\n".join(response_parts)

            raise RuntimeError("Gemini returned an empty response")

        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                wait = 2 ** attempt  # 2s, 4s, 8s
                logger.warning(
                    "Gemini call failed (attempt %d/%d): %s – retrying in %ds",
                    attempt, max_attempts, exc, wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.error("Gemini call failed after %d attempts: %s", max_attempts, exc)

    raise RuntimeError(f"Gemini failed after {max_attempts} attempts") from last_exc


async def _solve_with_gemini(prompt: str) -> str:
    """Solve a task using the Gemini model via ADK."""
    from agent import runner, session_service
    from google.genai.types import Content, Part

    session = await session_service.create_session(
        app_name=config.AGENT_NAME,
        user_id=config.AGENT_ID,
    )

    return await _call_gemini_with_retry(
        runner_obj=runner,
        user_id=config.AGENT_ID,
        session_id=session.id,
        message=Content(role="user", parts=[Part(text=prompt)]),
    )


# ── NVIDIA backend ─────────────────────────────────────────────────────────

async def _call_nvidia_with_retry(
    prompt: str,
    system_prompt: str,
    max_attempts: int = 3,
) -> str:
    """Call NVIDIA's OpenAI-compatible API with exponential backoff."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        base_url=config.NVIDIA_BASE_URL,
        api_key=config.NVIDIA_API_KEY,
    )

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = await client.chat.completions.create(
                model=config.NVIDIA_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=4096,
            )

            text = response.choices[0].message.content
            if text:
                return text
            raise RuntimeError("NVIDIA returned an empty response")

        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                wait = 2 ** attempt  # 2s, 4s, 8s
                logger.warning(
                    "NVIDIA call failed (attempt %d/%d): %s – retrying in %ds",
                    attempt, max_attempts, exc, wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.error("NVIDIA call failed after %d attempts: %s", max_attempts, exc)

    raise RuntimeError(f"NVIDIA failed after {max_attempts} attempts") from last_exc


async def _solve_with_nvidia(prompt: str, system_prompt: str) -> str:
    """Solve a task using the NVIDIA Nemotron model."""
    return await _call_nvidia_with_retry(prompt, system_prompt)


# ── solve_task ──────────────────────────────────────────────────────────────

async def solve_task(task: TaskPayload) -> Path:
    """Solve a single Arena task and write the result to a submission file.

    Picks the first available provider from the pool. If a provider returns
    a 429, it is put into cooldown and the next provider is tried.

    Args:
        task: The task payload from the Arena MCP server.

    Returns:
        Path to the generated submission file.

    Raises:
        RuntimeError: If all providers fail (non-429 errors).
    """
    # Log the full payload for debugging
    logger.info(
        "Task payload: task_id=%s slug=%s prompt_len=%d metadata=%r",
        task.task_id, task.slug, len(task.prompt), task.metadata,
    )
    logger.debug("Full task prompt:\n%s", task.prompt)

    # Build the task-aware prompt
    user_prompt = _build_prompt(task)
    system_prompt = _build_system_prompt()

    # Try providers from the pool
    last_exc: Exception | None = None
    tried: set[str] = set()
    raw_solution: str | None = None

    while True:
        provider = _get_ready_provider()
        if provider is None:
            provider = await _wait_for_any_provider()

        if provider.name in tried:
            # We've already tried this provider and it failed with a non-429 error
            break

        logger.info(
            "Sending task %s (%s) to %s...",
            task.task_id, task.slug, provider.name.upper(),
        )

        try:
            if provider.name == "nvidia":
                raw_solution = await _solve_with_nvidia(user_prompt, system_prompt)
            else:
                raw_solution = await _solve_with_gemini(user_prompt)
            break  # success
        except Exception as exc:
            last_exc = exc
            tried.add(provider.name)
            if _is_429_error(exc):
                provider.mark_429()
                continue  # try next provider
            logger.error("Provider %s failed with non-429 error: %s", provider.name, exc)
            # Try remaining providers before giving up
            other_ready = [p for p in _provider_pool if p.name not in tried and p.check_ready()]
            if other_ready:
                continue
            break
    else:
        # while/else: loop exited without break (shouldn't happen, but guard)
        if raw_solution is None:
            raise RuntimeError("All providers exhausted") from last_exc

    if raw_solution is None:
        raise RuntimeError("All providers failed") from last_exc

    # Strip any markdown code fences the LLM may have included
    solution = _strip_code_fences(raw_solution)

    # Log a preview
    preview = solution[:200].replace("\n", "\\n")
    logger.info(
        "Solution for %s (%d chars): %s%s",
        task.slug, len(solution), preview, "..." if len(solution) > 200 else "",
    )

    # Write the submission file
    slug_safe = _safe_slug(task.slug)
    task_dir = CONTENT_DIR / slug_safe
    task_dir.mkdir(parents=True, exist_ok=True)
    submission_path = task_dir / "submission.md"
    submission_path.write_text(solution, encoding="utf-8")
    logger.info("Wrote submission to %s", submission_path)

    return submission_path


# ── Main loop ──────────────────────────────────────────────────────────────

async def run_loop() -> None:
    """Poll for tasks, solve them, submit results. Repeat until stopped.

    Registers the agent once at startup, then enters the poll loop.

    Stop conditions:
        - KeyboardInterrupt (Ctrl-C)
        - A file named ``FINISH`` exists in the working directory
        - An unrecoverable exception propagates out
    """
    consecutive_errors = 0
    logger.info(
        "Agent Arena poll loop starting (agent_id=%s, provider=%s)",
        config.AGENT_ID, config.LLM_PROVIDER.upper(),
    )

    # ── Register agent once at startup ──────────────────────────────────
    try:
        reg_response = await register_agent(config.AGENT_ID)
        logger.info("Agent registered successfully: %s", reg_response)
    except Exception:
        logger.exception("Failed to register agent – continuing anyway")

    try:
        while True:
            # ── Check for stop signal ───────────────────────────────────
            if FINISH_SIGNAL_FILE.exists():
                logger.info("FINISH signal file detected – shutting down cleanly.")
                break

            try:
                # ── 1. Fetch task ───────────────────────────────────────
                task = await get_task(config.AGENT_ID)

                if task is None:
                    logger.debug("No tasks available – idling for %.0fs", IDLE_POLL_INTERVAL)
                    await asyncio.sleep(IDLE_POLL_INTERVAL)
                    consecutive_errors = 0
                    continue

                logger.info("Got task %s (slug=%s)", task.task_id, task.slug)

                # ── 2. Solve ────────────────────────────────────────────
                submission_path = await solve_task(task)

                # ── 3. Submit ───────────────────────────────────────────
                response = await submit_task(config.AGENT_ID, task.task_id, submission_path)

                # ── 4. Parse score & skip if below threshold ────────────
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

            except NotImplementedError:
                # solve_task() stub – surface loudly so devs notice immediately
                logger.error(
                    "solve_task() is not implemented yet! "
                    "Fill in the TODO in arena_mcp/poll.py before running for real."
                )
                raise

            except Exception as exc:
                consecutive_errors += 1
                backoff = min(BASE_POLL_INTERVAL * (2 ** consecutive_errors), MAX_BACKOFF)

                # If this is a 429 from the solve step, mark the provider
                if _is_429_error(exc):
                    # Mark whichever provider was being used
                    provider_name = config.LLM_PROVIDER
                    for p in _provider_pool:
                        if p.name == provider_name:
                            p.mark_429()
                            break

                logger.exception("Error in poll loop (attempt %d) – backing off %.0fs", consecutive_errors, backoff)
                await asyncio.sleep(backoff)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt – shutting down poll loop.")
    finally:
        logger.info("Poll loop stopped.")
