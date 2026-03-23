"""Plugin manager for Kage."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kage.core.prompt import MiddlewareRegistry
from kage.core.tools import ToolRegistry
from kage.core.workflows import WorkflowRegistry, register_plugin_workflows
from kage.plugins.base import BasePlugin, Capability, PluginContext
from kage.plugins.sandbox import PluginSandbox, SandboxViolation, validate_plugin_code
from kage.plugins.schema import PluginSchema

if TYPE_CHECKING:
    from kage.core.models import Session
    from kage.core.tools import ToolSchema


class PluginLoadError(Exception):
    """Error loading a plugin."""

    pass


class PluginManager:
    """Manages plugin discovery, loading, and invocation."""

    def __init__(
        self,
        plugin_dirs: list[Path] | None = None,
        sandbox_enabled: bool = True,
        tool_registry: ToolRegistry | None = None,
        prompt_middleware_registry: MiddlewareRegistry | None = None,
        workflow_registry: WorkflowRegistry | None = None,
    ) -> None:
        self.plugin_dirs = plugin_dirs or []
        self.sandbox_enabled = sandbox_enabled
        self.tool_registry = tool_registry
        self.prompt_middleware_registry = prompt_middleware_registry
        self.workflow_registry = workflow_registry
        self._plugins: dict[str, BasePlugin] = {}
        self._capabilities: dict[
            str, tuple[str, Capability]
        ] = {}  # cap_name -> (plugin_name, capability)
        self._registered_tools: dict[str, list[str]] = {}
        self._plugin_schemas: dict[str, PluginSchema] = {}
        self._plugin_dirs_by_name: dict[str, Path] = {}
        self._sandbox = PluginSandbox() if sandbox_enabled else None

    def add_plugin_dir(self, path: Path) -> None:
        """Add a plugin directory."""
        if path.exists() and path not in self.plugin_dirs:
            self.plugin_dirs.append(path)

    def discover_plugins(self) -> list[tuple[Path, PluginSchema]]:
        """Discover available plugins in plugin directories.

        Returns:
            List of (plugin_dir, schema) tuples
        """
        discovered = []

        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                continue

            for subdir in plugin_dir.iterdir():
                if not subdir.is_dir():
                    continue

                yaml_path = subdir / "plugin.yaml"
                if not yaml_path.exists():
                    continue

                try:
                    schema = PluginSchema.from_yaml(yaml_path)
                    discovered.append((subdir, schema))
                except Exception:
                    continue

        return discovered

    def load_plugin(self, plugin_dir: Path) -> BasePlugin:
        """Load a plugin from a directory."""
        yaml_path = plugin_dir / "plugin.yaml"
        if not yaml_path.exists():
            raise PluginLoadError(f"No plugin.yaml found in {plugin_dir}")

        # Load schema
        try:
            schema = PluginSchema.from_yaml(yaml_path)
        except Exception as e:
            raise PluginLoadError(f"Invalid plugin.yaml: {e}") from e

        # Get plugin file
        plugin_file = plugin_dir / schema.entry_point
        if not plugin_file.exists():
            raise PluginLoadError(f"Entry point not found: {schema.entry_point}")

        # Validate code if sandbox enabled
        if self.sandbox_enabled:
            with open(plugin_file) as f:
                code = f.read()

            is_safe, issues = validate_plugin_code(code)
            if not is_safe:
                raise PluginLoadError("Plugin code validation failed:\n" + "\n".join(issues))

        # Load the plugin module
        try:
            if self._sandbox:
                # Use sandbox loader for runtime import restriction
                module = self._sandbox.load_module_from_file(
                    str(plugin_file), f"kage_plugin_{schema.name}"
                )
            else:
                spec = importlib.util.spec_from_file_location(
                    f"kage_plugin_{schema.name}",
                    plugin_file,
                )
                if spec is None or spec.loader is None:
                    raise PluginLoadError(f"Could not load plugin: {plugin_file}")

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

        except SandboxViolation:
            raise
        except Exception as e:
            raise PluginLoadError(f"Error loading plugin module: {e}") from e

        # Get plugin class
        plugin_class_obj = getattr(module, schema.plugin_class, None)
        if plugin_class_obj is None:
            raise PluginLoadError(
                f"Plugin class '{schema.plugin_class}' not found in {plugin_file}"
            )

        if not isinstance(plugin_class_obj, type) or not issubclass(
            plugin_class_obj, BasePlugin
        ):
            raise PluginLoadError("Plugin class must inherit from BasePlugin")
        plugin_class: type[BasePlugin] = plugin_class_obj

        # Instantiate plugin
        plugin = plugin_class()

        # Verify metadata matches schema
        if plugin.name != schema.name:
            raise PluginLoadError(f"Plugin name mismatch: {plugin.name} != {schema.name}")

        # Setup plugin
        try:
            plugin.setup()
        except Exception as e:
            raise PluginLoadError(f"Plugin setup failed: {e}") from e

        # Register plugin
        self._plugins[plugin.name] = plugin
        self._plugin_schemas[plugin.name] = schema
        self._plugin_dirs_by_name[plugin.name] = plugin_dir

        # Register capabilities
        for capability in plugin.get_capabilities():
            self._capabilities[capability.name] = (plugin.name, capability)

        try:
            if self.tool_registry:
                tool_schemas = self._register_tools_for_plugin(plugin, schema)
                self._registered_tools[plugin.name] = [tool.name for tool in tool_schemas]
            else:
                self._registered_tools[plugin.name] = []
            if self.prompt_middleware_registry is not None:
                from kage.core.prompt.plugin_middleware_loader import register_plugin_middlewares

                register_plugin_middlewares(
                    schema=schema,
                    registry=self.prompt_middleware_registry,
                    session=getattr(plugin.context, "session", None) if plugin._context is not None else None,
                    turn_id=0,
                )
            if self.workflow_registry is not None:
                register_plugin_workflows(
                    schema=schema,
                    plugin_dir=plugin_dir,
                    registry=self.workflow_registry,
                    session=getattr(plugin.context, "session", None) if plugin._context is not None else None,
                    turn_id=0,
                )
        except Exception as e:
            for cap_name, (plugin_name, _) in list(self._capabilities.items()):
                if plugin_name == plugin.name:
                    del self._capabilities[cap_name]
            self._plugins.pop(plugin.name, None)
            self._registered_tools.pop(plugin.name, None)
            self._plugin_dirs_by_name.pop(plugin.name, None)
            raise PluginLoadError(f"Plugin tool registration failed: {e}") from e

        return plugin

    def load_all_plugins(self) -> tuple[int, list[str]]:
        """Load all discovered plugins.

        Returns:
            Tuple of (loaded_count, list of error messages)
        """
        errors = []
        loaded = 0

        for plugin_dir, schema in self.discover_plugins():
            try:
                self.load_plugin(plugin_dir)
                loaded += 1
            except PluginLoadError as e:
                errors.append(f"{schema.name}: {e}")
            except Exception as e:
                errors.append(f"{plugin_dir.name}: {e}")

        return loaded, errors

    def get_plugin(self, name: str) -> BasePlugin | None:
        """Get a loaded plugin by name."""
        return self._plugins.get(name)

    def get_all_plugins(self) -> list[BasePlugin]:
        """Get all loaded plugins."""
        return list(self._plugins.values())

    def get_capability(self, name: str) -> tuple[BasePlugin, Capability] | None:
        """Get a capability by name.

        Returns:
            Tuple of (plugin, capability) or None
        """
        if name not in self._capabilities:
            return None

        plugin_name, capability = self._capabilities[name]
        plugin = self._plugins.get(plugin_name)
        if not plugin:
            return None

        return plugin, capability

    def get_all_capabilities(self) -> list[Capability]:
        """Get all registered capabilities."""
        return [cap for _, cap in self._capabilities.values()]

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Get OpenAI-compatible tool schemas for all capabilities."""
        return [cap.to_tool_schema() for cap in self.get_all_capabilities()]

    def set_context(
        self, session: Session, log_fn: Callable[[str], None] | None = None
    ) -> None:
        """Set context for all plugins."""
        context = PluginContext(session, log_fn)
        for plugin in self._plugins.values():
            plugin.set_context(context)
        if self.prompt_middleware_registry is not None:
            from kage.core.prompt.plugin_middleware_loader import register_plugin_middlewares

            for plugin_name, schema in self._plugin_schemas.items():
                plugin_instance = self._plugins.get(plugin_name)
                plugin_session = (
                    getattr(plugin_instance.context, "session", None)
                    if plugin_instance is not None and plugin_instance._context is not None
                    else None
                )
                register_plugin_middlewares(
                    schema=schema,
                    registry=self.prompt_middleware_registry,
                    session=plugin_session,
                    turn_id=0,
                )
        if self.workflow_registry is not None:
            for plugin_name, schema in self._plugin_schemas.items():
                plugin_instance = self._plugins.get(plugin_name)
                plugin_session = (
                    getattr(plugin_instance.context, "session", None)
                    if plugin_instance is not None and plugin_instance._context is not None
                    else None
                )
                plugin_dir = self._plugin_dirs_by_name.get(plugin_name)
                if plugin_dir is None:
                    continue
                register_plugin_workflows(
                    schema=schema,
                    plugin_dir=plugin_dir,
                    registry=self.workflow_registry,
                    session=plugin_session,
                    turn_id=0,
                )

    async def invoke_capability(
        self,
        capability_name: str,
        **kwargs: Any,
    ) -> Any:
        """Invoke a capability by name."""
        result = self.get_capability(capability_name)
        if not result:
            raise ValueError(f"Unknown capability: {capability_name}")

        plugin, capability = result
        return await plugin.invoke(capability_name, **kwargs)

    def unload_plugin(self, name: str) -> bool:
        """Unload a plugin."""
        plugin = self._plugins.get(name)
        if not plugin:
            return False

        # Cleanup
        plugin.cleanup()

        # Remove capabilities
        for cap_name, (plugin_name, _) in list(self._capabilities.items()):
            if plugin_name == name:
                del self._capabilities[cap_name]

        if self.tool_registry:
            for tool_name in self._registered_tools.get(name, []):
                self.tool_registry.unregister(tool_name)
        self._registered_tools.pop(name, None)
        self._plugin_schemas.pop(name, None)
        self._plugin_dirs_by_name.pop(name, None)

        # Remove plugin
        del self._plugins[name]
        return True

    def unload_all(self) -> None:
        """Unload all plugins."""
        for name in list(self._plugins.keys()):
            self.unload_plugin(name)

    def _register_tools_for_plugin(self, plugin: BasePlugin, schema: PluginSchema) -> list[ToolSchema]:
        """Lazily import plugin tool loader to avoid import cycles."""
        from kage.core.plugins.tool_loader import register_plugin_tools

        if plugin.name != schema.name:
            raise PluginLoadError(f"Plugin/schema name mismatch: {plugin.name} != {schema.name}")
        if self.tool_registry is None:
            return []
        plugin._manifest_schema = schema
        return register_plugin_tools(plugin, self.tool_registry, schema=schema)
