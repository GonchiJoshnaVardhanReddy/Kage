"""Tests for MCP adapter ToolRegistry integration."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from kage.core.hooks import HookEvent
from kage.core.tools import ToolExecutionPlan, ToolRegistry
from kage.core.tools.mcp_adapter import (
    MCPConnectionError,
    MCPExecutionError,
    MCPSchemaError,
    MCPServerConnection,
    connect,
    convert_schema,
    discover_tools,
    execute_mcp_tool,
    register_mcp_tools,
    reset_mcp_connections,
)


@pytest.fixture(autouse=True)
def _reset_connections() -> None:
    reset_mcp_connections()
    yield
    reset_mcp_connections()


def test_connect_server_http_transport() -> None:
    connection = connect({"name": "github", "transport": "http", "url": "http://localhost:9000"})
    assert connection.name == "github"
    assert connection.transport == "http"
    assert connection.url == "http://localhost:9000"


def test_connect_rejects_duplicate_server_name() -> None:
    connect({"name": "github", "transport": "http", "url": "http://localhost:9000"})
    with pytest.raises(MCPConnectionError, match="already connected"):
        connect({"name": "github", "transport": "stdio", "command": "github-mcp"})


def test_discover_tools_from_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = connect({"name": "test", "transport": "http", "url": "http://localhost:9000"})

    def fake_rpc_request(_self: MCPServerConnection, _request: dict[str, object]) -> dict[str, object]:
        return {
            "result": {
                "tools": [
                    {
                        "name": "scan",
                        "description": "Run scan",
                        "parameters": {
                            "type": "object",
                            "properties": {"target": {"type": "string"}},
                            "required": ["target"],
                            "additionalProperties": False,
                        },
                    }
                ]
            }
        }

    monkeypatch.setattr(MCPServerConnection, "_rpc_request_sync", fake_rpc_request)
    discovered = discover_tools(connection)
    assert len(discovered) == 1
    assert discovered[0]["name"] == "scan"


def test_convert_schema_to_tool_schema() -> None:
    schema = convert_schema(
        "nmap",
        {
            "name": "scan",
            "description": "Run nmap scan",
            "parameters": {
                "type": "object",
                "properties": {"target": {"type": "string"}},
                "required": ["target"],
                "additionalProperties": False,
            },
        },
    )
    assert schema.name == "mcp.nmap.scan"
    assert schema.namespace == "mcp.nmap"
    assert schema.parameter_schema["type"] == "object"
    assert schema.executor_binding.route == "mcp:nmap"


async def test_register_and_dispatch_execution_through_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect({"name": "test", "transport": "stdio", "command": "mock-mcp"})

    async def fake_execute_tool(
        _self: MCPServerConnection,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        return {
            "success": True,
            "output": f"echo:{tool_name}",
            "data": {"message": arguments.get("message")},
        }

    monkeypatch.setattr(MCPServerConnection, "execute_tool", fake_execute_tool)

    registry = ToolRegistry()
    registered = register_mcp_tools(
        "test",
        [
            {
                "name": "echo",
                "description": "Echo input",
                "parameters": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            }
        ],
        registry,
    )
    assert len(registered) == 1
    assert registry.get("mcp.test.echo") is not None

    result = await registry.execute(
        ToolExecutionPlan(tool_name="mcp.test.echo", arguments={"message": "hello"})
    )
    assert result.success is True
    assert result.data["message"] == "hello"
    assert result.metadata["server"] == "test"
    assert result.metadata["tool"] == "echo"


def test_namespace_collision_protection() -> None:
    connect({"name": "test", "transport": "stdio", "command": "mock-mcp"})

    registry = ToolRegistry()
    register_mcp_tools(
        "test",
        [
            {
                "name": "echo",
                "description": "Echo input",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
        ],
        registry,
    )
    with pytest.raises(MCPSchemaError, match="namespace collision"):
        register_mcp_tools(
            "test",
            [
                {
                    "name": "echo2",
                    "description": "Echo input 2",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                }
            ],
            registry,
        )


async def test_structured_error_propagation(monkeypatch: pytest.MonkeyPatch) -> None:
    connect({"name": "test", "transport": "stdio", "command": "mock-mcp"})

    async def fake_execute_tool(
        _self: MCPServerConnection,
        _tool_name: str,
        _arguments: dict[str, object],
    ) -> dict[str, object]:
        return {"error": {"message": "remote failure", "code": 42}}

    monkeypatch.setattr(MCPServerConnection, "execute_tool", fake_execute_tool)
    with pytest.raises(MCPExecutionError, match="remote failure") as exc_info:
        await execute_mcp_tool("test", "echo", {"message": "boom"})
    assert exc_info.value.code == 42


def test_invalid_parameter_schema_rejected() -> None:
    with pytest.raises(MCPSchemaError, match="type must be 'object'"):
        convert_schema(
            "github",
            {
                "name": "search_code",
                "description": "Search code",
                "parameters": {"type": "array"},
            },
        )


def test_transport_compatibility_guard() -> None:
    with pytest.raises(MCPConnectionError, match="unsupported"):
        connect({"name": "github", "transport": "grpc", "url": "http://localhost:9000"})


async def test_file_write_hook_compatibility(monkeypatch: pytest.MonkeyPatch) -> None:
    connect({"name": "test", "transport": "stdio", "command": "mock-mcp"})

    async def fake_execute_tool(
        _self: MCPServerConnection,
        _tool_name: str,
        _arguments: dict[str, object],
    ) -> dict[str, object]:
        return {
            "success": True,
            "metadata": {
                "file_writes": [
                    {"path": "notes.txt", "action": "write", "content": "hello"},
                ]
            },
        }

    monkeypatch.setattr(MCPServerConnection, "execute_tool", fake_execute_tool)

    events: list[HookEvent] = []

    @dataclass
    class _DispatchResult:
        continue_pipeline: bool = True

    async def hook_dispatch(event: HookEvent, _payload: dict[str, object]) -> _DispatchResult:
        events.append(event)
        return _DispatchResult(continue_pipeline=True)

    @dataclass
    class _Session:
        id: str

    await execute_mcp_tool(
        "test",
        "echo",
        {"message": "hello"},
        context={"hook_dispatch": hook_dispatch, "session": _Session(id="s1"), "turn_id": 1},
    )
    assert events == [HookEvent.PRE_FILE_WRITE, HookEvent.POST_FILE_WRITE]


async def test_mock_echo_server_registration_and_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock MCP server exposes mcp.test.echo and executes via ToolRegistry."""
    connect({"name": "test", "transport": "stdio", "command": "mock-mcp"})

    async def fake_execute_tool(
        _self: MCPServerConnection,
        _tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        message = str(arguments.get("message", ""))
        return {"success": True, "data": {"message": message}, "output": message}

    monkeypatch.setattr(MCPServerConnection, "execute_tool", fake_execute_tool)

    registry = ToolRegistry()
    register_mcp_tools(
        "test",
        [
            {
                "name": "echo",
                "description": "Echo tool",
                "parameters": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            }
        ],
        registry,
    )

    result = await registry.execute(
        ToolExecutionPlan(tool_name="mcp.test.echo", arguments={"message": "hello"})
    )
    assert result.success is True
    assert result.output == "hello"
    assert result.data["message"] == "hello"
