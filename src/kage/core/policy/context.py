"""Policy evaluation context models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class PolicyContext:
    """Runtime context evaluated by policy rules."""

    tool_name: str
    execution_phase: str
    agent_name: str | None = None
    session_id: str | None = None
    session_metadata: dict[str, Any] = field(default_factory=dict)
    filesystem_path: str | None = None
    network_target: str | None = None
    plugin_source: str | None = None
    mcp_server: str | None = None
    workspace_root: Path | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    tool_tags: list[str] = field(default_factory=list)
    tool_scopes: list[str] = field(default_factory=list)
    dangerous: bool = False
    requires_approval: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

