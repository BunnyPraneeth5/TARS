"""providers/retry.py – Shared retry utility with exponential backoff for LLM calls."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def call_with_retry(
    fn: Callable[[], Awaitable[T]],
    provider_name: str,
    max_attempts: int = 3,
    base_delay: float = 2.0,
) -> T:
    """Execute an async provider function with exponential backoff on exceptions.

    Args:
        fn: Zero-arg async callable executing the provider call.
        provider_name: Identifier for logging context.
        max_attempts: Maximum number of attempts before raising.
        base_delay: Base delay in seconds for exponential backoff (2^attempt * base_delay).

    Returns:
        The return value of fn().

    Raises:
        RuntimeError: If all attempts fail.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                wait = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "%s call failed (attempt %d/%d): %s – retrying in %.1fs",
                    provider_name, attempt, max_attempts, exc, wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.error("%s call failed after %d attempts: %s", provider_name, max_attempts, exc)

    raise RuntimeError(f"{provider_name} failed after {max_attempts} attempts") from last_exc
