"""OpenAI LLM provider for Kage."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from kage.ai.base import (
    BaseLLMProvider,
    LLMConfig,
    LLMMessage,
    LLMResponse,
    StreamChunk,
)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider (also works with OpenAI-compatible APIs)."""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
    ) -> None:
        super().__init__(base_url, api_key)
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "openai"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(120.0, connect=10.0),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def check_connection(self) -> bool:
        """Check if OpenAI API is reachable."""
        try:
            client = await self._get_client()
            response = await client.get("/models")
            return response.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """List available models."""
        try:
            client = await self._get_client()
            response = await client.get("/models")
            if response.status_code == 200:
                data = response.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception:
            pass
        return []

    def _build_request_body(
        self,
        messages: list[LLMMessage],
        config: LLMConfig,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Build the request body for OpenAI API."""
        body: dict[str, Any] = {
            "model": config.model,
            "messages": self._convert_messages(messages),
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
            "stream": stream,
        }

        if config.stop:
            body["stop"] = config.stop

        if config.tools:
            body["tools"] = config.tools
            if config.tool_choice:
                body["tool_choice"] = config.tool_choice

        return body

    async def complete(
        self,
        messages: list[LLMMessage],
        config: LLMConfig,
    ) -> LLMResponse:
        """Send a completion request to OpenAI."""
        client = await self._get_client()
        body = self._build_request_body(messages, config, stream=False)

        response = await client.post("/chat/completions", json=body)
        response.raise_for_status()

        data = response.json()
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        return LLMResponse(
            content=message.get("content", "") or "",
            role=message.get("role", "assistant"),
            finish_reason=choice.get("finish_reason"),
            tool_calls=message.get("tool_calls"),
            usage=data.get("usage"),
            raw=data,
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        config: LLMConfig,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a completion response from OpenAI."""
        client = await self._get_client()
        body = self._build_request_body(messages, config, stream=True)

        async with client.stream("POST", "/chat/completions", json=body) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line:
                    continue

                # SSE format: "data: {...}" or "data: [DONE]"
                if line.startswith("data: "):
                    data_str = line[6:]

                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                        choice = data.get("choices", [{}])[0]
                        delta = choice.get("delta", {})

                        content = delta.get("content", "") or ""
                        finish_reason = choice.get("finish_reason")
                        tool_calls = delta.get("tool_calls")

                        yield StreamChunk(
                            content=content,
                            finish_reason=finish_reason,
                            tool_calls=tool_calls,
                        )

                        if finish_reason:
                            break

                    except json.JSONDecodeError:
                        continue


class LMStudioProvider(OpenAIProvider):
    """LM Studio provider (OpenAI-compatible)."""

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        api_key: str | None = None,
    ) -> None:
        super().__init__(base_url, api_key)

    @property
    def provider_name(self) -> str:
        return "lmstudio"
