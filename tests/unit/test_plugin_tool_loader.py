"""Tests for plugin tool loader and manager integration with ToolRegistry."""

from __future__ import annotations

from pathlib import Path

import pytest

from kage.core.plugins.tool_loader import (
    PluginToolLoaderError,
    discover_plugin_tools,
    register_plugin_tools,
    validate_plugin_tool_schema,
)
from kage.core.tools import ToolExecutionPlan, ToolRegistry, register_builtin_tools
from kage.plugins.manager import PluginLoadError, PluginManager
from kage.plugins.schema import PluginSchema, PluginToolSchema


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _recon_plugin_dir() -> Path:
    return _repo_root() / "plugins" / "recon"


def test_plugin_tool_discovery() -> None:
    manager = PluginManager(plugin_dirs=[_repo_root() / "plugins"], sandbox_enabled=False)
    plugin = manager.load_plugin(_recon_plugin_dir())
    schema = PluginSchema.from_yaml(_recon_plugin_dir() / "plugin.yaml")
    manifests = discover_plugin_tools(plugin, schema=schema)
    names = [item.full_tool_name for item in manifests]
    assert "plugin.recon.scan" in names


def test_tool_schema_validation() -> None:
    manager = PluginManager(plugin_dirs=[_repo_root() / "plugins"], sandbox_enabled=False)
    plugin = manager.load_plugin(_recon_plugin_dir())
    schema = PluginSchema.from_yaml(_recon_plugin_dir() / "plugin.yaml")
    manifests = discover_plugin_tools(plugin, schema=schema)
    for manifest in manifests:
        validate_plugin_tool_schema(manifest)


def test_manifest_tool_schema_validation() -> None:
    manifest_tool = PluginToolSchema(
        name="scan",
        description="Scan target",
        parameters={"target": "str"},
    )
    validate_plugin_tool_schema(manifest_tool)


def test_namespace_isolation() -> None:
    manager = PluginManager(plugin_dirs=[_repo_root() / "plugins"], sandbox_enabled=False)
    plugin = manager.load_plugin(_recon_plugin_dir())
    schema = PluginSchema.from_yaml(_recon_plugin_dir() / "plugin.yaml")
    manifests = discover_plugin_tools(plugin, schema=schema)
    assert all(manifest.full_tool_name.startswith("plugin.recon.") for manifest in manifests)


def test_duplicate_conflict_detection() -> None:
    manager = PluginManager(plugin_dirs=[_repo_root() / "plugins"], sandbox_enabled=False)
    plugin = manager.load_plugin(_recon_plugin_dir())
    schema = PluginSchema.from_yaml(_recon_plugin_dir() / "plugin.yaml")
    registry = ToolRegistry()
    register_plugin_tools(plugin, registry, schema=schema)
    with pytest.raises(PluginToolLoaderError, match="collision"):
        register_plugin_tools(plugin, registry, schema=schema)


async def test_execution_dispatch_through_registry() -> None:
    manager = PluginManager(plugin_dirs=[_repo_root() / "plugins"], sandbox_enabled=False)
    plugin = manager.load_plugin(_recon_plugin_dir())
    schema = PluginSchema.from_yaml(_recon_plugin_dir() / "plugin.yaml")
    registry = ToolRegistry()
    register_plugin_tools(plugin, registry, schema=schema)
    result = await registry.execute(
        ToolExecutionPlan(tool_name="plugin.recon.scan", arguments={"target": "example.com"})
    )
    assert result.success is True
    assert isinstance(result.data, dict)
    assert result.data["status"] == "ok"
    assert result.data["target"] == "example.com"


def test_plugin_manager_registers_tools_automatically() -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    manager = PluginManager(
        plugin_dirs=[_repo_root() / "plugins"],
        sandbox_enabled=False,
        tool_registry=registry,
    )
    manager.load_plugin(_recon_plugin_dir())
    assert registry.get("plugin.recon.scan") is not None


def test_plugin_manager_duplicate_conflict_detection() -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    manager = PluginManager(
        plugin_dirs=[_repo_root() / "plugins"],
        sandbox_enabled=False,
        tool_registry=registry,
    )
    manager.load_plugin(_recon_plugin_dir())
    with pytest.raises(PluginLoadError, match="registration failed"):
        manager.load_plugin(_recon_plugin_dir())

