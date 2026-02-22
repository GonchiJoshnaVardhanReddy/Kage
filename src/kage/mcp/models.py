"""MCP data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPTool:
    """A tool exposed by an MCP server."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str | None = None

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


@dataclass
class MCPToolResult:
    """Result from calling an MCP tool."""

    tool_name: str
    success: bool
    content: Any = None
    error: str | None = None
    is_error: bool = False

    @property
    def text(self) -> str:
        """Get result as text."""
        if self.is_error or self.error:
            return f"Error: {self.error}"
        if isinstance(self.content, str):
            return self.content
        if isinstance(self.content, list):
            # MCP returns content as list of content blocks
            texts = []
            for item in self.content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        texts.append(item.get("text", ""))
                    elif "text" in item:
                        texts.append(item["text"])
                else:
                    texts.append(str(item))
            return "\n".join(texts)
        return str(self.content) if self.content else ""


@dataclass
class MCPServerInfo:
    """Information about an MCP server."""

    name: str
    version: str | None = None
    protocol_version: str = "2024-11-05"
    capabilities: dict[str, Any] = field(default_factory=dict)
    tools: list[MCPTool] = field(default_factory=list)


@dataclass
class MCPResource:
    """A resource exposed by an MCP server."""

    uri: str
    name: str
    description: str | None = None
    mime_type: str | None = None


@dataclass
class MCPPrompt:
    """A prompt template from an MCP server."""

    name: str
    description: str | None = None
    arguments: list[dict[str, Any]] = field(default_factory=list)
