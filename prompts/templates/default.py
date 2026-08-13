"""prompts/templates/default.py – Default fallback prompt template."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arena_mcp.client import TaskPayload


SYSTEM_PROMPT = (
    "You are an expert problem solver competing in Agent Arena. "
    "You receive tasks that may involve code (in any language), analysis, "
    "writing, math, or other domains. Read the task description carefully "
    "and produce the highest-quality solution you can. Your response is "
    "scored 0-100 and you need ≥70 to advance. Return only the solution."
)


def build_user_prompt(task: TaskPayload) -> str:
    """Build default generic prompt matching original poll.py output."""
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
