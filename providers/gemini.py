"""providers/gemini.py – Gemini ADK implementation of AbstractProvider."""

from __future__ import annotations

import logging
from typing import Any

import config
from google.genai.types import Content, Part
from providers.base import AbstractProvider
from providers.retry import call_with_retry

logger = logging.getLogger(__name__)


class GeminiProvider(AbstractProvider):
    """LLM provider implementation for Google Gemini via Google ADK."""

    def __init__(
        self,
        runner: Any,
        session_service: Any,
        name: str = "gemini",
        cooldown: float = 300.0,
    ) -> None:
        super().__init__(name=name, cooldown=cooldown)
        self.runner = runner
        self.session_service = session_service

    async def solve(self, prompt: str, system_prompt: str) -> str:
        """Solve a task using Gemini via ADK runner."""
        session = await self.session_service.create_session(
            app_name=config.AGENT_NAME,
            user_id=config.AGENT_ID,
        )

        message = Content(role="user", parts=[Part(text=prompt)])

        async def _call() -> str:
            response_parts: list[str] = []
            async for event in self.runner.run_async(
                user_id=config.AGENT_ID,
                session_id=session.id,
                new_message=message,
            ):
                if event.is_final_response():
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if hasattr(part, "text") and part.text:
                                response_parts.append(part.text)

            if response_parts:
                return "\n".join(response_parts)

            raise RuntimeError("Gemini returned an empty response")

        return await call_with_retry(_call, provider_name="Gemini")
