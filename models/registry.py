"""models/registry.py – ModelRegistry query engine for TARS."""

from __future__ import annotations

import logging
from pathlib import Path

from models.config import ModelConfig

logger = logging.getLogger(__name__)

# Standard default models registered in-code
DEFAULT_MODELS = [
    ModelConfig(
        id="gemini-2.5-flash",
        provider="gemini",
        display_name="Gemini 2.5 Flash",
        context_window=1048576,
        max_output_tokens=65536,
        supports_vision=True,
        supports_function_calling=True,
        cost_per_1k_input=0.00015,
        cost_per_1k_output=0.0006,
        tags=["fast", "code", "reasoning"],
    ),
    ModelConfig(
        id="gemini-2.5-pro",
        provider="gemini",
        display_name="Gemini 2.5 Pro",
        context_window=1048576,
        max_output_tokens=65536,
        supports_vision=True,
        supports_function_calling=True,
        cost_per_1k_input=0.00125,
        cost_per_1k_output=0.01,
        tags=["reasoning", "code", "premium"],
    ),
    ModelConfig(
        id="nvidia/nemotron-3-super-120b-a12b",
        provider="nvidia",
        display_name="NVIDIA Nemotron 3 Super 120B",
        context_window=32768,
        max_output_tokens=4096,
        tags=["free", "code"],
    ),
]


class ModelRegistry:
    """Catalog of known models with capabilities, constraints, and pricing."""

    def __init__(self, models: list[ModelConfig] | None = None) -> None:
        self._models: dict[str, ModelConfig] = {}
        initial = models if models is not None else DEFAULT_MODELS
        for m in initial:
            self.register(m)

    def register(self, config: ModelConfig) -> None:
        """Register a model in the catalog."""
        self._models[config.id] = config
        logger.debug("Registered model in registry: %s (%s)", config.id, config.provider)

    def get(self, model_id: str) -> ModelConfig | None:
        """Lookup model config by ID."""
        return self._models.get(model_id)

    def list_all(self) -> list[ModelConfig]:
        """Return all registered models."""
        return list(self._models.values())

    def list_by_provider(self, provider: str) -> list[ModelConfig]:
        """Return models matching provider."""
        return [m for m in self._models.values() if m.provider == provider]

    def list_by_min_context(self, min_tokens: int) -> list[ModelConfig]:
        """Return models meeting context window requirement."""
        return [m for m in self._models.values() if m.context_window >= min_tokens]

    def cheapest(self, min_context: int = 0) -> ModelConfig | None:
        """Return cheapest model matching context requirement."""
        eligible = self.list_by_min_context(min_context)
        if not eligible:
            return None
        return min(eligible, key=lambda m: m.cost_per_1k_input + m.cost_per_1k_output)

    def load_from_yaml(self, path: Path) -> None:
        """Populate registry from YAML file if available."""
        if not path.exists():
            logger.warning("YAML model file not found: %s", path)
            return

        try:
            import yaml

            content = path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            for m_dict in data.get("models", []):
                cfg = ModelConfig(
                    id=m_dict["id"],
                    provider=m_dict["provider"],
                    display_name=m_dict.get("display_name", m_dict["id"]),
                    context_window=m_dict.get("context_window", 32768),
                    max_output_tokens=m_dict.get("max_output_tokens", 4096),
                    supports_vision=m_dict.get("supports_vision", False),
                    supports_function_calling=m_dict.get("supports_function_calling", False),
                    supports_streaming=m_dict.get("supports_streaming", True),
                    cost_per_1k_input=m_dict.get("cost_per_1k_input", 0.0),
                    cost_per_1k_output=m_dict.get("cost_per_1k_output", 0.0),
                    rate_limit_rpm=m_dict.get("rate_limit_rpm"),
                    tags=m_dict.get("tags", []),
                    notes=m_dict.get("notes", ""),
                )
                self.register(cfg)
            logger.info("Loaded models from %s", path)
        except Exception as exc:
            logger.warning("Failed to load models from %s: %s", path, exc)
