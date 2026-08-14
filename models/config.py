"""models/config.py – ModelConfig data container for TARS."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelConfig:
    """Represents model capabilities, constraints, and pricing metadata."""

    id: str
    provider: str
    display_name: str
    context_window: int = 32768
    max_output_tokens: int = 4096
    supports_vision: bool = False
    supports_function_calling: bool = False
    supports_streaming: bool = True
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    rate_limit_rpm: int | None = None
    tags: list[str] = field(default_factory=list)
    notes: str = ""
