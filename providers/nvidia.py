"""providers/nvidia.py – NVIDIA OpenAI-compatible API implementation of AbstractProvider."""

from __future__ import annotations

import logging

import config
from openai import AsyncOpenAI
from providers.base import AbstractProvider
from providers.retry import call_with_retry

logger = logging.getLogger(__name__)


class NVIDIAProvider(AbstractProvider):
    """LLM provider implementation for NVIDIA models via OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str = config.NVIDIA_API_KEY,
        model: str = config.NVIDIA_MODEL,
        base_url: str = config.NVIDIA_BASE_URL,
        name: str = "nvidia",
        cooldown: float = 300.0,
    ) -> None:
        super().__init__(name=name, cooldown=cooldown)
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    async def solve(self, prompt: str, system_prompt: str) -> str:
        """Solve a task using NVIDIA Nemotron via OpenAI client."""
        client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )

        async def _call() -> str:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=4096,
            )

            text = response.choices[0].message.content
            if text:
                return text
            raise RuntimeError("NVIDIA returned an empty response")

        return await call_with_retry(_call, provider_name="NVIDIA")
