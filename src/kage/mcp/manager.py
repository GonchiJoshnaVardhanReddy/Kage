"""MCP Manager - handles multiple MCP server connections."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from kage.mcp.client import MCPClient, MCPError
from kage.mcp.models import MCPTool, MCPToolResult
from kage.persistence.config import MCPConfig, MCPServerConfig

logger = logging.getLogger(__name__)


class MCPManager:
    """Manages connections to multiple MCP servers."""

    def __init__(self, config: MCPConfig) -> None:
        self.config = config
        self._clients: dict[str, MCPClient] = {}
        self._docker_containers: dict[str, str] = {}  # name -> container_id
        self._tools_cache: dict[str, list[MCPTool]] = {}

    def _remove_server_tools(self, server_name: str) -> None:
        """Remove cached tools associated with a server."""
        new_cache: dict[str, list[MCPTool]] = {}
        for tool_name, tools in self._tools_cache.items():
            filtered = [tool for tool in tools if tool.server_name != server_name]
            if filtered:
                new_cache[tool_name] = filtered
        self._tools_cache = new_cache

    async def start(self) -> None:
        """Start all configured MCP servers."""
        if not self.config.enabled:
            logger.info("MCP is disabled in config")
            return

        # Auto-discover MCP servers
        if self.config.auto_discover:
            await self._discover_servers()

        # Connect to configured servers
        for server_config in self.config.servers:
            if not server_config.enabled:
                continue

            try:
                await self._connect_server(server_config)
            except Exception as e:
                logger.error(f"Failed to connect to {server_config.name}: {e}")

    async def stop(self) -> None:
        """Stop all MCP servers and clean up."""
        # Disconnect all clients
        for name, client in list(self._clients.items()):
            try:
                await client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting {name}: {e}")
            finally:
                self._remove_server_tools(name)

        self._clients.clear()

        # Stop Docker containers
        for name, container_id in list(self._docker_containers.items()):
            try:
                await self._stop_docker_container(container_id)
            except Exception as e:
                logger.error(f"Error stopping container {name}: {e}")

        self._docker_containers.clear()
        self._tools_cache.clear()

    async def _discover_servers(self) -> None:
        """Auto-discover MCP servers from known locations."""
        discovered = []

        # Check discovery paths
        for path_str in self.config.discovery_paths:
            path = Path(path_str).expanduser()
            if not path.exists():
                continue

            # Look for MCP config files
            for config_file in path.glob("*.json"):
                try:
                    import json

                    with open(config_file) as f:
                        data = json.load(f)

                    if "mcpServers" in data:
                        for name, server_data in data["mcpServers"].items():
                            server_config = MCPServerConfig(
                                name=name,
                                transport="stdio",
                                command=server_data.get("command"),
                                env=server_data.get("env", {}),
                            )
                            discovered.append(server_config)

                except Exception as e:
                    logger.debug(f"Could not parse {config_file}: {e}")

        # Check for common MCP servers
        common_servers = [
            ("filesystem", "npx", ["-y", "@modelcontextprotocol/server-filesystem", "."]),
            ("github", "npx", ["-y", "@modelcontextprotocol/server-github"]),
        ]

        for name, cmd, args in common_servers:
            if shutil.which(cmd) and not any(s.name == name for s in self.config.servers):
                discovered.append(
                    MCPServerConfig(
                        name=name,
                        transport="stdio",
                        command=f"{cmd} {' '.join(args)}",
                        auto_start=False,  # Don't auto-start discovered servers
                    )
                )

        # Add discovered servers to config (but don't overwrite existing)
        existing_names = {s.name for s in self.config.servers}
        for server in discovered:
            if server.name not in existing_names:
                self.config.servers.append(server)
                logger.info(f"Discovered MCP server: {server.name}")

    async def _connect_server(self, config: MCPServerConfig) -> MCPClient:
        """Connect to an MCP server based on its config."""
        if config.name in self._clients:
            return self._clients[config.name]

        client: MCPClient | None = None

        if config.transport == "stdio" and config.command:
            client = MCPClient.from_stdio(
                name=config.name,
                command=config.command,
                env=config.env,
            )

        elif config.transport == "sse" and config.url:
            client = MCPClient.from_sse(
                name=config.name,
                url=config.url,
            )

        elif config.transport == "docker" and config.docker_image:
            # Start Docker container first
            container_id = await self._start_docker_container(
                config.name,
                config.docker_image,
                config.env,
            )
            self._docker_containers[config.name] = container_id

            # Connect via stdio to docker exec
            client = MCPClient.from_stdio(
                name=config.name,
                command=["docker", "exec", "-i", container_id, "mcp-server"],
                env=config.env,
            )

        if not client:
            raise MCPError(f"Invalid server config for {config.name}")

        # Connect and get tools
        await client.connect()
        self._clients[config.name] = client

        # Cache tools
        for tool in client.get_tools():
            existing = self._tools_cache.setdefault(tool.name, [])
            existing.append(tool)

        logger.info(f"Connected to MCP server: {config.name} ({len(client.get_tools())} tools)")

        return client

    async def _start_docker_container(
        self,
        name: str,
        image: str,
        env: dict[str, str] | None = None,
    ) -> str:
        """Start an MCP server in a Docker container."""
        if not self.config.docker_enabled:
            raise MCPError("Docker is disabled in config")

        # Build docker run command
        cmd = ["docker", "run", "-d", "--rm", "--name", f"kage-mcp-{name}"]

        # Add environment variables
        if env:
            for key, value in env.items():
                cmd.extend(["-e", f"{key}={value}"])

        cmd.append(image)

        # Run container
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise MCPError(f"Failed to start container: {result.stderr}")

        container_id = result.stdout.strip()
        logger.info(f"Started Docker container {name}: {container_id[:12]}")

        # Wait for container to be ready
        await asyncio.sleep(2)

        return container_id

    async def _stop_docker_container(self, container_id: str) -> None:
        """Stop a Docker container."""
        subprocess.run(
            ["docker", "stop", container_id],
            capture_output=True,
            timeout=10,
        )

    def get_all_tools(self) -> list[MCPTool]:
        """Get all available tools from all connected servers."""
        return [tools[0] for tools in self._tools_cache.values() if tools]

    def get_tool(self, name: str) -> MCPTool | None:
        """Get a specific tool by name."""
        candidates = self._tools_cache.get(name, [])
        return candidates[0] if candidates else None

    def get_tools_for_llm(self) -> list[dict[str, Any]]:
        """Get tools in OpenAI function calling format."""
        return [tool.to_openai_format() for tool in self.get_all_tools()]

    def has_tool(self, name: str) -> bool:
        """Check whether any connected server provides a tool."""
        return bool(self._tools_cache.get(name))

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> MCPToolResult:
        """Call a tool on the appropriate MCP server."""
        tools = self._tools_cache.get(name, [])
        if not tools:
            return MCPToolResult(
                tool_name=name,
                success=False,
                error=f"Tool not found: {name}",
                is_error=True,
            )

        errors: list[str] = []

        # Try each server exposing this tool until one succeeds.
        for tool in tools:
            server_name = tool.server_name or ""
            client = self._clients.get(server_name)
            if not client:
                errors.append(f"{server_name}: server not connected")
                continue

            result = await client.call_tool(name, arguments)
            if result.success and not result.is_error:
                return result

            errors.append(f"{server_name}: {result.error or 'tool call failed'}")

            # Best-effort reconnect and retry once on the same server.
            if await self.reconnect(server_name):
                retry_client = self._clients.get(server_name)
                if retry_client:
                    retry_result = await retry_client.call_tool(name, arguments)
                    if retry_result.success and not retry_result.is_error:
                        return retry_result
                    errors.append(
                        f"{server_name} (retry): {retry_result.error or 'tool call failed'}"
                    )

        return MCPToolResult(
            tool_name=name,
            success=False,
            error="; ".join(errors) if errors else f"Failed to call tool: {name}",
            is_error=True,
        )

    def get_connected_servers(self) -> list[str]:
        """Get list of connected server names."""
        return list(self._clients.keys())

    def is_connected(self, server_name: str) -> bool:
        """Check if a specific server is connected."""
        client = self._clients.get(server_name)
        return client is not None and client.is_connected

    async def reconnect(self, server_name: str) -> bool:
        """Reconnect to a specific server."""
        # Find config
        config = next(
            (s for s in self.config.servers if s.name == server_name),
            None,
        )
        if not config:
            return False

        # Disconnect if connected
        if server_name in self._clients:
            import contextlib

            with contextlib.suppress(Exception):
                await self._clients[server_name].disconnect()
            del self._clients[server_name]
            self._remove_server_tools(server_name)

        # Reconnect
        try:
            await self._connect_server(config)
            return True
        except Exception as e:
            logger.error(f"Failed to reconnect to {server_name}: {e}")
            return False

    async def __aenter__(self) -> MCPManager:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()
