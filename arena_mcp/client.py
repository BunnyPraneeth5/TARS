"""
arena_mcp/client.py – Thin wrapper around fastmcp.Client for Agent Arena.

Provides get_task() and submit_task() with automatic JWT retry on AUTH_ERROR.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastmcp import Client

import config

logger = logging.getLogger(__name__)

# ── Data containers ─────────────────────────────────────────────────────────

@dataclass
class TaskPayload:
    """Represents a single task fetched from the Arena MCP server."""

    task_id: str
    slug: str
    prompt: str
    metadata: dict[str, Any]


# ── Auth-error sentinel ────────────────────────────────────────────────────

class AuthError(Exception):
    """Raised when the MCP server rejects us with an authentication error."""


# ── Helpers ─────────────────────────────────────────────────────────────────

def _build_client() -> Client:
    """Construct a fastmcp Client pointed at the configured MCP_ENDPOINT."""
    return Client(config.MCP_ENDPOINT)


def _is_auth_error(exc: Exception) -> bool:
    """Decide whether *exc* is an authentication / authorisation failure."""
    msg = str(exc).lower()
    return any(tok in msg for tok in ("auth", "unauthorized", "403", "jwt", "token"))


def _parse_tool_result(result: Any) -> Any:
    """Extract structured data from an MCP tool result.

    fastmcp's call_tool returns a CallToolResult object containing content
    blocks. We extract the first TextContent block and parse its JSON text.
    """
    if result is None:
        return None

    # Handle CallToolResult objects (fastmcp wraps results in this)
    content = getattr(result, "content", None)
    if content is None:
        # If it's already a dict or primitive, just return it
        if isinstance(result, (dict, str, int, float, bool)):
            return result
        # Try treating it as a list of content blocks directly
        content = result if isinstance(result, list) else None

    if content is not None:
        for block in content:
            if hasattr(block, "text"):
                try:
                    return json.loads(block.text)
                except (json.JSONDecodeError, TypeError):
                    return block.text
        return content

    return result


# ── Public API ──────────────────────────────────────────────────────────────

async def get_task(agent_id: str) -> TaskPayload | None:
    """Fetch the next available task from the Arena MCP server.

    Args:
        agent_id: The agent identifier registered with Agent Arena.

    Returns:
        A TaskPayload if a task is available, or None when the queue is empty.

    Raises:
        AuthError: If the server rejects us after one JWT-refresh retry.
    """
    async def _call() -> TaskPayload | None:
        async with _build_client() as client:
            result = await client.call_tool(
                "get_tasks",
                {
                    "idToken": config.EPHEMERAL_JWT,
                    "agentId": agent_id,
                },
            )
            parsed = _parse_tool_result(result)
            if parsed is None:
                return None

            # get_tasks returns a JSON array containing exactly one task object
            if isinstance(parsed, list):
                if len(parsed) == 0:
                    return None
                task_data = parsed[0]
            elif isinstance(parsed, dict):
                task_data = parsed
            else:
                logger.warning("Unexpected get_tasks response type: %s – %r", type(parsed), parsed)
                return None

            return TaskPayload(
                task_id=task_data.get("id", task_data.get("taskId", task_data.get("task_id", "unknown"))),
                slug=task_data.get("title", task_data.get("slug", "unknown")),
                prompt=task_data.get("description", task_data.get("prompt", "")),
                metadata={k: v for k, v in task_data.items()
                          if k not in ("id", "taskId", "task_id", "slug", "title", "prompt", "description")},
            )

    try:
        return await _call()
    except Exception as exc:
        if _is_auth_error(exc):
            logger.warning("AUTH_ERROR on get_task – refreshing JWT and retrying once.")
            config.refresh_jwt()
            return await _call()  # retry once; let it raise on second failure
        raise


async def submit_task(agent_id: str, task_id: str, file_path: str | Path) -> dict[str, Any]:
    """Submit a completed task back to the Arena MCP server.

    Args:
        agent_id: The agent identifier registered with Agent Arena.
        task_id:  The task ID received from get_task().
        file_path: Absolute or relative path to the submission file
                   (typically ``content/tasks/<slug>/submission.md``).

    Returns:
        The raw response dict from the Arena server.

    Raises:
        AuthError: If the server rejects us after one JWT-refresh retry.
        FileNotFoundError: If *file_path* does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Submission file not found: {path}")

    submission_content = path.read_text(encoding="utf-8")

    async def _call() -> dict[str, Any]:
        async with _build_client() as client:
            result = await client.call_tool(
                "submit_task",
                {
                    "idToken": config.EPHEMERAL_JWT,
                    "agentId": agent_id,
                    "taskId": task_id,
                    "content": submission_content,
                },
            )
            parsed = _parse_tool_result(result)
            return parsed if isinstance(parsed, dict) else {"raw": parsed}

    try:
        return await _call()
    except Exception as exc:
        if _is_auth_error(exc):
            logger.warning("AUTH_ERROR on submit_task – refreshing JWT and retrying once.")
            config.refresh_jwt()
            return await _call()
        raise
