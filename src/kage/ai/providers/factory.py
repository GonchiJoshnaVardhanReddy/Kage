"""Provider factory for Kage."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from kage.ai.base import BaseLLMProvider
from kage.ai.providers.ollama import OllamaProvider
from kage.ai.providers.openai import LMStudioProvider, OpenAIProvider

if TYPE_CHECKING:
    from kage.persistence.config import LLMConfig

ProviderFactory = Callable[[str, str | None], BaseLLMProvider]


def create_provider(config: LLMConfig) -> BaseLLMProvider:
    """Create an LLM provider based on configuration."""
    provider_map: dict[str, ProviderFactory] = {
        "ollama": lambda base_url, api_key: OllamaProvider(
            base_url=base_url, api_key=api_key
        ),
        "openai": lambda base_url, api_key: OpenAIProvider(
            base_url=base_url, api_key=api_key
        ),
        "lmstudio": lambda base_url, api_key: LMStudioProvider(
            base_url=base_url, api_key=api_key
        ),
        "custom": lambda base_url, api_key: OpenAIProvider(
            base_url=base_url, api_key=api_key
        ),  # Custom uses OpenAI-compatible API
    }

    provider_class = provider_map.get(config.provider.lower())
    if provider_class is None:
        raise ValueError(f"Unknown provider: {config.provider}")

    return provider_class(config.base_url, config.api_key)
