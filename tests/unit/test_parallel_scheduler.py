"""Tests for parallel agent scheduler and orchestrator integration."""

from __future__ import annotations

import asyncio
from pathlib import Path

from kage.core.agents import (
    AgentContext,
    AgentOrchestrator,
    AgentPipeline,
    AgentResult,
    BaseAgent,
    DependencyGraph,
    ParallelAgentGroup,
)
from kage.core.models import Session
from kage.core.tools import ToolRegistry, register_builtin_tools


class _DelayedAgent(BaseAgent):
    def __init__(self, name: str, delay_s: float, note: str, artifact_key: str, artifact_value: str) -> None:
        self.name = name
        self.description = f"agent-{name}"
        self._delay_s = delay_s
        self._note = note
        self._artifact_key = artifact_key
        self._artifact_value = artifact_value

    async def run(self, context: AgentContext) -> AgentResult:
        await asyncio.sleep(self._delay_s)
        context.memory.add_note(self._note)
        context.memory.add_artifact(self._artifact_key, self._artifact_value)
        context.memory.set_confidence(self.name, 0.7 + self._delay_s)
        return AgentResult(success=True, output={"agent": self.name, "artifact": self._artifact_key})


class _RecorderAgent(BaseAgent):
    def __init__(self, name: str, seen: list[str]) -> None:
        self.name = name
        self.description = f"agent-{name}"
        self._seen = seen

    async def run(self, _context: AgentContext) -> AgentResult:
        self._seen.append(self.name)
        return AgentResult(success=True, output={"agent": self.name})


def _build_context(tmp_path: Path) -> AgentContext:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    session = Session()
    return AgentContext(
        session=session,
        registry=registry,
        metadata={"workspace_root": tmp_path, "session_metadata": session.metadata, "turn_id": 3},
    )


async def test_parallel_execution_ordering_and_outputs(tmp_path: Path) -> None:
    context = _build_context(tmp_path)
    group = ParallelAgentGroup(
        agents=[
            _DelayedAgent("fast", 0.01, "fast-note", "artifact", "fast"),
            _DelayedAgent("slow", 0.05, "slow-note", "artifact", "slow"),
        ],
        name="fanout",
    )
    pipeline = AgentPipeline(agents=[group], name="parallel-order")
    result = await AgentOrchestrator().run(pipeline, context)
    assert result.success is True
    assert len(result.aggregated_outputs) == 2
    assert "artifact" in result.memory.artifacts
    assert "artifact__slow" in result.memory.artifacts


async def test_dependency_resolution_respects_graph(tmp_path: Path) -> None:
    seen: list[str] = []
    context = _build_context(tmp_path)
    group = ParallelAgentGroup(
        agents=[
            _RecorderAgent("recon", seen),
            _RecorderAgent("enum", seen),
            _RecorderAgent("scan", seen),
        ],
        name="deps",
        dependencies=DependencyGraph(
            {
                "recon": [],
                "enum": ["recon"],
                "scan": ["enum"],
            }
        ),
    )
    pipeline = AgentPipeline(agents=[group], name="parallel-deps")
    result = await AgentOrchestrator().run(pipeline, context)
    assert result.success is True
    assert seen == ["recon", "enum", "scan"]


async def test_memory_merge_correctness(tmp_path: Path) -> None:
    context = _build_context(tmp_path)
    group = ParallelAgentGroup(
        agents=[
            _DelayedAgent("a", 0.02, "note-a", "shared", "one"),
            _DelayedAgent("b", 0.03, "note-b", "shared", "two"),
        ],
        name="merge",
    )
    pipeline = AgentPipeline(agents=[group], name="parallel-merge")
    result = await AgentOrchestrator().run(pipeline, context)
    assert result.success is True
    assert "note-a" in result.memory.notes
    assert "note-b" in result.memory.notes
    assert result.memory.artifacts["shared"] == "one"
    assert result.memory.artifacts["shared__b"] == "two"


async def test_aggregation_strategy_history_and_confidence(tmp_path: Path) -> None:
    context = _build_context(tmp_path)
    group = ParallelAgentGroup(
        agents=[
            _DelayedAgent("alpha", 0.01, "n1", "k1", "v1"),
            _DelayedAgent("beta", 0.02, "n2", "k2", "v2"),
        ],
        name="aggregate",
    )
    result = await AgentOrchestrator().run(AgentPipeline(agents=[group], name="agg"), context)
    assert result.success is True
    assert any(record.agent_name == "alpha" for record in result.history)
    assert any(record.agent_name == "beta" for record in result.history)
    assert result.memory.confidence_scores["alpha"] > 0.0
    assert result.memory.confidence_scores["beta"] > 0.0


async def test_parallel_trace_emission_correctness(tmp_path: Path) -> None:
    context = _build_context(tmp_path)
    group = ParallelAgentGroup(
        agents=[
            _DelayedAgent("x", 0.01, "x-note", "x", "1"),
            _DelayedAgent("y", 0.01, "y-note", "y", "1"),
        ],
        name="trace-group",
    )
    result = await AgentOrchestrator().run(AgentPipeline(agents=[group], name="trace"), context)
    assert result.success is True
    event_types = [event.event_type for event in context.session.trace.get_turn(3)]
    assert "parallel_group_started" in event_types
    assert "parallel_agent_started" in event_types
    assert "parallel_agent_completed" in event_types
    assert "parallel_merge_completed" in event_types
    assert "parallel_group_completed" in event_types


async def test_sequential_compatibility_preserved(tmp_path: Path) -> None:
    seen: list[str] = []
    context = _build_context(tmp_path)
    pipeline = AgentPipeline(
        agents=[_RecorderAgent("one", seen), _RecorderAgent("two", seen), _RecorderAgent("three", seen)],
        name="sequential",
    )
    result = await AgentOrchestrator().run(pipeline, context)
    assert result.success is True
    assert seen == ["one", "two", "three"]

