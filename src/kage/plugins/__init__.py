"""Plugins module for Kage."""

from kage.plugins.base import BasePlugin, Capability, CapabilityParameter, PluginContext, capability
from kage.plugins.manager import PluginLoadError, PluginManager
from kage.plugins.sandbox import PluginSandbox, SandboxViolation, validate_plugin_code
from kage.plugins.schema import PluginSchema, PluginToolSchema

__all__ = [
    "BasePlugin",
    "Capability",
    "CapabilityParameter",
    "PluginContext",
    "PluginManager",
    "PluginLoadError",
    "PluginSandbox",
    "SandboxViolation",
    "capability",
    "validate_plugin_code",
    "PluginSchema",
    "PluginToolSchema",
]
