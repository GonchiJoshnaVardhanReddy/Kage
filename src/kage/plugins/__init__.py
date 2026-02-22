"""Plugins module for Kage."""

from kage.plugins.base import BasePlugin, Capability, CapabilityParameter, PluginContext
from kage.plugins.manager import PluginLoadError, PluginManager
from kage.plugins.sandbox import PluginSandbox, SandboxViolation, validate_plugin_code
from kage.plugins.schema import PluginSchema

__all__ = [
    "BasePlugin",
    "Capability",
    "CapabilityParameter",
    "PluginContext",
    "PluginManager",
    "PluginLoadError",
    "PluginSandbox",
    "SandboxViolation",
    "validate_plugin_code",
    "PluginSchema",
]
