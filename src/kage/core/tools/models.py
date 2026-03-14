"""Core models for schema-based tool execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import Enum
from inspect import isawaitable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolExecutionOrigin(str, Enum):
    """Originator of a tool execution plan."""

    LLM = "llm"
    PLUGIN = "plugin"
    AGENT = "agent"
    SYSTEM = "system"


class ToolValidationStrategy(str, Enum):
    """Argument validation strategy for a tool."""

    STRICT = "strict"
    COERCE = "coerce"


class ToolExecutorKind(str, Enum):
    """Executor source for a tool."""

    BUILTIN = "builtin"
    PLUGIN = "plugin"
    MCP = "mcp"
    AGENT = "agent"
    EXTERNAL = "external"


class ToolPermissionMetadata(BaseModel):
    """Permission and policy metadata for a tool."""

    dangerous: bool = False
    requires_approval: bool = False
    scopes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


ToolExecutor = Callable[
    ["ToolExecutionPlan", dict[str, Any]],
    "ToolExecutionResult | dict[str, Any] | str | Awaitable[ToolExecutionResult | dict[str, Any] | str]",
]


class ToolExecutorBinding(BaseModel):
    """Binding metadata and runtime callable for tool execution."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    kind: ToolExecutorKind
    route: str = "local"
    executor: ToolExecutor | None = Field(default=None, exclude=True)


class ToolSchema(BaseModel):
    """Schema definition for a runtime tool."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    parameter_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    executor_binding: ToolExecutorBinding
    permissions: ToolPermissionMetadata = Field(default_factory=ToolPermissionMetadata)
    validation_strategy: ToolValidationStrategy = ToolValidationStrategy.STRICT
    namespace: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _validate_tool_name(cls, value: str) -> str:
        if "." not in value:
            raise ValueError("Tool name must be namespaced (e.g. builtin.shell.run)")
        segments = value.split(".")
        if any(not segment for segment in segments):
            raise ValueError("Tool name contains empty namespace segments")
        if any(segment.lower() != segment for segment in segments):
            raise ValueError("Tool name segments must be lowercase")
        return value

    @field_validator("parameter_schema")
    @classmethod
    def _validate_parameter_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        schema_type = value.get("type")
        if schema_type != "object":
            raise ValueError("Tool parameter schema must be a JSON object schema")
        if "properties" not in value:
            value["properties"] = {}
        if "required" not in value:
            value["required"] = []
        return value

    @field_validator("namespace")
    @classmethod
    def _validate_namespace(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            name = info.data.get("name")
            if isinstance(name, str) and "." in name:
                return ".".join(name.split(".")[:-1])
            return value
        return value


class ToolExecutionPlan(BaseModel):
    """A structured, deterministic instruction to execute one tool."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    origin: ToolExecutionOrigin = ToolExecutionOrigin.LLM
    confidence_score: float | None = None
    approval_required: bool = False
    description: str | None = None

    @field_validator("tool_name")
    @classmethod
    def _validate_tool_name(cls, value: str) -> str:
        if not value or "." not in value:
            raise ValueError("Execution plan tool_name must be namespaced")
        return value

    @field_validator("confidence_score")
    @classmethod
    def _validate_confidence(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if value < 0.0 or value > 1.0:
            raise ValueError("confidence_score must be between 0 and 1")
        return value


class ToolExecutionResult(BaseModel):
    """Result of executing one tool invocation."""

    success: bool
    output: str | None = None
    data: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    async def normalize(
        cls,
        raw_result: ToolExecutionResult | dict[str, Any] | str | Awaitable[Any],
    ) -> ToolExecutionResult:
        """Normalize arbitrary executor output into ToolExecutionResult."""
        resolved = raw_result
        if isawaitable(resolved):
            resolved = await resolved
        if isinstance(resolved, ToolExecutionResult):
            return resolved
        if isinstance(resolved, dict):
            return ToolExecutionResult(**resolved)
        if isinstance(resolved, str):
            return ToolExecutionResult(success=True, output=resolved, data=resolved)
        return ToolExecutionResult(success=True, data=resolved)


class ToolRegistryError(Exception):
    """Base exception for tool registry errors."""


class ToolValidationError(ToolRegistryError):
    """Raised when tool arguments fail schema validation."""


class ToolExecutionError(ToolRegistryError):
    """Raised when tool execution fails at registry level."""

