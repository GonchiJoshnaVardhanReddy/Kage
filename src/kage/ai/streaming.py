"""Streaming response handler for Kage."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from kage.ai.base import BaseLLMProvider, LLMConfig, LLMMessage


@dataclass
class StreamState:
    """State accumulated during streaming."""

    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str | None = None
    chunks_received: int = 0


class StreamHandler:
    """Handles streaming responses from LLM providers."""

    def __init__(
        self,
        provider: BaseLLMProvider,
        on_chunk: Callable[[str], None] | None = None,
        on_complete: Callable[[str], None] | None = None,
    ) -> None:
        self.provider = provider
        self.on_chunk = on_chunk
        self.on_complete = on_complete

    async def stream_response(
        self,
        messages: list[LLMMessage],
        config: LLMConfig,
    ) -> StreamState:
        """Stream a response and return accumulated state."""
        state = StreamState()

        async for chunk in self.provider.stream(messages, config):
            state.chunks_received += 1
            state.content += chunk.content

            if chunk.tool_calls:
                state.tool_calls.extend(chunk.tool_calls)

            if chunk.finish_reason:
                state.finish_reason = chunk.finish_reason

            # Call chunk callback
            if self.on_chunk and chunk.content:
                self.on_chunk(chunk.content)

        # Call completion callback
        if self.on_complete:
            self.on_complete(state.content)

        return state

    async def stream_with_timeout(
        self,
        messages: list[LLMMessage],
        config: LLMConfig,
        timeout: float = 120.0,
    ) -> StreamState:
        """Stream with a timeout."""
        try:
            return await asyncio.wait_for(
                self.stream_response(messages, config),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            state = StreamState()
            state.finish_reason = "timeout"
            return state


class BufferedStreamHandler:
    """Streams responses with word/line buffering for smoother output."""

    def __init__(
        self,
        provider: BaseLLMProvider,
        on_token: Callable[[str], None] | None = None,
        on_line: Callable[[str], None] | None = None,
        buffer_mode: str = "word",  # "char", "word", or "line"
    ) -> None:
        self.provider = provider
        self.on_token = on_token
        self.on_line = on_line
        self.buffer_mode = buffer_mode

    async def stream_response(
        self,
        messages: list[LLMMessage],
        config: LLMConfig,
    ) -> StreamState:
        """Stream with buffering."""
        state = StreamState()
        buffer = ""

        async for chunk in self.provider.stream(messages, config):
            state.chunks_received += 1
            state.content += chunk.content
            buffer += chunk.content

            if self.buffer_mode == "char":
                if self.on_token and chunk.content:
                    self.on_token(chunk.content)
                buffer = ""

            elif self.buffer_mode == "word":
                # Flush on whitespace
                if buffer and buffer[-1] in " \t\n":
                    if self.on_token:
                        self.on_token(buffer)
                    buffer = ""

            elif self.buffer_mode == "line":
                # Flush on newline
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if self.on_line:
                        self.on_line(line + "\n")

            if chunk.tool_calls:
                state.tool_calls.extend(chunk.tool_calls)

            if chunk.finish_reason:
                state.finish_reason = chunk.finish_reason

        # Flush remaining buffer
        if buffer:
            if self.buffer_mode == "line" and self.on_line:
                self.on_line(buffer)
            elif self.on_token:
                self.on_token(buffer)

        return state


async def stream_to_console(
    provider: BaseLLMProvider,
    messages: list[LLMMessage],
    config: LLMConfig,
    print_fn: Callable[[str], None] = print,
) -> str:
    """Simple helper to stream response directly to console."""
    handler = StreamHandler(
        provider=provider,
        on_chunk=lambda c: print_fn(c, end="", flush=True),
    )
    state = await handler.stream_response(messages, config)
    print_fn("")  # Final newline
    return state.content
