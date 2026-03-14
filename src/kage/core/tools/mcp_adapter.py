"""MCP adapter for schema-driven ToolRegistry integration."""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from inspect import isawaitable
from typing import Any

import httpx

from kage.core.hooks import HookEvent
from kage.core.tools.models import (
    ToolExecutionPlan,
    ToolExecutionResult,
    ToolExecutorBinding,
    ToolExecutorKind,
    ToolPermissionMetadata,
    ToolSchema,
)
from kage.core.tools.registry import ToolRegistry

_SERVER_SEGMENT_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_TOOL_SEGMENT_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_SUPPORTED_TRANSPORTS = {"stdio", "http", "sse"}


class MCPAdapterError(Exception):
    """Base MCP adapter error."""


class MCPConnectionError(MCPAdapterError):
    """Raised when an MCP server connection is invalid or unavailable."""


class MCPDiscoveryError(MCPAdapterError):
    """Raised when MCP tool discovery fails."""


class MCPSchemaError(MCPAdapterError):
    """Raised when MCP tool schema translation/registration fails."""


class MCPExecutionError(MCPAdapterError):
    """Raised when MCP tool execution fails."""

    def __init__(
        self,
        message: str,
        *,
        code: str | int | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details) if details is not None else {}


@dataclass(slots=True)
class MCPServerConnection:
    """Normalized MCP server connection metadata."""

    name: str
    transport: str
    timeout_s: float
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    env: dict[str, str] = field(default_factory=dict)

    def discover_tools(self) -> list[dict[str, Any]]:
        """Discover tools exposed by this MCP server."""
        payload = self._rpc_request_sync({"method": "tools/list", "params": {}})
        result = _extract_rpc_result(payload, operation="discover")
        tools = _extract_tool_list(result)
        return tools

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Execute one MCP tool through this connection."""
        payload = await self._rpc_request_async(
            {
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            }
        )
        return _extract_rpc_result(payload, operation="execute")

    def _rpc_request_sync(self, request_payload: dict[str, Any]) -> Any:
        if self.transport == "stdio":
            return self._stdio_request_sync(request_payload)
        if self.transport == "http":
            return self._http_request_sync(request_payload)
        if self.transport == "sse":
            raise MCPConnectionError(
                f"MCP transport 'sse' is not implemented for server '{self.name}'"
            )
        raise MCPConnectionError(
            f"Unsupported MCP transport '{self.transport}' for server '{self.name}'"
        )

    async def _rpc_request_async(self, request_payload: dict[str, Any]) -> Any:
        if self.transport == "stdio":
            return await asyncio.to_thread(self._stdio_request_sync, request_payload)
        if self.transport == "http":
            return await self._http_request_async(request_payload)
        if self.transport == "sse":
            raise MCPConnectionError(
                f"MCP transport 'sse' is not implemented for server '{self.name}'"
            )
        raise MCPConnectionError(
            f"Unsupported MCP transport '{self.transport}' for server '{self.name}'"
        )

    def _stdio_request_sync(self, request_payload: dict[str, Any]) -> Any:
        if not self.command:
            raise MCPConnectionError(f"MCP stdio server '{self.name}' requires 'command'")
        try:
            completed = subprocess.run(
                [self.command, *self.args],
                input=json.dumps(request_payload),
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
                env=(self.env if self.env else None),
            )
        except FileNotFoundError as exc:
            raise MCPConnectionError(
                f"MCP stdio command not found for server '{self.name}': {self.command}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise MCPConnectionError(
                f"MCP stdio request timed out for server '{self.name}' after {self.timeout_s}s"
            ) from exc

        if completed.returncode != 0:
            stderr_preview = (completed.stderr or "").strip()[:500]
            raise MCPConnectionError(
                f"MCP stdio server '{self.name}' returned non-zero exit status "
                f"{completed.returncode}: {stderr_preview}"
            )

        stdout = (completed.stdout or "").strip()
        if not stdout:
            raise MCPConnectionError(f"MCP stdio server '{self.name}' returned empty response")

        return _parse_json_payload(stdout, server_name=self.name)

    def _http_request_sync(self, request_payload: dict[str, Any]) -> Any:
        if not self.url:
            raise MCPConnectionError(f"MCP http server '{self.name}' requires 'url'")
        try:
            response = httpx.post(self.url, json=request_payload, timeout=self.timeout_s)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise MCPConnectionError(
                f"MCP http request failed for server '{self.name}': {exc}"
            ) from exc
        except ValueError as exc:
            raise MCPConnectionError(
                f"MCP http server '{self.name}' returned invalid JSON"
            ) from exc

    async def _http_request_async(self, request_payload: dict[str, Any]) -> Any:
        if not self.url:
            raise MCPConnectionError(f"MCP http server '{self.name}' requires 'url'")
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.post(self.url, json=request_payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise MCPConnectionError(
                f"MCP http request failed for server '{self.name}': {exc}"
            ) from exc
        except ValueError as exc:
            raise MCPConnectionError(
                f"MCP http server '{self.name}' returned invalid JSON"
            ) from exc


_MCP_CONNECTIONS: dict[str, MCPServerConnection] = {}
_RUNTIME_CONTEXT_PROVIDER: Callable[[], dict[str, Any]] | None = None


def _read_config_value(server_config: Any, key: str) -> Any:
    if isinstance(server_config, Mapping):
        return server_config.get(key)
    return getattr(server_config, key, None)


def _validate_segment(value: str, *, kind: str, pattern: re.Pattern[str]) -> str:
    if not pattern.match(value):
        raise MCPSchemaError(f"Invalid MCP {kind}: '{value}'")
    return value


def _validate_segment_for_connection(
    value: str,
    *,
    kind: str,
    pattern: re.Pattern[str],
) -> str:
    if not pattern.match(value):
        raise MCPConnectionError(f"Invalid MCP {kind}: '{value}'")
    return value


def _normalize_parameter_schema(raw_schema: Any, *, server_name: str, tool_name: str) -> dict[str, Any]:
    if raw_schema is None:
        raw_schema = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    if not isinstance(raw_schema, dict):
        raise MCPSchemaError(
            f"Invalid parameter schema for mcp.{server_name}.{tool_name}: expected object schema"
        )

    schema = dict(raw_schema)
    schema_type = schema.get("type")
    if schema_type not in (None, "object"):
        raise MCPSchemaError(
            f"Invalid parameter schema for mcp.{server_name}.{tool_name}: type must be 'object'"
        )
    schema["type"] = "object"

    properties = schema.get("properties")
    if properties is None:
        properties = {}
    if not isinstance(properties, dict):
        raise MCPSchemaError(
            f"Invalid parameter schema for mcp.{server_name}.{tool_name}: properties must be an object"
        )
    schema["properties"] = properties

    required = schema.get("required")
    if required is None:
        required = []
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        raise MCPSchemaError(
            f"Invalid parameter schema for mcp.{server_name}.{tool_name}: required must be string[]"
        )
    schema["required"] = required
    return schema


def _parse_json_payload(raw_output: str, *, server_name: str) -> Any:
    lines = [line.strip() for line in raw_output.splitlines() if line.strip()]
    if not lines:
        raise MCPConnectionError(f"MCP server '{server_name}' produced no JSON output")
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise MCPConnectionError(
            f"MCP server '{server_name}' produced non-JSON output: {lines[-1][:160]}"
        ) from exc


def _extract_rpc_result(payload: Any, *, operation: str) -> Any:
    if not isinstance(payload, dict):
        return payload
    error = payload.get("error")
    if isinstance(error, dict):
        message_raw = error.get("message")
        message = str(message_raw) if isinstance(message_raw, str) else f"MCP {operation} failed"
        raise MCPExecutionError(message, code=error.get("code"), details=error)
    if isinstance(error, str):
        raise MCPExecutionError(error)
    if "result" in payload:
        return payload["result"]
    return payload


def _extract_tool_list(payload: Any) -> list[dict[str, Any]]:
    tools = payload.get("tools") if isinstance(payload, dict) else payload
    if not isinstance(tools, list):
        raise MCPDiscoveryError("MCP discovery payload must include a tools array")
    normalized: list[dict[str, Any]] = []
    for item in tools:
        if isinstance(item, dict):
            normalized.append(item)
        else:
            raise MCPDiscoveryError("MCP discovery returned a non-object tool definition")
    return normalized


async def _dispatch_file_hooks(
    *,
    context: dict[str, Any] | None,
    server_name: str,
    tool_name: str,
    result: ToolExecutionResult,
) -> None:
    if context is None:
        return
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    writes = metadata.get("file_writes")
    if not isinstance(writes, list):
        return

    hook_dispatch = context.get("hook_dispatch")
    if not callable(hook_dispatch):
        return

    session = context.get("session")
    session_id = getattr(session, "id", "")
    turn_id = context.get("turn_id", 0)
    if not isinstance(turn_id, int):
        turn_id = 0

    for write in writes:
        if not isinstance(write, dict):
            continue
        path = write.get("path")
        if not isinstance(path, str) or not path:
            continue
        action_raw = write.get("action")
        action = str(action_raw) if isinstance(action_raw, str) else "write"
        content_raw = write.get("content")
        content = str(content_raw) if isinstance(content_raw, str) else ""
        byte_count = len(content.encode("utf-8"))

        pre_result = hook_dispatch(
            HookEvent.PRE_FILE_WRITE,
            {
                "session_id": session_id,
                "turn_id": turn_id,
                "path": path,
                "action": action,
                "content": content,
                "byte_count": byte_count,
                "metadata": {
                    "tool_name": f"mcp.{server_name}.{tool_name}",
                    "server": server_name,
                },
            },
        )
        if isawaitable(pre_result):
            pre_result = await pre_result
        continue_pipeline = True
        if isinstance(pre_result, dict):
            continue_pipeline = bool(pre_result.get("continue_pipeline", True))
        else:
            continue_pipeline = bool(getattr(pre_result, "continue_pipeline", True))
        if continue_pipeline is False:
            continue

        post_result = hook_dispatch(
            HookEvent.POST_FILE_WRITE,
            {
                "session_id": session_id,
                "turn_id": turn_id,
                "path": path,
                "action": action,
                "bytes_written": byte_count,
                "metadata": {
                    "tool_name": f"mcp.{server_name}.{tool_name}",
                    "server": server_name,
                },
            },
        )
        if isawaitable(post_result):
            await post_result


def configure_runtime_context_provider(provider: Callable[[], dict[str, Any]] | None) -> None:
    """Configure lazy runtime context provider for MCP execution hooks."""
    global _RUNTIME_CONTEXT_PROVIDER
    _RUNTIME_CONTEXT_PROVIDER = provider


def _merge_runtime_context(context: dict[str, Any] | None) -> dict[str, Any] | None:
    if context is not None:
        return context
    if _RUNTIME_CONTEXT_PROVIDER is None:
        return None
    resolved = _RUNTIME_CONTEXT_PROVIDER()
    if not isinstance(resolved, dict):
        return None
    return resolved


def connect(server_config: Any) -> MCPServerConnection:
    """Connect to one MCP server configuration and cache the connection."""
    name_raw = _read_config_value(server_config, "name")
    transport_raw = _read_config_value(server_config, "transport")
    timeout_raw = _read_config_value(server_config, "timeout")
    command_raw = _read_config_value(server_config, "command")
    args_raw = _read_config_value(server_config, "args")
    url_raw = _read_config_value(server_config, "url")
    env_raw = _read_config_value(server_config, "env")

    if not isinstance(name_raw, str) or not name_raw:
        raise MCPConnectionError("MCP server config requires non-empty string field: name")
    if not isinstance(transport_raw, str) or not transport_raw:
        raise MCPConnectionError(f"MCP server '{name_raw}' requires non-empty string field: transport")

    name = _validate_segment_for_connection(
        name_raw.strip(),
        kind="server name",
        pattern=_SERVER_SEGMENT_RE,
    )
    transport = transport_raw.strip().lower()
    if transport not in _SUPPORTED_TRANSPORTS:
        raise MCPConnectionError(
            f"MCP server '{name}' transport '{transport}' is unsupported "
            f"(supported: {', '.join(sorted(_SUPPORTED_TRANSPORTS))})"
        )

    timeout_s = float(timeout_raw) if isinstance(timeout_raw, (int, float)) else 30.0
    if timeout_s <= 0:
        raise MCPConnectionError(f"MCP server '{name}' timeout must be greater than zero")

    command = command_raw.strip() if isinstance(command_raw, str) and command_raw.strip() else None
    args = [str(item) for item in args_raw] if isinstance(args_raw, list) else []
    url = url_raw.strip() if isinstance(url_raw, str) and url_raw.strip() else None
    env = dict(env_raw) if isinstance(env_raw, dict) else {}

    if transport == "stdio" and command is None:
        raise MCPConnectionError(f"MCP stdio server '{name}' requires command")
    if transport in {"http", "sse"} and url is None:
        raise MCPConnectionError(f"MCP {transport} server '{name}' requires url")

    if name in _MCP_CONNECTIONS:
        raise MCPConnectionError(f"MCP server name already connected: {name}")

    connection = MCPServerConnection(
        name=name,
        transport=transport,
        timeout_s=timeout_s,
        command=command,
        args=args,
        url=url,
        env=env,
    )
    _MCP_CONNECTIONS[name] = connection
    return connection


def discover_tools(server_connection: MCPServerConnection) -> list[dict[str, Any]]:
    """Discover remote MCP tools for one server connection."""
    return server_connection.discover_tools()


def convert_schema(server_name: str, tool_definition: Mapping[str, Any]) -> ToolSchema:
    """Convert one MCP remote schema into ToolSchema."""
    server = _validate_segment(server_name, kind="server name", pattern=_SERVER_SEGMENT_RE)
    name_raw = tool_definition.get("name")
    if not isinstance(name_raw, str) or not name_raw.strip():
        raise MCPSchemaError(f"MCP tool from server '{server}' requires a non-empty name")
    remote_tool = _validate_segment(name_raw.strip(), kind="tool name", pattern=_TOOL_SEGMENT_RE)

    description_raw = tool_definition.get("description")
    description = (
        description_raw.strip()
        if isinstance(description_raw, str) and description_raw.strip()
        else f"MCP tool '{remote_tool}' from server '{server}'"
    )
    parameter_schema = _normalize_parameter_schema(
        tool_definition.get("parameters", tool_definition.get("inputSchema")),
        server_name=server,
        tool_name=remote_tool,
    )

    dangerous = bool(tool_definition.get("dangerous", False))
    requires_approval = bool(tool_definition.get("requires_approval", dangerous))

    async def _wrapped_mcp_executor(
        plan: ToolExecutionPlan,
        context: dict[str, Any],
    ) -> ToolExecutionResult:
        return await execute_mcp_tool(server, remote_tool, plan.arguments, context=context)

    return ToolSchema(
        name=f"mcp.{server}.{remote_tool}",
        description=description,
        parameter_schema=parameter_schema,
        executor_binding=ToolExecutorBinding(
            kind=ToolExecutorKind.MCP,
            route=f"mcp:{server}",
            executor=_wrapped_mcp_executor,
        ),
        permissions=ToolPermissionMetadata(
            dangerous=dangerous,
            requires_approval=requires_approval,
            scopes=["mcp", server],
            tags=["mcp", server],
        ),
        namespace=f"mcp.{server}",
        metadata={
            "server": server,
            "remote_tool": remote_tool,
            "transport": (
                _MCP_CONNECTIONS[server].transport if server in _MCP_CONNECTIONS else None
            ),
        },
    )


def register_mcp_tools(
    server_name: str,
    tool_definitions: Sequence[Mapping[str, Any]],
    registry: ToolRegistry,
) -> list[ToolSchema]:
    """Register discovered MCP tools into ToolRegistry."""
    server = _validate_segment(server_name, kind="server name", pattern=_SERVER_SEGMENT_RE)
    if server not in _MCP_CONNECTIONS:
        raise MCPConnectionError(f"MCP server '{server}' is not connected")

    if any(tool.name.startswith(f"mcp.{server}.") for tool in registry.list()):
        raise MCPSchemaError(f"MCP namespace collision: server '{server}' already has registered tools")

    converted: list[ToolSchema] = []
    seen_tool_names: set[str] = set()
    for definition in tool_definitions:
        schema = convert_schema(server, definition)
        if schema.name in seen_tool_names:
            raise MCPSchemaError(f"MCP tool schema conflict from server '{server}': {schema.name}")
        seen_tool_names.add(schema.name)
        if registry.get(schema.name) is not None:
            raise MCPSchemaError(f"MCP tool namespace conflict: {schema.name} already exists")
        converted.append(schema)

    for schema in converted:
        registry.register(schema)
    return converted


async def execute(
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> ToolExecutionResult:
    """Execute one MCP tool by server/tool name."""
    return await execute_mcp_tool(server_name, tool_name, arguments)


async def execute_mcp_tool(
    server: str,
    tool: str,
    arguments: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> ToolExecutionResult:
    """Execute one MCP tool and normalize into ToolExecutionResult."""
    _validate_segment(server, kind="server name", pattern=_SERVER_SEGMENT_RE)
    _validate_segment(tool, kind="tool name", pattern=_TOOL_SEGMENT_RE)
    if not isinstance(arguments, dict):
        raise MCPExecutionError("MCP tool arguments must be an object")

    connection = _MCP_CONNECTIONS.get(server)
    if connection is None:
        raise MCPConnectionError(f"MCP server '{server}' is not connected")

    raw_result = await connection.execute_tool(tool, arguments)

    if isinstance(raw_result, dict):
        nested_error = raw_result.get("error")
        if isinstance(nested_error, dict):
            message_raw = nested_error.get("message")
            message = (
                message_raw
                if isinstance(message_raw, str) and message_raw.strip()
                else f"MCP tool execution failed: mcp.{server}.{tool}"
            )
            raise MCPExecutionError(
                message,
                code=nested_error.get("code"),
                details=nested_error,
            )
        if isinstance(nested_error, str):
            raise MCPExecutionError(nested_error)

    result = await ToolExecutionResult.normalize(raw_result)
    if not result.metadata:
        result.metadata = {}
    result.metadata.setdefault("server", server)
    result.metadata.setdefault("tool", tool)
    result.metadata.setdefault("namespace", f"mcp.{server}")
    merged_context = _merge_runtime_context(context)
    await _dispatch_file_hooks(
        context=merged_context,
        server_name=server,
        tool_name=tool,
        result=result,
    )
    return result


def reset_mcp_connections() -> None:
    """Clear in-memory MCP connection cache (used by tests/runtime reinit)."""
    _MCP_CONNECTIONS.clear()
    configure_runtime_context_provider(None)

