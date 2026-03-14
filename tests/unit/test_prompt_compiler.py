"""Tests for prompt layer compiler runtime."""

from __future__ import annotations

from kage.core.agents import WorkflowMemory
from kage.core.models import Command, Session
from kage.core.prompt import (
    BasePromptLayer,
    CompiledPrompt,
    PromptCompiler,
    PromptContext,
    PromptMiddlewareManager,
    TokenBudget,
)
from kage.core.tools import ToolRegistry, register_builtin_tools


def _context() -> PromptContext:
    session = Session()
    session.commands.append(Command(command="echo one"))
    registry = ToolRegistry()
    register_builtin_tools(registry)
    memory = WorkflowMemory()
    memory.add_note("first note")
    return PromptContext(
        session=session,
        registry=registry,
        workflow_memory=memory,
        transcript_excerpts=["user asked for reconnaissance"],
    )


class _InjectLayerMiddleware:
    def before_compile(self, context: PromptContext) -> list[object]:
        context.metadata["runtime_context"] = "middleware-updated"
        return [_InjectedLayer()]

    def after_compile(self, compiled_prompt: CompiledPrompt) -> CompiledPrompt:
        compiled_prompt.system_prompt += "\n\n## Middleware Tail\n- rewritten=true"
        return compiled_prompt


class _InjectedLayer(BasePromptLayer):
    def __init__(self) -> None:
        super().__init__(name="middleware_layer", priority=25, enabled=True)

    def content(self, _context: PromptContext) -> str:
        return "## Middleware Layer\n- injected=true"


def test_layer_ordering_by_priority() -> None:
    compiler = PromptCompiler()
    compiled = compiler.compile(_context())
    priorities = [layer.priority for layer in compiled.layers]
    assert priorities == sorted(priorities)


def test_middleware_injection_and_rewrite() -> None:
    manager = PromptMiddlewareManager()
    manager.register(_InjectLayerMiddleware())
    compiler = PromptCompiler(middleware=manager)
    compiled = compiler.compile(_context())
    names = [layer.name for layer in compiled.layers]
    assert "middleware_layer" in names
    assert "rewritten=true" in compiled.system_prompt


def test_memory_truncation_behavior() -> None:
    context = _context()
    for i in range(40):
        context.workflow_memory.add_note(f"note-{i}")
    compiler = PromptCompiler(
        budget=TokenBudget(
            max_tokens=4096,
            layer_limits={"session_memory": 30},
        )
    )
    compiled = compiler.compile(context)
    memory_layer = next(layer for layer in compiled.layers if layer.name == "session_memory")
    assert len(memory_layer.content) > 0
    assert len(memory_layer.content) <= 200


def test_token_budget_drops_low_priority_layers() -> None:
    compiler = PromptCompiler(budget=TokenBudget(max_tokens=40))
    compiled = compiler.compile(_context())
    assert compiled.token_count_estimate <= 40
    assert len(compiled.dropped_layers) >= 1


def test_agent_context_integration_runtime_layer() -> None:
    context = _context()
    context.active_agent_pipeline = {
        "name": "recon-pipeline",
        "step_index": 2,
        "total_steps": 5,
        "objective": "enumerate open services",
        "tool_outputs": ["nmap open ports 22,80,443"],
    }
    compiler = PromptCompiler()
    compiled = compiler.compile(context)
    runtime_layer = next(layer for layer in compiled.layers if layer.name == "runtime_context")
    assert "recon-pipeline" in runtime_layer.content
    assert "enumerate open services" in runtime_layer.content

