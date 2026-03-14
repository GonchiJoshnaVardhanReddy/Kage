"""Agent pipeline definitions and result aggregation models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .agent import BaseAgent
from .context import AgentExecutionRecord
from .memory import WorkflowMemory


@dataclass(slots=True)
class AgentPipeline:
    """Ordered sequence of agents executed by the orchestrator."""

    agents: list[BaseAgent]
    name: str = "agent-pipeline"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OrchestrationResult:
    """Final orchestration output."""

    success: bool
    pipeline_name: str
    terminated_early: bool
    started_at: datetime
    completed_at: datetime
    history: list[AgentExecutionRecord] = field(default_factory=list)
    aggregated_outputs: list[dict[str, Any]] = field(default_factory=list)
    memory: WorkflowMemory = field(default_factory=WorkflowMemory)
    errors: list[str] = field(default_factory=list)

