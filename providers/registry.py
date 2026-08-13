"""providers/registry.py – ProviderRegistry pool manager for TARS LLM providers."""

from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from providers.base import AbstractProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Manages an ordered pool of AbstractProvider instances.

    Registration order defines selection priority.
    """

    def __init__(self, providers: Sequence[AbstractProvider] | None = None) -> None:
        self._providers: list[AbstractProvider] = list(providers) if providers else []

    def register(self, provider: AbstractProvider) -> None:
        """Register a new provider in the pool."""
        self._providers.append(provider)
        logger.info("Registered LLM provider: %s", provider.name)

    def get_provider(self, name: str) -> AbstractProvider | None:
        """Lookup provider by name."""
        for p in self._providers:
            if p.name == name:
                return p
        return None

    def get_all(self) -> list[AbstractProvider]:
        """Return all registered providers."""
        return list(self._providers)

    def get_ready_provider(self) -> AbstractProvider | None:
        """Return the first provider that is ready (not in cooldown), or None."""
        for p in self._providers:
            if p.check_ready():
                return p
        return None

    async def wait_for_any_provider(self) -> AbstractProvider:
        """Sleep until the soonest provider recovers from cooldown, then return it."""
        if not self._providers:
            raise RuntimeError("No providers registered in ProviderRegistry")

        soonest = min(self._providers, key=lambda p: p.seconds_until_ready)
        wait = soonest.seconds_until_ready
        if wait > 0:
            logger.info(
                "All providers in cooldown – sleeping %.0fs until %s is ready",
                wait, soonest.name,
            )
            await asyncio.sleep(wait)
        soonest.available = True
        return soonest
