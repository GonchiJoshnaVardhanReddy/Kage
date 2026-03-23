"""Plugin metadata schema for Kage."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class CapabilitySchema(BaseModel):
    """Schema for a capability in plugin.yaml."""

    name: str
    description: str
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    returns: str = "string"
    dangerous: bool = False
    requires_approval: bool = True
    category: str = "general"


class PluginToolSchema(BaseModel):
    """Schema for a ToolRegistry-bound tool declared in plugin.yaml."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    executor: str | None = None
    dangerous: bool = False
    requires_approval: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Tool name cannot be empty")
        if "." in normalized:
            raise ValueError("Manifest tool name must be local (do not include namespace prefix)")
        if not re.match(r"^[a-z][a-z0-9_-]*$", normalized):
            raise ValueError("Tool name must match ^[a-z][a-z0-9_-]*$")
        return normalized


class PluginSchema(BaseModel):
    """Schema for plugin.yaml metadata."""

    name: str
    version: str
    description: str
    author: str | None = None
    category: str = "general"
    entry_point: str = "plugin.py"  # Python file containing the plugin class
    plugin_class: str = "Plugin"  # Class name to instantiate

    required_tools: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    capabilities: list[CapabilitySchema] = Field(default_factory=list)
    tools: list[PluginToolSchema] = Field(default_factory=list)
    middleware: list[str] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)

    # Sandbox settings
    allowed_imports: list[str] = Field(default_factory=list)
    network_access: bool = False
    file_access: bool = False

    @classmethod
    def from_yaml(cls, path: Path) -> PluginSchema:
        """Load plugin schema from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def to_yaml(self, path: Path) -> None:
        """Save plugin schema to YAML file."""
        with open(path, "w") as f:
            yaml.dump(self.model_dump(mode="json"), f, default_flow_style=False)


# Default allowed imports for sandboxed plugins
DEFAULT_ALLOWED_IMPORTS = [
    # Standard library - safe modules
    "re",
    "json",
    "base64",
    "hashlib",
    "datetime",
    "collections",
    "itertools",
    "functools",
    "dataclasses",
    "typing",
    "enum",
    "ipaddress",
    "urllib.parse",
    # Kage modules
    "kage.plugins.base",
    "kage.core.models",
]

# Blocked imports - never allowed
BLOCKED_IMPORTS = [
    "os",
    "sys",
    "subprocess",
    "shutil",
    "socket",
    "http",
    "urllib.request",
    "ftplib",
    "telnetlib",
    "smtplib",
    "importlib",
    "__builtins__",
    "builtins",
    "eval",
    "exec",
    "compile",
    "open",  # Block file access
    "input",
]
