"""Tool schema runtime for Kage."""

from kage.core.tools.builtin import register_builtin_tools
from kage.core.tools.mcp_adapter import (
    MCPAdapterError,
    MCPConnectionError,
    MCPDiscoveryError,
    MCPExecutionError,
    MCPSchemaError,
    configure_runtime_context_provider,
    connect,
    convert_schema,
    discover_tools,
    execute,
    execute_mcp_tool,
    register_mcp_tools,
    reset_mcp_connections,
)
from kage.core.tools.models import (
    ToolExecutionError,
    ToolExecutionOrigin,
    ToolExecutionPlan,
    ToolExecutionResult,
    ToolExecutorBinding,
    ToolExecutorKind,
    ToolPermissionMetadata,
    ToolRegistryError,
    ToolSchema,
    ToolValidationError,
    ToolValidationStrategy,
)
from kage.core.tools.parser import plans_from_commands, plans_from_provider_tool_calls
from kage.core.tools.registry import ToolRegistry, ToolValidationResult

__all__ = [
    "ToolExecutionError",
    "ToolExecutionOrigin",
    "ToolExecutionPlan",
    "ToolExecutionResult",
    "ToolExecutorBinding",
    "ToolExecutorKind",
    "ToolPermissionMetadata",
    "ToolRegistry",
    "ToolRegistryError",
    "ToolSchema",
    "ToolValidationError",
    "ToolValidationResult",
    "ToolValidationStrategy",
    "MCPAdapterError",
    "MCPConnectionError",
    "MCPDiscoveryError",
    "MCPExecutionError",
    "MCPSchemaError",
    "configure_runtime_context_provider",
    "connect",
    "discover_tools",
    "convert_schema",
    "register_mcp_tools",
    "execute",
    "execute_mcp_tool",
    "reset_mcp_connections",
    "plans_from_commands",
    "plans_from_provider_tool_calls",
    "register_builtin_tools",
]

