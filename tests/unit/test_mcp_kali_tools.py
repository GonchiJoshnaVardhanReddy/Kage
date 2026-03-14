"""Unit tests for Kali tools MCP orchestration."""

from __future__ import annotations

import pytest

from kage.mcp.kali_tools import KaliToolsAdvisor
from kage.mcp.manager import MCPManager
from kage.mcp.models import MCPTool, MCPToolResult
from kage.persistence.config import MCPConfig


class _StubManager:
    def __init__(self, responses: dict[str, MCPToolResult]) -> None:
        self._responses = responses

    def has_tool(self, name: str) -> bool:
        return name in {"search_kali_tools", "get_tool_details", "get_tool_usage"}

    async def call_tool(self, name: str, _arguments=None):  # noqa: ANN001
        return self._responses.get(
            name,
            MCPToolResult(tool_name=name, success=False, error="missing", is_error=True),
        )


@pytest.mark.asyncio
async def test_kali_tools_advisor_builds_recommendation() -> None:
    manager = _StubManager(
        {
            "search_kali_tools": MCPToolResult(
                tool_name="search_kali_tools",
                success=True,
                content=[{"type": "text", "text": "- sqlmap: SQL injection testing"}],
            ),
            "get_tool_details": MCPToolResult(
                tool_name="get_tool_details",
                success=True,
                content=[{"type": "text", "text": "sqlmap details"}],
            ),
            "get_tool_usage": MCPToolResult(
                tool_name="get_tool_usage",
                success=True,
                content=[{"type": "text", "text": "sqlmap -u http://target --dbs"}],
            ),
        }
    )
    advisor = KaliToolsAdvisor(manager)  # type: ignore[arg-type]

    result = await advisor.recommend_tools("check SQL injection")

    assert result.has_recommendations
    assert result.recommendations[0].tool_name == "sqlmap"
    assert result.recommendations[0].suggested_command == "sqlmap -u http://target --dbs"


class _FakeClient:
    def __init__(self, result: MCPToolResult) -> None:
        self._result = result
        self.is_connected = True

    async def call_tool(self, _name: str, _arguments=None):  # noqa: ANN001
        return self._result


@pytest.mark.asyncio
async def test_mcp_manager_call_tool_fallback_across_servers() -> None:
    manager = MCPManager(MCPConfig(enabled=True, auto_discover=False, servers=[]))
    manager._tools_cache = {  # type: ignore[attr-defined]
        "search_kali_tools": [
            MCPTool(name="search_kali_tools", description="", server_name="primary"),
            MCPTool(name="search_kali_tools", description="", server_name="secondary"),
        ]
    }
    manager._clients = {  # type: ignore[attr-defined]
        "primary": _FakeClient(
            MCPToolResult(
                tool_name="search_kali_tools",
                success=False,
                error="primary down",
                is_error=True,
            )
        ),
        "secondary": _FakeClient(
            MCPToolResult(
                tool_name="search_kali_tools",
                success=True,
                content=[{"type": "text", "text": "ok"}],
            )
        ),
    }

    result = await manager.call_tool("search_kali_tools", {"query": "nmap"})

    assert result.success is True
    assert result.text == "ok"
