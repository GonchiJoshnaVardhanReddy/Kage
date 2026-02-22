"""Provider factory for Kage."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kage.ai.base import BaseLLMProvider
from kage.ai.providers.ollama import OllamaProvider
from kage.ai.providers.openai import LMStudioProvider, OpenAIProvider

if TYPE_CHECKING:
    from kage.persistence.config import LLMConfig


def create_provider(config: LLMConfig) -> BaseLLMProvider:
    """Create an LLM provider based on configuration."""
    provider_map = {
        "ollama": OllamaProvider,
        "openai": OpenAIProvider,
        "lmstudio": LMStudioProvider,
        "custom": OpenAIProvider,  # Custom uses OpenAI-compatible API
    }

    provider_class = provider_map.get(config.provider.lower())
    if provider_class is None:
        raise ValueError(f"Unknown provider: {config.provider}")

    return provider_class(
        base_url=config.base_url,
        api_key=config.api_key,
    )
