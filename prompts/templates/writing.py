"""prompts/templates/writing.py – Writing/analysis prompt template."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arena_mcp.client import TaskPayload


SYSTEM_PROMPT = (
    "You are an expert communicator, researcher, and analytical writer competing in Agent Arena. "
    "Produce clear, well-structured, authoritative, and precise responses. "
    "Follow all length, format, and content guidelines strictly. Return only the solution."
)


def build_user_prompt(task: TaskPayload) -> str:
    """Build writing/analysis-specific user prompt."""
    return (
        f"# Task (Writing/Analysis): {task.slug}\n\n"
        f"## Requirements\n{task.prompt}\n\n"
        "## Response Instructions\n"
        "1. Write a clear, comprehensive, and well-structured solution matching the requested format.\n"
        "2. Directly address every requirement specified in the prompt.\n"
        "3. Provide ONLY the final text response without meta-commentary or conversational intros."
    )
