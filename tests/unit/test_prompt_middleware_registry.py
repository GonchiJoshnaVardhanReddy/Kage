"""Tests for prompt middleware registry and plugin auto-registration."""

from __future__ import annotations

from pathlib import Path

from kage.core.agents import WorkflowMemory
from kage.core.models import Command, Session
from kage.core.prompt import (
    BasePromptLayer,
    CompiledPrompt,
    MiddlewareRegistry,
    PromptCompiler,
    PromptContext,
)
from kage.core.prompt.plugin_middleware_loader import register_plugin_middlewares
from kage.core.tools import ToolRegistry, register_builtin_tools
from kage.plugins.manager import PluginManager
from kage.plugins.schema import PluginSchema


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _recon_plugin_dir() -> Path:
    return _repo_root() / "plugins" / "recon"


def _context() -> PromptContext:
    session = Session()
    session.commands.append(Command(command="echo one"))
    registry = ToolRegistry()
    register_builtin_tools(registry)
    memory = WorkflowMemory()
    memory.findings.append({"title": "Open port 443", "severity": "medium"})
    return PromptContext(
        session=session,
        registry=registry,
        workflow_memory=memory,
        transcript_excerpts=["user asked for reconnaissance"],
        metadata={"turn_id": 11},
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


class _InjectLayerMiddleware:
    name = "injector"
    priority = 25

    def before_compile(self, context: PromptContext) -> list[object]:
        context.metadata["runtime_context"] = "middleware-updated"
        return [_InjectedLayer()]

    def after_compile(self, compiled_prompt: CompiledPrompt) -> CompiledPrompt:
        return compiled_prompt


class _RewritePromptMiddleware:
    name = "rewriter"
    priority = 40

    def before_compile(self, _context: PromptContext) -> list[object] | None:
        return None

    def after_compile(self, compiled_prompt: CompiledPrompt) -> CompiledPrompt:
        compiled_prompt.system_prompt += "\n\n## Middleware Tail\n- rewritten=true"
        return compiled_prompt


class _InjectedLayer(BasePromptLayer):
    def __init__(self) -> None:
        super().__init__(name="middleware_layer", priority=26, enabled=True)

    def content(self, _context: PromptContext) -> str:
        return "## Middleware Layer\n- injected=true"


def test_middleware_ordering_deterministic() -> None:
    context = _context()
    registry = MiddlewareRegistry()
    registry.register(_OrderedMiddleware("second", 20))
    registry.register(_OrderedMiddleware("first", 10))
    registry.apply_before(context)
    assert context.metadata["order"] == ["first", "second"]


def test_middleware_context_modification_and_layer_injection() -> None:
    context = _context()
    registry = MiddlewareRegistry()
    registry.register(_InjectLayerMiddleware())
    compiled = PromptCompiler(middleware=registry).compile(context)
    names = [layer.name for layer in compiled.layers]
    assert "middleware_layer" in names
    assert context.metadata["runtime_context"] == "middleware-updated"


def test_middleware_prompt_modification() -> None:
    context = _context()
    registry = MiddlewareRegistry()
    registry.register(_RewritePromptMiddleware())
    compiled = PromptCompiler(middleware=registry).compile(context)
    assert "rewritten=true" in compiled.system_prompt


def test_plugin_manifest_auto_registration() -> None:
    schema = PluginSchema.from_yaml(_recon_plugin_dir() / "plugin.yaml")
    registry = MiddlewareRegistry()
    registered = register_plugin_middlewares(schema=schema, registry=registry)
    assert "recon_context_injector" in registered
    assert [item.name for item in registry.list()] == ["recon_context_injector"]


def test_plugin_manager_auto_registration_and_trace() -> None:
    session = Session()
    registry = MiddlewareRegistry()
    manager = PluginManager(
        plugin_dirs=[_repo_root() / "plugins"],
        sandbox_enabled=False,
        prompt_middleware_registry=registry,
    )
    manager.load_plugin(_recon_plugin_dir())
    manager.set_context(session)
    manager.load_plugin(_recon_plugin_dir())

    middleware_names = [item.name for item in registry.list()]
    assert middleware_names == ["recon_context_injector"]

    events = [event for event in session.trace.events if event.event_type == "middleware_registered"]
    assert events
    assert events[-1].payload.get("middleware") == "recon_context_injector"
    assert events[-1].payload.get("plugin") == "recon"


def test_trace_emission_for_middleware_application() -> None:
    context = _context()
    registry = MiddlewareRegistry()
    registry.register(_InjectLayerMiddleware())
    registry.register(_RewritePromptMiddleware())
    PromptCompiler(middleware=registry).compile(context)

    turn_events = context.session.trace.get_turn(11)
    event_types = [event.event_type for event in turn_events]
    assert "middleware_applied" in event_types
    assert "middleware_modified_context" in event_types
    assert "middleware_modified_prompt" in event_types

