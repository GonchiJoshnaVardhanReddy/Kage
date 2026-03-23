"""Regression tests for legacy prompt middleware adapter removal."""

from __future__ import annotations

from pathlib import Path

import pytest

from kage.core.agents import WorkflowMemory
from kage.core.models import Command, Session
from kage.core.prompt import CompiledPrompt, MiddlewareRegistry, PromptCompiler, PromptContext
from kage.core.prompt.plugin_middleware_loader import register_plugin_middlewares
from kage.core.tools import ToolRegistry, register_builtin_tools
from kage.plugins.manager import PluginManager
from kage.plugins.schema import PluginSchema


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _recon_plugin_dir() -> Path:
    return _repo_root() / "plugins" / "recon"


def _context(turn_id: int = 19) -> PromptContext:
    session = Session()
    session.commands.append(Command(command="echo one"))
    registry = ToolRegistry()
    register_builtin_tools(registry)
    workflow_memory = WorkflowMemory()
    workflow_memory.findings.append({"title": "Open port 443", "severity": "medium"})
    return PromptContext(
        session=session,
        registry=registry,
        workflow_memory=workflow_memory,
        transcript_excerpts=["user asked for reconnaissance"],
        metadata={"turn_id": turn_id},
    )


class _OrderedMiddleware:
    def __init__(self, name: str, priority: int) -> None:
        self.name = name
        self.priority = priority

    def before_compile(self, context: PromptContext) -> list[object] | None:
        order = context.metadata.setdefault("order", [])
        if isinstance(order, list):
            order.append(self.name)
        return None

    def after_compile(self, compiled_prompt: CompiledPrompt) -> CompiledPrompt:
        return compiled_prompt


class _PromptMutatingMiddleware:
    name = "prompt_mutator"
    priority = 10

    def before_compile(self, context: PromptContext) -> list[object] | None:
        context.metadata["runtime_context"] = "legacy-removal"
        return None

    def after_compile(self, compiled_prompt: CompiledPrompt) -> CompiledPrompt:
        compiled_prompt.system_prompt += "\n\n## Middleware Tail\n- rewritten=true"
        return compiled_prompt


def test_prompt_middleware_manager_import_fails() -> None:
    with pytest.raises(ImportError):
        __import__("kage.core.prompt.middleware")


def test_middleware_registry_still_compiles_prompt() -> None:
    context = _context()
    registry = MiddlewareRegistry()
    registry.register(_PromptMutatingMiddleware())
    compiled = PromptCompiler(middleware=registry).compile(context)
    assert "rewritten=true" in compiled.system_prompt


def test_plugin_manifest_auto_registration_uses_registry() -> None:
    schema = PluginSchema.from_yaml(_recon_plugin_dir() / "plugin.yaml")
    registry = MiddlewareRegistry()
    registered = register_plugin_middlewares(schema=schema, registry=registry)
    assert "recon_context_injector" in registered
    assert [item.name for item in registry.list()] == ["recon_context_injector"]


def test_ordering_preserved_priority_then_registration_order() -> None:
    context = _context()
    registry = MiddlewareRegistry()
    registry.register(_OrderedMiddleware("same_priority_first", 20))
    registry.register(_OrderedMiddleware("same_priority_second", 20))
    registry.register(_OrderedMiddleware("higher_priority", 10))
    registry.apply_before(context)
    assert context.metadata["order"] == [
        "higher_priority",
        "same_priority_first",
        "same_priority_second",
    ]


def test_trace_emission_unchanged_for_registration_and_application() -> None:
    session = Session()
    middleware_registry = MiddlewareRegistry()
    middleware_registry.register(_PromptMutatingMiddleware())
    manager = PluginManager(
        plugin_dirs=[_repo_root() / "plugins"],
        sandbox_enabled=False,
        prompt_middleware_registry=middleware_registry,
    )
    manager.load_plugin(_recon_plugin_dir())
    manager.set_context(session)

    context = PromptContext(
        session=session,
        registry=ToolRegistry(),
        workflow_memory=WorkflowMemory(),
        metadata={"turn_id": 21},
    )
    register_builtin_tools(context.registry)
    PromptCompiler(middleware=middleware_registry).compile(context)

    event_types = [event.event_type for event in session.trace.events]
    assert "middleware_registered" in event_types
    assert "middleware_applied" in event_types
    assert "middleware_modified_context" in event_types
    assert "middleware_modified_prompt" in event_types

