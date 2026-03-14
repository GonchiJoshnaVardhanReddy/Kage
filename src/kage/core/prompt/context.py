"""Prompt compiler context models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kage.core.agents import WorkflowMemory
from kage.core.models import Session
from kage.core.tools import ToolRegistry


@dataclass(slots=True)
class PromptContext:
    """Runtime data used to compile layered prompts."""

    session: Session
    registry: ToolRegistry
    workflow_memory: WorkflowMemory = field(default_factory=WorkflowMemory)
    active_agent_pipeline: dict[str, Any] | None = None
    plugin_injections: list[str] = field(default_factory=list)
    transcript_excerpts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PromptLayerOutput:
    """Rendered output of one prompt layer."""

    name: str
    priority: int
    content: str


@dataclass(slots=True)
class CompiledPrompt:
    """Provider-ready compiled prompt payload."""

    system_prompt: str
    layers: list[PromptLayerOutput] = field(default_factory=list)
    dropped_layers: list[str] = field(default_factory=list)
    token_count_estimate: int = 0

