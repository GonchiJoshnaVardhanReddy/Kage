"""Tool installation verification utilities."""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from typing import TypedDict

from kage.core.intent import SECURITY_TOOLS
from kage.security.tool_graph import get_tools_for_stage


class ToolCheckResult(TypedDict):
    """Structured result for tool installation checks."""

    installed: bool
    path: str | None


def check_tool_installed(tool_name: str) -> ToolCheckResult:
    """Check whether a tool is installed and return its path if available."""
    normalized = tool_name.strip().lower()
    tool_path = shutil.which(normalized) if normalized else None
    return {
        "installed": tool_path is not None,
        "path": tool_path,
    }


def get_install_suggestion(tool_name: str) -> str:
    """Return a suggested install command for a missing tool."""
    return f"sudo apt install {tool_name.strip().lower()}"


def detect_installed_security_tools(tools: Iterable[str] | None = None) -> list[str]:
    """Detect installed security tools from PATH."""
    if tools is None:
        candidates = set(SECURITY_TOOLS)
        for stage in (
            "reconnaissance",
            "web_enumeration",
            "vulnerability_scanning",
            "sql_injection_testing",
            "password_attacks",
            "exploitation",
            "post_exploitation",
        ):
            candidates.update(get_tools_for_stage(stage))
    else:
        candidates = {tool.strip().lower() for tool in tools if tool.strip()}

    installed = [tool for tool in sorted(candidates) if check_tool_installed(tool)["installed"]]
    return installed

