"""providers/base.py – AbstractProvider base class for TARS LLM providers."""

from __future__ import annotations

import abc
import logging
import time

logger = logging.getLogger(__name__)


class AbstractProvider(abc.ABC):
    """Abstract base class for all LLM providers in TARS.

    Tracks availability and rate-limit (429) cooldown status while defining
    the contract for solving tasks.
    """

    def __init__(self, name: str, cooldown: float = 300.0) -> None:
        self.name = name
        self.available = True
        self.last_429 = 0.0
        self.cooldown = cooldown

    def mark_rate_limited(self) -> None:
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

    @staticmethod
    def is_429_error(exc: Exception) -> bool:
        """Detect HTTP 429 (rate limit) errors from various client libraries."""
        msg = str(exc).lower()
        if "429" in msg or "rate limit" in msg or "too many requests" in msg:
            return True
        status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        return status == 429

    @abc.abstractmethod
    async def solve(self, prompt: str, system_prompt: str) -> str:
        """Solve a task using this provider.

        Args:
            prompt: User-facing prompt for the task.
            system_prompt: System-level instruction.

        Returns:
            The raw text response from the LLM.

        Raises:
            RuntimeError: On provider failure or empty response.
            Exception: On network, auth, or rate limit errors.
        """
        pass
