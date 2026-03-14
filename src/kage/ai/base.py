"""Base LLM provider interface for Kage."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


@dataclass
class LLMMessage:
    """A message in an LLM conversation."""

    role: str  # system, user, assistant, tool
    content: str
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: str
    role: str = "assistant"
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    usage: dict[str, int] | None = None
    raw: dict[str, Any] | None = None


@dataclass
class StreamChunk:
    """A chunk of streaming response."""

    content: str
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


@dataclass
class LLMConfig:
    """Configuration for LLM provider."""

    model: str
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    stop: list[str] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None


class ToolDefinition(BaseModel):
    """Definition of a tool the LLM can call."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of the provider."""
        ...

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        config: LLMConfig,
    ) -> LLMResponse:
        """Send a completion request and return the full response."""
        ...

    @abstractmethod
    def stream(
        self,
        messages: list[LLMMessage],
        config: LLMConfig,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a completion response chunk by chunk."""
        ...

    @abstractmethod
    async def check_connection(self) -> bool:
        """Check if the provider is reachable and configured correctly."""
        ...

    async def close(self) -> None:
        """Close any provider resources."""
        return None

    async def list_models(self) -> list[str]:
        """List available models, if the provider supports it."""
        return []

    def _convert_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        """Convert LLMMessage objects to provider-specific format."""
        result = []
        for msg in messages:
            m: dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.name:
                m["name"] = msg.name
            if msg.tool_calls:
                m["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            result.append(m)
        return result
