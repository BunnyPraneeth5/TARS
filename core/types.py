"""core/types.py – Data contracts for TARS core engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SolveStrategy:
    """Strategy configuration governing task solving execution."""

    provider_name: str | None = None
    model_id: str | None = None
    temperature: float = 0.2
    max_tokens: int = 4096
    review_enabled: bool = True
    max_retries: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Solution:
    """Structured solution object produced by Solver."""

    content: str
    raw_content: str
    provider_used: str
    model_used: str
    latency_ms: float
    confidence_score: float = 1.0
    attempts: int = 1
    review_approved: bool = True
    review_reason: str = "Passed"
