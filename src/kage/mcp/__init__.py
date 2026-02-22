"""MCP (Model Context Protocol) integration for Kage."""

from kage.mcp.client import MCPClient, MCPError
from kage.mcp.manager import MCPManager
from kage.mcp.models import MCPTool, MCPToolResult

__all__ = [
    "MCPClient",
    "MCPError",
    "MCPManager",
    "MCPTool",
    "MCPToolResult",
]
