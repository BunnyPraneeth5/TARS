"""prompts/templates/code.py – Coding task prompt template."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arena_mcp.client import TaskPayload


SYSTEM_PROMPT = (
    "You are an elite software engineer competing in Agent Arena. "
    "Your objective is to produce clean, correct, high-performance code that passes all test cases. "
    "Focus on edge cases, efficiency, correct imports, and proper syntax. "
    "Return ONLY the executable code or required solution output without conversational filler."
)


def build_user_prompt(task: TaskPayload) -> str:
    """Build code-specific user prompt."""
    return (
        f"# Task (Coding/Software): {task.slug}\n\n"
        f"## Problem Description\n{task.prompt}\n\n"
        "## Coding Guidelines\n"
        "1. Write complete, working code that fully solves the problem.\n"
        "2. Ensure accurate syntax, imports, and algorithm efficiency.\n"
        "3. Provide ONLY the code/solution content without commentary or conversation.\n"
        "4. Do NOT enclose in markdown code fences unless explicitly requested by the prompt."
    )
