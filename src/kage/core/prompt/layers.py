"""Prompt layer abstractions and default layer implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from kage.ai.prompts import SYSTEM_PROMPT
from kage.core.observability import recorder_for_session

from .context import PromptContext


class PromptLayer(Protocol):
    """Protocol for one prompt layer."""

    name: str
    priority: int
    enabled: bool

    def content(self, context: PromptContext) -> str:
        """Render layer content from context."""
        ...


@dataclass(slots=True)
class BasePromptLayer:
    """Base prompt layer object."""

    name: str
    priority: int
    enabled: bool = True

    def content(self, _context: PromptContext) -> str:
        return ""


class SystemLayer(BasePromptLayer):
    """Base system identity/capabilities layer."""

    def __init__(self, *, priority: int = 10, enabled: bool = True) -> None:
        super().__init__(name="system", priority=priority, enabled=enabled)

    def content(self, _context: PromptContext) -> str:
        return SYSTEM_PROMPT


class PolicyLayer(BasePromptLayer):
    """Policy layer for runtime safety and scope constraints."""

    def __init__(self, *, priority: int = 20, enabled: bool = True) -> None:
        super().__init__(name="policy", priority=priority, enabled=enabled)

    def content(self, context: PromptContext) -> str:
        safe_mode = context.session.safe_mode
        scope_targets = [target.value for target in context.session.scope.targets]
        lines = ["## Runtime Policy"]
        lines.append(f"- Safe mode: {'enabled' if safe_mode else 'disabled'}")
        if scope_targets:
            lines.append("- Scope targets:")
            for target in scope_targets:
                lines.append(f"  - {target}")
        else:
            lines.append("- Scope targets: none defined")
        return "\n".join(lines)


class CommandLayer(BasePromptLayer):
    """Layer that summarizes recent command execution context."""

    def __init__(self, *, priority: int = 30, enabled: bool = True) -> None:
        super().__init__(name="command", priority=priority, enabled=enabled)

    def content(self, context: PromptContext) -> str:
        commands = context.session.commands[-5:]
        if not commands:
            return ""
        lines = ["## Recent Commands"]
        for command in commands:
            lines.append(f"- {command.command} ({command.status.value})")
        return "\n".join(lines)


class SessionMemoryLayer(BasePromptLayer):
    """Layer that exposes session metadata and workflow memory."""

    def __init__(self, *, priority: int = 40, enabled: bool = True) -> None:
        super().__init__(name="session_memory", priority=priority, enabled=enabled)

    def content(self, context: PromptContext) -> str:
        from kage.core.memory import MemoryRetriever, get_or_create_memory_store

        lines = ["## Session Memory"]
        store = get_or_create_memory_store(context.session)
        retriever = MemoryRetriever(store)
        query_hints = [
            *(context.transcript_excerpts[-3:] if context.transcript_excerpts else []),
            *(context.workflow_memory.notes[-2:] if context.workflow_memory.notes else []),
        ]
        query = " ".join(query_hints).strip()
        blocks = retriever.retrieve(query, limit=4) if query else retriever.retrieve_recent(limit=4)
        if blocks:
            lines.append("- Compacted memory blocks:")
            recorder = recorder_for_session(context.session, component="prompt_memory_layer")
            turn_id = int(context.metadata.get("turn_id", 0))
            for block in blocks:
                lines.append(f"  - {block.summary}")
                if block.entities:
                    lines.append(f"    entities: {', '.join(block.entities[:6])}")
                if block.artifacts:
                    lines.append(f"    artifacts: {', '.join(block.artifacts[:6])}")
                recorder.record(
                    event_type="memory_block_used",
                    turn_id=turn_id,
                    payload={"block_id": block.block_id, "confidence_score": block.confidence_score},
                )
        if context.workflow_memory.notes:
            lines.append("- Notes:")
            for note in context.workflow_memory.notes[-8:]:
                lines.append(f"  - {note}")
        if context.workflow_memory.findings:
            lines.append(f"- Findings tracked: {len(context.workflow_memory.findings)}")
        if context.workflow_memory.targets:
            lines.append("- Workflow targets:")
            for target in context.workflow_memory.targets[-8:]:
                lines.append(f"  - {target}")
        if context.workflow_memory.artifacts:
            artifact_keys = sorted(context.workflow_memory.artifacts.keys())
            lines.append(f"- Artifacts: {', '.join(artifact_keys)}")
        if len(lines) == 1:
            return ""
        return "\n".join(lines)


class PluginLayer(BasePromptLayer):
    """Layer for plugin-provided prompt context injections."""

    def __init__(self, *, priority: int = 50, enabled: bool = True) -> None:
        super().__init__(name="plugin", priority=priority, enabled=enabled)

    def content(self, context: PromptContext) -> str:
        if not context.plugin_injections:
            return ""
        lines = ["## Plugin Context"]
        for item in context.plugin_injections:
            if item.strip():
                lines.append(f"- {item.strip()}")
        return "\n".join(lines)


class RuntimeContextLayer(BasePromptLayer):
    """Layer for runtime + agent pipeline execution context."""

    def __init__(self, *, priority: int = 60, enabled: bool = True) -> None:
        super().__init__(name="runtime_context", priority=priority, enabled=enabled)

    def content(self, context: PromptContext) -> str:
        lines = ["## Runtime Context"]

        pipeline = context.active_agent_pipeline or {}
        if pipeline:
            lines.append(f"- Active pipeline: {pipeline.get('name', 'unknown')}")
            if "step_index" in pipeline and "total_steps" in pipeline:
                lines.append(f"- Pipeline step: {pipeline['step_index']}/{pipeline['total_steps']}")
            objective = pipeline.get("objective")
            if isinstance(objective, str) and objective.strip():
                lines.append(f"- Current objective: {objective.strip()}")
            tool_outputs = pipeline.get("tool_outputs")
            if isinstance(tool_outputs, list) and tool_outputs:
                lines.append("- Agent tool outputs:")
                for item in tool_outputs[-5:]:
                    lines.append(f"  - {str(item)[:300]}")

        if context.transcript_excerpts:
            lines.append("- Recent transcript excerpts:")
            for excerpt in context.transcript_excerpts[-6:]:
                lines.append(f"  - {excerpt[:300]}")

        metadata_runtime = context.metadata.get("runtime_context")
        if isinstance(metadata_runtime, str) and metadata_runtime.strip():
            lines.append(f"- Runtime notes: {metadata_runtime.strip()}")

        if len(lines) == 1:
            return ""
        return "\n".join(lines)

