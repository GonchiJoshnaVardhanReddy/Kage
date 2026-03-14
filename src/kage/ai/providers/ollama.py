"""Ollama LLM provider for Kage."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from kage.ai.base import (
    BaseLLMProvider,
    LLMConfig,
    LLMMessage,
    LLMResponse,
    StreamChunk,
)

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        api_key: str | None = None,
    ) -> None:
        super().__init__(base_url, api_key)
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "ollama"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(120.0, connect=10.0),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def check_connection(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.debug("Ollama connection check failed: %s", e)
            return False

    async def list_models(self) -> list[str]:
        """List available models."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.warning("Failed to list Ollama models: %s", e)
        return []

    # Keywords that indicate a model is embedding-only (not suitable for chat)
    EMBEDDING_KEYWORDS = {"embed", "embedding", "nomic-embed", "bge", "e5", "gte"}

    def _build_request_body(
        self,
        messages: list[LLMMessage],
        config: LLMConfig,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Build the request body for Ollama API."""
        model_lower = config.model.lower()
        if any(kw in model_lower for kw in self.EMBEDDING_KEYWORDS):
            raise ValueError(
                f"Model '{config.model}' appears to be an embedding model, not a chat model. "
                f"Please configure a chat model (e.g. llama3.1, mistral, qwen2). "
                f"Run 'kage setup' to reconfigure."
            )
        body: dict[str, Any] = {
            "model": config.model,
            "messages": self._convert_messages(messages),
            "stream": stream,
            "options": {
                "temperature": config.temperature,
                "num_predict": config.max_tokens,
                "top_p": config.top_p,
            },
        }

        if config.stop:
            body["options"]["stop"] = config.stop

        # Ollama supports tools in newer versions
        if config.tools:
            body["tools"] = config.tools

        return body

    async def complete(
        self,
        messages: list[LLMMessage],
        config: LLMConfig,
    ) -> LLMResponse:
        """Send a completion request to Ollama."""
        client = await self._get_client()
        body = self._build_request_body(messages, config, stream=False)

        response = await client.post("/api/chat", json=body)
        response.raise_for_status()

        data = response.json()
        message = data.get("message", {})

        return LLMResponse(
            content=message.get("content", ""),
            role=message.get("role", "assistant"),
            finish_reason=data.get("done_reason"),
            tool_calls=message.get("tool_calls"),
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            },
            raw=data,
        )

    def stream(
        self,
        messages: list[LLMMessage],
        config: LLMConfig,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a completion response from Ollama."""
        async def _stream() -> AsyncIterator[StreamChunk]:
            client = await self._get_client()
            body = self._build_request_body(messages, config, stream=True)

            async with client.stream("POST", "/api/chat", json=body) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        message = data.get("message", {})
                        content = message.get("content", "")

                        finish_reason = None
                        if data.get("done"):
                            finish_reason = data.get("done_reason", "stop")

                        yield StreamChunk(
                            content=content,
                            finish_reason=finish_reason,
                            tool_calls=message.get("tool_calls"),
                        )

                        if data.get("done"):
                            break

                    except json.JSONDecodeError:
                        continue

        return _stream()
