"""Tests for memory compaction runtime and integrations."""

from __future__ import annotations

from pathlib import Path

from kage.core.agents import (
    AgentContext,
    AgentOrchestrator,
    AgentPipeline,
    PlannerAgent,
    ShellExecutorAgent,
)
from kage.core.memory import (
    MemoryBlock,
    MemoryCompactor,
    MemoryRetriever,
    MemoryStore,
    RuleBasedMemorySummarizer,
    get_or_create_memory_store,
)
from kage.core.models import Session
from kage.core.prompt import PromptCompiler, PromptContext
from kage.core.tools import ToolRegistry, register_builtin_tools


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    return registry


def test_block_creation_and_store_persistence() -> None:
    session = Session()
    store = get_or_create_memory_store(session)
    block = MemoryBlock(
        summary="Open ports detected: 22, 80",
        entities=["example.com"],
        artifacts=["port_scan_result"],
        confidence_score=0.82,
        source_turn_ids=[1, 2],
    )
    store.add(block)
    assert store.blocks
    assert store.blocks[0].summary.startswith("Open ports detected")
    assert isinstance(session.metadata.get("memory_blocks"), list)


def test_retrieval_ranking_prefers_matching_block() -> None:
    store = MemoryStore()
    store.add(
        MemoryBlock(
            summary="Open ports detected: 22, 80",
            entities=["example.com"],
            artifacts=["port_scan_result"],
            confidence_score=0.82,
            source_turn_ids=[1],
        )
    )
    store.add(
        MemoryBlock(
            summary="TLS certificate details collected",
            entities=["example.com"],
            artifacts=["tls_report"],
            confidence_score=0.65,
            source_turn_ids=[2],
        )
    )
    retriever = MemoryRetriever(store)
    results = retriever.retrieve("open ports example.com")
    assert results
    assert "open ports" in results[0].summary.lower()


def test_compaction_trigger_and_deduplication() -> None:
    session = Session()
    store = get_or_create_memory_store(session)
    compactor = MemoryCompactor(
        store=store,
        summarizer=RuleBasedMemorySummarizer(),
    )
    excerpts = [
        "Scan result example.com ports 22 80",
        "Scan result example.com ports 22 80",
        "Scan result example.com ports 22 80",
        "Scan result example.com ports 22 80",
        "Scan result example.com ports 22 80",
    ]
    created = compactor.compact(
        session=session,
        workflow_memory=type("wm", (), {"intermediate_outputs": []})(),
        transcript_excerpts=excerpts,
        turn_id=4,
        trigger="agent_pipeline_completed",
    )
    assert created
    assert store.blocks
    dedup_events = [event for event in session.trace.get_turn(4) if event.event_type == "memory_block_deduplicated"]
    assert isinstance(dedup_events, list)


def test_prompt_layer_prefers_memory_blocks() -> None:
    session = Session()
    store = get_or_create_memory_store(session)
    store.add(
        MemoryBlock(
            summary="Open ports detected: 22, 80",
            entities=["example.com"],
            artifacts=["port_scan_result"],
            confidence_score=0.82,
            source_turn_ids=[1],
        )
    )
    context = PromptContext(
        session=session,
        registry=_registry(),
        transcript_excerpts=["What ports are open on example.com?"],
        metadata={"turn_id": 6},
    )
    compiled = PromptCompiler().compile(context)
    memory_layer = next(layer for layer in compiled.layers if layer.name == "session_memory")
    assert "Compacted memory blocks" in memory_layer.content
    used_events = [event for event in session.trace.get_turn(6) if event.event_type == "memory_block_used"]
    assert used_events


async def test_agent_workflow_triggers_compaction(tmp_path: Path) -> None:
    session = Session()
    context = AgentContext(
        session=session,
        registry=_registry(),
        metadata={"workspace_root": tmp_path, "session_metadata": session.metadata, "turn_id": 10},
    )
    pipeline = AgentPipeline(agents=[PlannerAgent(), ShellExecutorAgent()], name="memory-agent")
    result = await AgentOrchestrator().run(pipeline, context)
    assert result.success is True

    store = get_or_create_memory_store(session)
    assert store.blocks
    turn_events = [event.event_type for event in session.trace.get_turn(10)]
    assert "memory_compaction_triggered" in turn_events
    assert "memory_block_created" in turn_events

