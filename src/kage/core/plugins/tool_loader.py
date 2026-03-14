"""Plugin tool discovery and ToolRegistry registration."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, cast

from pydantic import BaseModel

from kage.core.tools import (
    ToolExecutorBinding,
    ToolExecutorKind,
    ToolPermissionMetadata,
    ToolRegistry,
    ToolRegistryError,
    ToolSchema,
)
from kage.plugins.base import BasePlugin
from kage.plugins.schema import PluginSchema, PluginToolSchema


class PluginToolLoaderError(Exception):
    """Raised when plugin tool discovery/registration fails."""


class PluginToolManifest(BaseModel):
    """Normalized manifest representation for plugin tool declarations."""

    plugin_name: str
    tool: PluginToolSchema

    @property
    def full_tool_name(self) -> str:
        return f"plugin.{self.plugin_name}.{self.tool.name}"


def _plugin_tool_executor_factory(executor: Callable[..., Any]) -> Callable[..., dict[str, Any]]:
    def _tool_executor(plan: Any, _context: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": True,
            "data": executor(**plan.arguments),
        }

    return _tool_executor


def _build_parameter_schema(parameters: dict[str, Any]) -> dict[str, Any]:
    type_map = {
        "str": "string",
        "string": "string",
        "int": "integer",
        "integer": "integer",
        "float": "number",
        "number": "number",
        "bool": "boolean",
        "boolean": "boolean",
        "dict": "object",
        "object": "object",
        "list": "array",
        "array": "array",
    }
    properties: dict[str, Any] = {}
    required: list[str] = []
    for key, value in parameters.items():
        if not isinstance(key, str) or not key:
            raise PluginToolLoaderError("Tool parameter names must be non-empty strings")

        if isinstance(value, str):
            param_type = type_map.get(value.strip().lower())
            if not param_type:
                raise PluginToolLoaderError(f"Unsupported parameter type '{value}' for '{key}'")
            properties[key] = {"type": param_type}
            required.append(key)
            continue

        if isinstance(value, dict):
            raw_type = str(value.get("type", "string")).strip().lower()
            param_type = type_map.get(raw_type)
            if not param_type:
                raise PluginToolLoaderError(f"Unsupported parameter type '{raw_type}' for '{key}'")
            descriptor: dict[str, Any] = {"type": param_type}
            description = value.get("description")
            if isinstance(description, str) and description.strip():
                descriptor["description"] = description.strip()
            if "default" in value:
                descriptor["default"] = value["default"]
            properties[key] = descriptor
            if value.get("required", True):
                required.append(key)
            continue

        raise PluginToolLoaderError(f"Invalid parameter definition for '{key}'")

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _resolve_executor(plugin: BasePlugin, manifest: PluginToolManifest) -> Callable[..., Any]:
    executor_name = manifest.tool.executor or manifest.tool.name
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", executor_name):
        raise PluginToolLoaderError(f"Invalid executor name '{executor_name}'")

    candidate_names = [executor_name]
    if not executor_name.startswith("_"):
        candidate_names.extend([f"tool_{executor_name}", f"_{executor_name}"])

    for candidate in candidate_names:
        handler = getattr(plugin, candidate, None)
        if callable(handler):
            return cast(Callable[..., Any], handler)

    raise PluginToolLoaderError(
        f"Executor '{executor_name}' not found on plugin '{manifest.plugin_name}'"
    )


def discover_plugin_tools(
    plugin: BasePlugin,
    schema: PluginSchema | None = None,
) -> list[PluginToolManifest]:
    """Discover tool declarations from plugin manifest schema."""
    resolved_schema = schema
    if resolved_schema is None:
        maybe_schema = getattr(plugin, "_manifest_schema", None)
        if isinstance(maybe_schema, PluginSchema):
            resolved_schema = maybe_schema
    if resolved_schema is None:
        raise PluginToolLoaderError(
            f"Manifest schema unavailable for plugin '{plugin.name}'. "
            "Provide schema explicitly or set plugin._manifest_schema."
        )

    if resolved_schema.name != plugin.name:
        raise PluginToolLoaderError(
            f"Plugin/schema name mismatch: plugin={plugin.name} schema={resolved_schema.name}"
        )

    manifests: list[PluginToolManifest] = []
    for declared in resolved_schema.tools:
        manifests.append(
            PluginToolManifest(
                plugin_name=plugin.name,
                tool=declared,
            )
        )
    return manifests


def validate_plugin_tool_schema(manifest: PluginToolManifest | PluginToolSchema) -> None:
    """Validate one plugin tool manifest before registration."""
    if isinstance(manifest, PluginToolSchema):
        manifest = PluginToolManifest(plugin_name="placeholder", tool=manifest)

    full_name = manifest.full_tool_name
    if not full_name.startswith("plugin.") and manifest.plugin_name != "placeholder":
        raise PluginToolLoaderError("Plugin tool names must be in plugin.* namespace")
    if manifest.plugin_name != "placeholder":
        segments = full_name.split(".")
        if len(segments) < 3:
            raise PluginToolLoaderError(f"Invalid plugin tool name: {full_name}")
        if any(not segment for segment in segments):
            raise PluginToolLoaderError(f"Invalid plugin tool name: {full_name}")
    if not manifest.tool.description.strip():
        raise PluginToolLoaderError(f"Tool '{full_name}' must have description")
    if not isinstance(manifest.tool.parameters, dict):
        raise PluginToolLoaderError(f"Tool '{full_name}' parameters must be an object")


def register_plugin_tools(
    plugin: BasePlugin,
    registry: ToolRegistry,
    *,
    schema: PluginSchema | None = None,
) -> list[ToolSchema]:
    """Register declared plugin manifest tools in ToolRegistry."""
    manifests = discover_plugin_tools(plugin, schema=schema)
    registered: list[ToolSchema] = []

    plugin_prefix = f"plugin.{plugin.name}."
    for existing in registry.list():
        if existing.name.startswith(plugin_prefix):
            raise PluginToolLoaderError(
                f"Plugin namespace collision: plugin '{plugin.name}' already has registered tools"
            )

    for manifest in manifests:
        validate_plugin_tool_schema(manifest)
        full_name = manifest.full_tool_name

        if registry.get(full_name):
            raise PluginToolLoaderError(f"Tool collision: '{full_name}' already registered")
        for existing in registry.list():
            if existing.name == full_name:
                raise PluginToolLoaderError(f"Tool collision: '{full_name}' already registered")

        executor = _resolve_executor(plugin, manifest)
        parameter_schema = _build_parameter_schema(manifest.tool.parameters)

        tool_schema = ToolSchema(
            name=full_name,
            description=manifest.tool.description,
            parameter_schema=parameter_schema,
            executor_binding=ToolExecutorBinding(
                kind=ToolExecutorKind.PLUGIN,
                route="plugin",
                executor=_plugin_tool_executor_factory(executor),
            ),
            permissions=ToolPermissionMetadata(
                dangerous=manifest.tool.dangerous,
                requires_approval=manifest.tool.requires_approval,
                scopes=["plugin", plugin.name],
                tags=["plugin", plugin.name],
            ),
            namespace=f"plugin.{plugin.name}",
            metadata={
                "plugin": plugin.name,
                "executor": manifest.tool.executor or manifest.tool.name,
                **manifest.tool.metadata,
            },
        )

        try:
            registry.register(tool_schema)
        except ToolRegistryError as exc:
            raise PluginToolLoaderError(str(exc)) from exc
        registered.append(tool_schema)

    return registered

