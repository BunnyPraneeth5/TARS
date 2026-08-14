"""core/reviewer.py – Post-solve quality assurance Reviewer for TARS."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arena_mcp.client import TaskPayload

logger = logging.getLogger(__name__)

# Refusal phrases commonly returned by models on forbidden or misunderstood prompts
REFUSAL_PATTERNS = [
    re.compile(r"\bas an ai\b", re.IGNORECASE),
    re.compile(r"\bi cannot fulfill\b", re.IGNORECASE),
    re.compile(r"\bi am unable to\b", re.IGNORECASE),
    re.compile(r"\bi cannot assist\b", re.IGNORECASE),
    re.compile(r"\bi can't help\b", re.IGNORECASE),
    re.compile(r"\bsorry, but i cannot\b", re.IGNORECASE),
    re.compile(r"\bi cannot write code for\b", re.IGNORECASE),
]


@dataclass
class ReviewResult:
    """Outcome of solution quality review."""

    approved: bool
    reason: str
    sanitized_content: str | None = None
    confidence: float = 1.0


class Reviewer:
    """Inspects LLM outputs before submission to detect refusals, empty output, or format flaws."""

    def review(self, task: TaskPayload, raw_solution: str) -> ReviewResult:
        """Inspect solution for quality, format matching, and refusal patterns.

        Args:
            task: Task payload.
            raw_solution: LLM response string.

        Returns:
            ReviewResult indicating approval status and feedback.
        """
        cleaned = raw_solution.strip()

        # 1. Empty solution check
        if not cleaned:
            logger.warning("Reviewer rejected solution for %s: Empty response", task.slug)
            return ReviewResult(approved=False, reason="Empty response from model", confidence=0.0)

        # 2. Refusal pattern check
        for pattern in REFUSAL_PATTERNS:
            if pattern.search(cleaned):
                logger.warning("Reviewer rejected solution for %s: Detected refusal phrase (%s)", task.slug, pattern.pattern)
                return ReviewResult(
                    approved=False,
                    reason=f"Model refusal detected: {pattern.pattern}",
                    confidence=0.1,
                )

        # 3. Minimum length check for complex tasks
        if len(cleaned) < 5 and len(task.prompt) > 100:
            logger.warning("Reviewer flagged solution for %s: Unusually short response (%d chars)", task.slug, len(cleaned))
            return ReviewResult(
                approved=True,
                reason="Response approved but unusually short",
                sanitized_content=cleaned,
                confidence=0.5,
            )

        logger.debug("Reviewer approved solution for %s", task.slug)
        return ReviewResult(
            approved=True,
            reason="Response passed quality checks",
            sanitized_content=cleaned,
            confidence=0.95,
        )
