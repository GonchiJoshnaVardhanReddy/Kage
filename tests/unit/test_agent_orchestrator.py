"""Tests for agent orchestration runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kage.core.agents import (
    AgentContext,
    AgentOrchestrator,
    AgentPipeline,
    AgentResult,
    AgentTerminationSignal,
    BaseAgent,
    PlannerAgent,
    ReporterAgent,
    ShellExecutorAgent,
)
from kage.core.hooks import HookEvent, HookManager
from kage.core.models import Session
from kage.core.tools import ToolRegistry, register_builtin_tools


class _RecordingAgent(BaseAgent):
    def __init__(self, name: str, seen: list[str]) -> None:
        self.name = name
        self.description = f"agent-{name}"
        self._seen = seen

    async def run(self, context: AgentContext) -> AgentResult:
        self._seen.append(self.name)
        context.memory.add_note(f"ran:{self.name}")
        return AgentResult(success=True, output={"agent": self.name})


class _StopAgent(BaseAgent):
    name = "stop-agent"
    description = "stops pipeline"

    async def run(self, _context: AgentContext) -> AgentResult:
        return AgentResult(
            success=True,
            message="stop now",
            output={"stopped": True},
            termination=AgentTerminationSignal.STOP_PIPELINE,
        )


def _build_context(tmp_path: Path) -> AgentContext:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    session = Session()
    return AgentContext(
        session=session,
        registry=registry,
        metadata={
            "workspace_root": tmp_path,
            "session_metadata": session.metadata,
            "turn_id": 1,
        },
    )


async def test_pipeline_ordering(tmp_path: Path) -> None:
    seen: list[str] = []
    context = _build_context(tmp_path)
    pipeline = AgentPipeline(
        agents=[_RecordingAgent("a", seen), _RecordingAgent("b", seen), _RecordingAgent("c", seen)],
        name="order",
    )
    result = await AgentOrchestrator().run(pipeline, context)
    assert result.success is True
    assert seen == ["a", "b", "c"]
    assert len(result.aggregated_outputs) == 3


async def test_memory_propagation_across_agents(tmp_path: Path) -> None:
    context = _build_context(tmp_path)
    pipeline = AgentPipeline(
        agents=[PlannerAgent(), ShellExecutorAgent(), ReporterAgent()],
        name="memory",
    )
    result = await AgentOrchestrator().run(pipeline, context)
    assert result.success is True
    assert "planned_tool_call" in result.memory.artifacts
    assert "report" in result.memory.artifacts
    assert any("Workflow executed" in note for note in result.memory.notes)


async def test_tool_execution_routing_through_registry(tmp_path: Path) -> None:
    context = _build_context(tmp_path)
    context.metadata["planned_command"] = "echo hello"
    pipeline = AgentPipeline(agents=[PlannerAgent(), ShellExecutorAgent()], name="routing")
    result = await AgentOrchestrator().run(pipeline, context)
    assert result.success is True
    tool_records = [entry for entry in result.history if entry.tool_name is not None]
    assert len(tool_records) == 1
    assert tool_records[0].tool_name == "builtin.shell.run"
    assert tool_records[0].tool_result is not None
    assert tool_records[0].tool_result.success is True


async def test_termination_signal_stops_remaining_agents(tmp_path: Path) -> None:
    seen: list[str] = []
    context = _build_context(tmp_path)
    pipeline = AgentPipeline(
        agents=[_RecordingAgent("first", seen), _StopAgent(), _RecordingAgent("last", seen)],
        name="termination",
    )
    result = await AgentOrchestrator().run(pipeline, context)
    assert result.terminated_early is True
    assert seen == ["first"]
    assert all(output.get("agent") != "last" for output in result.aggregated_outputs)


async def test_result_aggregation_and_hook_events(tmp_path: Path) -> None:
    context = _build_context(tmp_path)
    hooks = HookManager()
    events: list[HookEvent] = []

    @dataclass
    class _HookResult:
        continue_pipeline: bool = True

    async def pre_hook(_payload: dict[str, Any]) -> _HookResult:
        events.append(HookEvent.PRE_COMMAND_RUN)
        return _HookResult(continue_pipeline=True)

    async def post_hook(_payload: dict[str, Any]) -> _HookResult:
        events.append(HookEvent.POST_COMMAND_RUN)
        return _HookResult(continue_pipeline=True)

    hooks.register(event=HookEvent.PRE_COMMAND_RUN, callback=pre_hook, name="pre")
    hooks.register(event=HookEvent.POST_COMMAND_RUN, callback=post_hook, name="post")

    pipeline = AgentPipeline(agents=[PlannerAgent(), ShellExecutorAgent(), ReporterAgent()], name="aggregate")
    result = await AgentOrchestrator(hooks=hooks).run(pipeline, context)
    assert result.success is True
    assert len(result.aggregated_outputs) == 3
    assert HookEvent.PRE_COMMAND_RUN in events
    assert HookEvent.POST_COMMAND_RUN in events


async def test_context_emits_hooks_without_orchestrator_hooks(tmp_path: Path) -> None:
    context = _build_context(tmp_path)
    events: list[HookEvent] = []

    @dataclass
    class _HookResult:
        continue_pipeline: bool = True

    async def hook_dispatch(event: HookEvent, _payload: dict[str, Any]) -> _HookResult:
        events.append(event)
        return _HookResult(continue_pipeline=True)

    context.metadata["hook_dispatch"] = hook_dispatch
    await context.execute_tool("builtin.shell.run", {"command": "echo context-hooks"})
    assert events == [HookEvent.PRE_COMMAND_RUN, HookEvent.POST_COMMAND_RUN]

