"""Tests for observability trace pipeline integration."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from kage.core.agents import (
    AgentContext,
    AgentOrchestrator,
    AgentPipeline,
    PlannerAgent,
    ShellExecutorAgent,
)
from kage.core.hooks import HookEvent, HookManager
from kage.core.models import Session
from kage.core.observability import TraceEvent, TraceRecorder, export_json, export_jsonl
from kage.core.prompt import PromptCompiler, PromptContext
from kage.core.tools import ToolExecutionPlan, ToolRegistry, register_builtin_tools
from kage.persistence.session import SessionStorage


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    return registry


def test_event_ordering_and_batch_flush() -> None:
    session = Session()
    recorder = TraceRecorder(trace=session.trace, session_id=session.id, default_component="test")
    recorder.attach_metadata({"scope": "unit"})
    recorder.record(event_type="prompt_compiled", turn_id=1, payload={"a": 1})
    asyncio.run(recorder.add_to_batch(event_type="tool_called", turn_id=1, payload={"b": 2}))
    asyncio.run(recorder.add_to_batch(event_type="tool_completed", turn_id=1, payload={"c": 3}))
    assert asyncio.run(recorder.flush_batch()) == 2

    events = session.trace.get_turn(1)
    assert [event.event_type for event in events] == [
        "prompt_compiled",
        "tool_called",
        "tool_completed",
    ]
    assert events[0].payload["scope"] == "unit"


async def test_event_persistence_roundtrip(tmp_path: Path) -> None:
    storage = SessionStorage(storage_dir=tmp_path)
    session = Session(name="trace-persist")
    session.trace.append(
        TraceEvent(
            event_type="policy_decision",
            session_id=session.id,
            turn_id=2,
            component="test",
            payload={"decision": "allow"},
        )
    )
    await storage.save(session)
    loaded = await storage.load(session.id)
    assert loaded is not None
    assert loaded.trace.events
    assert loaded.trace.events[0].event_type == "policy_decision"


def test_multi_turn_trace_integrity() -> None:
    session = Session()
    recorder = TraceRecorder(trace=session.trace, session_id=session.id)
    recorder.record(event_type="prompt_compiled", turn_id=1)
    recorder.record(event_type="tool_called", turn_id=2)
    recorder.record(event_type="tool_completed", turn_id=2)

    assert [event.event_type for event in session.trace.get_turn(1)] == ["prompt_compiled"]
    assert [event.event_type for event in session.trace.get_turn(2)] == ["tool_called", "tool_completed"]


async def test_agent_pipeline_trace_correctness(tmp_path: Path) -> None:
    session = Session()
    context = AgentContext(
        session=session,
        registry=_registry(),
        metadata={"workspace_root": tmp_path, "session_metadata": session.metadata, "turn_id": 5},
    )
    pipeline = AgentPipeline(agents=[PlannerAgent(), ShellExecutorAgent()], name="trace-agent")
    result = await AgentOrchestrator().run(pipeline, context)
    assert result.success is True

    types = [event.event_type for event in session.trace.get_turn(5)]
    assert "agent_started" in types
    assert "pipeline_step_started" in types
    assert "agent_step_completed" in types
    assert "agent_completed" in types


def test_prompt_layer_trace_emission() -> None:
    session = Session()
    context = PromptContext(session=session, registry=_registry(), metadata={"turn_id": 7})
    compiled = PromptCompiler().compile(context)
    assert compiled.system_prompt

    turn_events = session.trace.get_turn(7)
    event_types = [event.event_type for event in turn_events]
    assert "prompt_compiled" in event_types
    assert "layer_applied" in event_types


async def test_tool_and_hook_events_and_exports(tmp_path: Path) -> None:
    session = Session()
    registry = _registry()
    hook_manager = HookManager()

    def block_hook(_payload: dict) -> dict:
        return {"continue_pipeline": False}

    hook_manager.register(event=HookEvent.PRE_COMMAND_RUN, callback=block_hook, name="block")
    result = await hook_manager.dispatch(
        HookEvent.PRE_COMMAND_RUN,
        {"session_id": session.id, "turn_id": 9, "command": "builtin.session.note"},
    )
    assert result.continue_pipeline is False

    await registry.execute(
        ToolExecutionPlan(tool_name="builtin.session.note", arguments={"text": "hello"}),
        context={"session": session, "session_metadata": session.metadata, "workspace_root": tmp_path, "turn_id": 9},
    )

    turn_types = [event.event_type for event in session.trace.get_turn(9)]
    assert "hook_triggered" in turn_types
    assert "hook_blocked_execution" in turn_types
    assert "policy_decision" in turn_types
    assert "tool_selected" in turn_types
    assert "tool_executed" in turn_types
    assert "tool_completed" in turn_types

    exported_json = export_json(session.trace)
    parsed = json.loads(exported_json)
    assert isinstance(parsed.get("events"), list)

    exported_jsonl = export_jsonl(session.trace)
    lines = [line for line in exported_jsonl.splitlines() if line.strip()]
    assert lines

