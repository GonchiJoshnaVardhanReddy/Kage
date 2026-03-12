"""Command routing engine for Kage.

Routes commands to the appropriate executor based on tool type:
- Security tools → Kali MCP executor (with fallback)
- Development/system tools → Local executor
"""

from __future__ import annotations

import logging
import re
from enum import Enum

from pydantic import BaseModel, Field

from kage.core.intent import SECURITY_TOOLS

logger = logging.getLogger(__name__)


class ExecutorType(str, Enum):
    """Target executor for a command."""

    LOCAL = "local"
    KALI_MCP = "kali_mcp"


class RouteResult(BaseModel):
    """Result of command routing decision."""

    executor_type: ExecutorType
    tool_name: str | None = None
    reasoning: str = ""
    fallback_to_local: bool = Field(
        default=False,
        description="If True, fall back to local if MCP fails",
    )


# Tools that should ALWAYS run locally regardless of context
LOCAL_ONLY_TOOLS: set[str] = {
    "git", "python", "python3", "pip", "pip3",
    "node", "npm", "npx", "yarn", "pnpm",
    "go", "cargo", "rustc", "javac", "java", "mvn", "gradle",
    "gcc", "g++", "make", "cmake", "dotnet", "ruby", "gem",
    "docker", "docker-compose", "kubectl",
    "code", "vim", "nano", "emacs",
    "ls", "cd", "cp", "mv", "mkdir", "cat", "echo", "touch",
    "head", "tail", "wc", "sort", "uniq", "awk", "sed",
    "tar", "zip", "unzip", "gzip",
    "chmod", "chown",
    "ps", "top", "kill", "df", "du", "free",
    "curl", "wget",
    "apt", "apt-get", "yum", "dnf", "pacman", "brew",
    "systemctl", "service", "journalctl",
}


def _extract_tool_from_command(command: str) -> str | None:
    """Extract the primary tool name from a shell command."""
    command = command.strip()

    # Handle sudo prefix
    if command.startswith("sudo "):
        command = command[5:].strip()

    # Handle environment variables prefix (FOO=bar cmd)
    while re.match(r"^\w+=\S+\s", command):
        command = re.sub(r"^\w+=\S+\s+", "", command)

    # Handle pipe chains — route based on first command
    command = command.split("|")[0].strip()

    # Handle command chaining (&&, ;)
    command = re.split(r"[;&]", command)[0].strip()

    # Get the first token
    parts = command.split()
    if not parts:
        return None

    tool = parts[0]

    # Handle path-qualified commands (/usr/bin/nmap → nmap)
    if "/" in tool:
        tool = tool.rsplit("/", 1)[-1]

    return tool.lower()


class CommandRouter:
    """Routes commands to appropriate executors."""

    def __init__(
        self,
        kali_available: bool = False,
        custom_security_tools: set[str] | None = None,
    ) -> None:
        self._kali_available = kali_available
        self._security_tools = SECURITY_TOOLS.copy()
        if custom_security_tools:
            self._security_tools.update(custom_security_tools)

    @property
    def kali_available(self) -> bool:
        return self._kali_available

    @kali_available.setter
    def kali_available(self, value: bool) -> None:
        self._kali_available = value

    def route(self, command: str) -> RouteResult:
        """Determine which executor should handle this command."""
        tool = _extract_tool_from_command(command)

        if not tool:
            return RouteResult(
                executor_type=ExecutorType.LOCAL,
                reasoning="Could not parse command tool",
            )

        # Local-only tools always run locally
        if tool in LOCAL_ONLY_TOOLS:
            return RouteResult(
                executor_type=ExecutorType.LOCAL,
                tool_name=tool,
                reasoning=f"Local tool: {tool}",
            )

        # Security tools → Kali MCP (if available)
        if tool in self._security_tools:
            if self._kali_available:
                return RouteResult(
                    executor_type=ExecutorType.KALI_MCP,
                    tool_name=tool,
                    reasoning=f"Security tool: {tool} → Kali MCP",
                    fallback_to_local=True,
                )
            else:
                logger.info(
                    "Security tool '%s' would use Kali MCP but it's not available. "
                    "Running locally.",
                    tool,
                )
                return RouteResult(
                    executor_type=ExecutorType.LOCAL,
                    tool_name=tool,
                    reasoning=f"Security tool: {tool} (Kali MCP unavailable, using local)",
                )

        # Default: run locally
        return RouteResult(
            executor_type=ExecutorType.LOCAL,
            tool_name=tool,
            reasoning=f"Default routing: {tool} → local",
            fallback_to_local=False,
        )
