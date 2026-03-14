"""Kali MCP executor for Kage.

Executes security commands on remote Kali Linux instances
via MCP (Model Context Protocol) servers. Supports multiple
servers with automatic failover.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from kage.executor.base import BaseExecutor, ExecutionResult, StreamingOutput
from kage.utils import utcnow

logger = logging.getLogger(__name__)


class KaliMCPError(Exception):
    """Error communicating with Kali MCP server."""


class KaliExecutor(BaseExecutor):
    """Execute commands on a Kali Linux instance via MCP.

    Supports multiple MCP server endpoints with automatic failover.
    If all MCP servers fail, raises KaliMCPError so the caller can
    fall back to local execution.
    """

    def __init__(
        self,
        servers: dict[str, str] | None = None,
        working_dir: str | None = None,
    ) -> None:
        """Initialize with a map of server names to URLs.

        Args:
            servers: Dict of {name: url}, e.g. {"kali_local": "http://127.0.0.1:5000"}
            working_dir: Default working directory on the remote host.
        """
        super().__init__(working_dir=working_dir)
        self._servers: dict[str, str] = servers or {}
        self._active_server: str | None = None
        self._mcp_client = None

    @property
    def environment_name(self) -> str:
        if self._active_server:
            return f"kali_mcp ({self._active_server})"
        return "kali_mcp"

    @property
    def server_count(self) -> int:
        return len(self._servers)

    def add_server(self, name: str, url: str) -> None:
        """Register an MCP server endpoint."""
        self._servers[name] = url

    def remove_server(self, name: str) -> None:
        """Remove an MCP server endpoint."""
        self._servers.pop(name, None)
        if self._active_server == name:
            self._active_server = None

    async def _try_server(self, name: str, url: str) -> bool:
        """Attempt to connect to a single MCP server."""
        try:
            from kage.mcp.client import MCPClient

            client = MCPClient.from_sse(name=name, url=url)
            await client.connect()
            self._mcp_client = client
            self._active_server = name
            logger.info("Connected to Kali MCP server: %s (%s)", name, url)
            return True
        except Exception as e:
            logger.warning("Failed to connect to Kali MCP server %s (%s): %s", name, url, e)
            return False

    async def _ensure_connection(self) -> None:
        """Ensure we have an active MCP connection, trying all servers."""
        if self._mcp_client and self._active_server:
            return

        if not self._servers:
            raise KaliMCPError("No Kali MCP servers configured")

        for name, url in self._servers.items():
            if await self._try_server(name, url):
                return

        raise KaliMCPError(
            f"Could not connect to any Kali MCP server. "
            f"Tried: {', '.join(self._servers.keys())}"
        )

    async def execute(
        self,
        command: str,
        timeout: int = 300,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,  # noqa: ARG002
    ) -> ExecutionResult:
        """Execute a command via Kali MCP with server failover."""
        started_at = utcnow()
        last_error: Exception | None = None

        # Try the active server first, then others
        server_order = list(self._servers.items())
        if self._active_server and self._active_server in self._servers:
            active_url = self._servers[self._active_server]
            server_order = [
                (self._active_server, active_url),
                *[(n, u) for n, u in self._servers.items() if n != self._active_server],
            ]

        for name, url in server_order:
            try:
                if not await self._try_server(name, url):
                    continue

                result = await self._mcp_client.call_tool(
                    name="run_command",
                    arguments={
                        "command": command,
                        "timeout": timeout,
                        "working_dir": working_dir or self.working_dir,
                    },
                )

                return ExecutionResult(
                    command=command,
                    exit_code=0 if result.success else 1,
                    stdout=result.content or "",
                    stderr=result.error or "",
                    started_at=started_at,
                    completed_at=utcnow(),
                    timed_out=False,
                    environment=self.environment_name,
                    working_dir=working_dir or self.working_dir,
                    metadata={"mcp_server": name, "mcp_url": url},
                )

            except Exception as e:
                last_error = e
                logger.warning("MCP execution failed on %s: %s", name, e)
                self._active_server = None
                self._mcp_client = None
                continue

        raise KaliMCPError(
            f"All Kali MCP servers failed. Last error: {last_error}"
        )

    async def execute_streaming(
        self,
        command: str,
        timeout: int = 300,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> AsyncIterator[StreamingOutput]:
        """Stream command output via Kali MCP.

        Falls back to non-streaming execute since MCP streaming
        support varies by server implementation.
        """
        result = await self.execute(command, timeout, working_dir, env)
        if result.stdout:
            yield StreamingOutput(text=result.stdout, stream="stdout")
        if result.stderr:
            yield StreamingOutput(text=result.stderr, stream="stderr")

    async def check_available(self) -> bool:
        """Check if any Kali MCP server is reachable."""
        if not self._servers:
            return False

        for name, url in self._servers.items():
            if await self._try_server(name, url):
                return True

        return False

    async def disconnect(self) -> None:
        """Disconnect from the active MCP server."""
        if self._mcp_client:
            import contextlib

            with contextlib.suppress(Exception):
                await self._mcp_client.disconnect()
            self._mcp_client = None
            self._active_server = None
