"""
arena_mcp/poll.py – Polling loop: get_task → solve → submit_task, repeat.

Runs until interrupted (Ctrl-C) or a FINISH signal file is detected.
Supports Gemini (via ADK) and NVIDIA (via OpenAI-compatible API) as LLM providers.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

import config
from arena_mcp.client import TaskPayload, get_task, submit_task

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────

BASE_POLL_INTERVAL: float = 5.0     # seconds between polls when a task was found
IDLE_POLL_INTERVAL: float = 30.0    # seconds between polls when queue is empty
MAX_BACKOFF: float = 120.0          # ceiling for exponential backoff on errors

FINISH_SIGNAL_FILE: Path = Path("FINISH")  # touch this file to stop the loop

CONTENT_DIR: Path = Path("content/tasks")

# Regex to strip invalid filename chars on Windows (: * ? " < > |)
_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*]')

SOLVE_SYSTEM_PROMPT = (
    "You are a Python expert. Solve the given coding problem. "
    "Return only the Python code, no explanation, no markdown fences."
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
                    {"role": "system", "content": SOLVE_SYSTEM_PROMPT},
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


async def _solve_with_nvidia(prompt: str) -> str:
    """Solve a task using the NVIDIA Nemotron model."""
    return await _call_nvidia_with_retry(prompt)


# ── solve_task ──────────────────────────────────────────────────────────────

async def solve_task(task: TaskPayload) -> Path:
    """Solve a single Arena task and write the result to a submission file.

    Uses either Gemini (via ADK) or NVIDIA (via OpenAI-compatible API)
    depending on the LLM_PROVIDER config setting.

    Args:
        task: The task payload from the Arena MCP server.

    Returns:
        Path to the generated submission file.
    """
    # Log the full payload for debugging
    logger.info(
        "Task payload: task_id=%s slug=%s prompt_len=%d metadata=%r",
        task.task_id, task.slug, len(task.prompt), task.metadata,
    )
    logger.debug("Full task prompt:\n%s", task.prompt)

    # Build the prompt
    user_prompt = (
        f"Task: {task.slug}\n\n"
        f"{task.prompt}\n\n"
        f"{SOLVE_SYSTEM_PROMPT}"
    )

    provider = config.LLM_PROVIDER
    logger.info(
        "Sending task %s (%s) to %s...",
        task.task_id, task.slug, provider.upper(),
    )

    # Dispatch to the configured provider
    if provider == "nvidia":
        raw_solution = await _solve_with_nvidia(user_prompt)
    else:
        raw_solution = await _solve_with_gemini(user_prompt)

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
                logger.info("Submitted task %s – server response: %s", task.task_id, response)

                consecutive_errors = 0
                await asyncio.sleep(BASE_POLL_INTERVAL)

            except NotImplementedError:
                # solve_task() stub – surface loudly so devs notice immediately
                logger.error(
                    "solve_task() is not implemented yet! "
                    "Fill in the TODO in arena_mcp/poll.py before running for real."
                )
                raise

            except Exception:
                consecutive_errors += 1
                backoff = min(BASE_POLL_INTERVAL * (2 ** consecutive_errors), MAX_BACKOFF)
                logger.exception("Error in poll loop (attempt %d) – backing off %.0fs", consecutive_errors, backoff)
                await asyncio.sleep(backoff)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt – shutting down poll loop.")
    finally:
        logger.info("Poll loop stopped.")
