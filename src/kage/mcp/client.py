"""MCP client implementation for stdio and SSE transports."""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

import httpx

from kage.mcp.models import MCPServerInfo, MCPTool, MCPToolResult

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """MCP-related error."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class MCPTransport(ABC):
    """Abstract base class for MCP transports."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""
        ...

    @abstractmethod
    async def send(self, message: dict[str, Any]) -> dict[str, Any]:
        """Send a request and wait for response."""
        ...

    @abstractmethod
    async def receive_notifications(self) -> AsyncIterator[dict[str, Any]]:
        """Receive server notifications."""
        ...


class StdioTransport(MCPTransport):
    """MCP transport over stdio (subprocess)."""

    def __init__(self, command: str | list[str], env: dict[str, str] | None = None) -> None:
        self.command = command if isinstance(command, list) else command.split()
        self.env = env or {}
        self._process: subprocess.Popen | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Start the subprocess."""
        import os

        full_env = {**os.environ, **self.env}

        self._process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=full_env,
            bufsize=0,
        )

        # Start reader task
        self._reader_task = asyncio.create_task(self._read_loop())

    async def disconnect(self) -> None:
        """Stop the subprocess."""
        import contextlib

        if self._reader_task:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task

        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    async def _read_loop(self) -> None:
        """Read responses from stdout."""
        if not self._process or not self._process.stdout:
            return

        loop = asyncio.get_event_loop()

        while True:
            try:
                line = await loop.run_in_executor(None, self._process.stdout.readline)
                if not line:
                    break

                try:
                    message = json.loads(line.decode())
                except json.JSONDecodeError:
                    continue

                # Handle response
                if "id" in message and message["id"] in self._pending:
                    future = self._pending.pop(message["id"])
                    if not future.done():
                        future.set_result(message)

            except Exception as e:
                logger.error(f"Error reading from MCP server: {e}")
                break

    async def send(self, message: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request."""
        if not self._process or not self._process.stdin:
            raise MCPError("Not connected")

        async with self._lock:
            self._request_id += 1
            request_id = self._request_id

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            **message,
        }

        # Create future for response
        future: asyncio.Future = asyncio.Future()
        self._pending[request_id] = future

        # Send request
        data = json.dumps(request) + "\n"
        self._process.stdin.write(data.encode())
        self._process.stdin.flush()

        # Wait for response with timeout
        try:
            response = await asyncio.wait_for(future, timeout=30)
        except asyncio.TimeoutError as e:
            self._pending.pop(request_id, None)
            raise MCPError("Request timed out") from e

        if "error" in response:
            error = response["error"]
            raise MCPError(error.get("message", "Unknown error"), error.get("code"))

        return response.get("result", {})

    async def receive_notifications(self) -> AsyncIterator[dict[str, Any]]:
        """Not implemented for stdio - notifications handled in read loop."""
        return
        yield  # Make this a generator


class SSETransport(MCPTransport):
    """MCP transport over Server-Sent Events (HTTP)."""

    def __init__(self, url: str, headers: dict[str, str] | None = None) -> None:
        self.url = url.rstrip("/")
        self.headers = headers or {}
        self._client: httpx.AsyncClient | None = None
        self._session_id: str | None = None

    async def connect(self) -> None:
        """Connect to SSE endpoint."""
        self._client = httpx.AsyncClient(
            headers=self.headers,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    async def disconnect(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def send(self, message: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request via HTTP POST."""
        if not self._client:
            raise MCPError("Not connected")

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            **message,
        }

        try:
            response = await self._client.post(
                f"{self.url}/message",
                json=request,
            )
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                error = data["error"]
                raise MCPError(error.get("message", "Unknown error"), error.get("code"))

            return data.get("result", {})

        except httpx.HTTPError as e:
            raise MCPError(f"HTTP error: {e}") from e

    async def receive_notifications(self) -> AsyncIterator[dict[str, Any]]:
        """Stream notifications from SSE endpoint."""
        if not self._client:
            return

        try:
            async with self._client.stream("GET", f"{self.url}/sse") as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            yield data
                        except json.JSONDecodeError:
                            continue
        except httpx.HTTPError:
            return


class MCPClient:
    """Client for communicating with MCP servers."""

    def __init__(
        self,
        name: str,
        transport: MCPTransport,
    ) -> None:
        self.name = name
        self.transport = transport
        self.server_info: MCPServerInfo | None = None
        self._tools: dict[str, MCPTool] = {}
        self._connected = False

    @classmethod
    def from_stdio(
        cls,
        name: str,
        command: str | list[str],
        env: dict[str, str] | None = None,
    ) -> MCPClient:
        """Create a client using stdio transport."""
        transport = StdioTransport(command, env)
        return cls(name, transport)

    @classmethod
    def from_sse(
        cls,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> MCPClient:
        """Create a client using SSE transport."""
        transport = SSETransport(url, headers)
        return cls(name, transport)

    async def connect(self) -> MCPServerInfo:
        """Connect to the MCP server and initialize."""
        await self.transport.connect()

        # Initialize connection
        result = await self.transport.send(
            {
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                    },
                    "clientInfo": {
                        "name": "kage",
                        "version": "0.1.0",
                    },
                },
            }
        )

        self.server_info = MCPServerInfo(
            name=result.get("serverInfo", {}).get("name", self.name),
            version=result.get("serverInfo", {}).get("version"),
            protocol_version=result.get("protocolVersion", "2024-11-05"),
            capabilities=result.get("capabilities", {}),
        )

        # Send initialized notification
        await self.transport.send(
            {
                "method": "notifications/initialized",
            }
        )

        self._connected = True

        # Fetch available tools
        await self.refresh_tools()

        return self.server_info

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        self._connected = False
        await self.transport.disconnect()

    async def refresh_tools(self) -> list[MCPTool]:
        """Fetch available tools from the server."""
        if not self._connected:
            raise MCPError("Not connected")

        result = await self.transport.send(
            {
                "method": "tools/list",
            }
        )

        self._tools = {}
        tools = []

        for tool_data in result.get("tools", []):
            tool = MCPTool(
                name=tool_data["name"],
                description=tool_data.get("description", ""),
                input_schema=tool_data.get("inputSchema", {}),
                server_name=self.name,
            )
            self._tools[tool.name] = tool
            tools.append(tool)

        if self.server_info:
            self.server_info.tools = tools

        return tools

    def get_tools(self) -> list[MCPTool]:
        """Get cached list of tools."""
        return list(self._tools.values())

    def get_tool(self, name: str) -> MCPTool | None:
        """Get a specific tool by name."""
        return self._tools.get(name)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        """Call a tool on the MCP server."""
        if not self._connected:
            raise MCPError("Not connected")

        if name not in self._tools:
            return MCPToolResult(
                tool_name=name,
                success=False,
                error=f"Tool not found: {name}",
                is_error=True,
            )

        try:
            result = await self.transport.send(
                {
                    "method": "tools/call",
                    "params": {
                        "name": name,
                        "arguments": arguments or {},
                    },
                }
            )

            return MCPToolResult(
                tool_name=name,
                success=True,
                content=result.get("content", []),
                is_error=result.get("isError", False),
            )

        except MCPError as e:
            return MCPToolResult(
                tool_name=name,
                success=False,
                error=str(e),
                is_error=True,
            )

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected

    async def __aenter__(self) -> MCPClient:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()
