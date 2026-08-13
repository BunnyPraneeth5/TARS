"""prompts/classifier.py – Rule-based task classifier for TARS."""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arena_mcp.client import TaskPayload

logger = logging.getLogger(__name__)




class TaskType(Enum):
    """Categorized task types handled by TARS."""

    CODE = auto()
    WRITING = auto()
    MATH = auto()
    ANALYSIS = auto()
    DEFAULT = auto()


class TaskClassifier:
    """Classifies incoming tasks into domain types using slug, prompt, and metadata."""

    _CODE_KEYWORDS = {
        "python", "javascript", "js", "code", "function", "algorithm",
        "bigcodebench", "implement", "debug", "memory leak", "nl2sql",
        "sql", "refactor", "bug", "script", "program", "class", "method",
    }

    _WRITING_KEYWORDS = {
        "write", "essay", "article", "blog", "creative", "documentation",
        "story", "summary", "summarize", "paraphrase", "translate",
    }

    _MATH_KEYWORDS = {
        "math", "calculate", "equation", "prove", "formula", "proof",
        "algebra", "calculus", "geometry", "theorem",
    }

    _ANALYSIS_KEYWORDS = {
        "analyze", "architecture", "scalability", "design", "evaluate",
        "blockchain", "forensics", "ticker", "review", "audit",
    }

    def classify(self, task: TaskPayload) -> TaskType:
        """Classify a task payload based on keyword signals.

        Args:
            task: Task payload fetched from Arena server.

        Returns:
            The inferred TaskType enum.
        """
        text = f"{task.slug} {task.prompt}".lower()
        meta_type = str(task.metadata.get("type", "")).lower()
        combined = f"{text} {meta_type}"

        # 1. Code signals
        if any(kw in combined for kw in self._CODE_KEYWORDS):
            logger.info("Task %s classified as CODE", task.slug)
            return TaskType.CODE

        # 2. Math signals
        if any(kw in combined for kw in self._MATH_KEYWORDS):
            logger.info("Task %s classified as MATH", task.slug)
            return TaskType.MATH

        # 3. Analysis signals
        if any(kw in combined for kw in self._ANALYSIS_KEYWORDS):
            logger.info("Task %s classified as ANALYSIS", task.slug)
            return TaskType.ANALYSIS

        # 4. Writing signals
        if any(kw in combined for kw in self._WRITING_KEYWORDS):
            logger.info("Task %s classified as WRITING", task.slug)
            return TaskType.WRITING

        # Default fallback
        logger.info("Task %s classified as DEFAULT", task.slug)
        return TaskType.DEFAULT
