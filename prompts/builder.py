"""prompts/builder.py – PromptBuilder for constructing type-aware prompts."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arena_mcp.client import TaskPayload

from prompts.classifier import TaskType
from prompts.templates import code, default, writing


logger = logging.getLogger(__name__)


class PromptBuilder:
    """Selects and renders domain-specific prompts based on TaskType."""

    def build_prompt(self, task: TaskPayload, task_type: TaskType) -> str:
        """Construct user prompt tailored to task type."""
        if task_type == TaskType.CODE:
            return code.build_user_prompt(task)
        elif task_type in (TaskType.WRITING, TaskType.ANALYSIS):
            return writing.build_user_prompt(task)
        else:
            return default.build_user_prompt(task)

    def build_system_prompt(self, task_type: TaskType) -> str:
        """Construct system prompt tailored to task type."""
        if task_type == TaskType.CODE:
            return code.SYSTEM_PROMPT
        elif task_type in (TaskType.WRITING, TaskType.ANALYSIS):
            return writing.SYSTEM_PROMPT
        else:
            return default.SYSTEM_PROMPT
