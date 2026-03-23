"""Runtime workflow template model and pipeline construction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kage.core.agents import (
    AgentPipeline,
    BaseAgent,
    DependencyGraph,
    ParallelAgentGroup,
    PlannerAgent,
    ReporterAgent,
    ShellExecutorAgent,
)

from .schema import ParallelStepSchema, WorkflowTemplateSchema

_BUILTIN_AGENT_FACTORIES: dict[str, type[BaseAgent]] = {
    "PlannerAgent": PlannerAgent,
    "ReconAgent": PlannerAgent,
    "EnumAgent": ShellExecutorAgent,
    "ScanAgent": ShellExecutorAgent,
    "VerifierAgent": ReporterAgent,
    "ShellExecutorAgent": ShellExecutorAgent,
    "ReporterAgent": ReporterAgent,
}


def _agent_from_name(name: str) -> BaseAgent:
    agent_class = _BUILTIN_AGENT_FACTORIES.get(name)
    if agent_class is None:
        raise ValueError(f"Unknown workflow agent: {name}")
    return agent_class()


@dataclass(slots=True)
class WorkflowTemplate:
    """Declarative workflow template materialized to runtime pipeline."""

    name: str
    description: str = ""
    pipeline_steps: list[str | list[str]] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    required_middleware: list[str] = field(default_factory=list)
    policy_overrides: dict[str, Any] = field(default_factory=dict)
    default_parameters: dict[str, Any] = field(default_factory=dict)
    source: str = "runtime"

    @classmethod
    def from_schema(cls, schema: WorkflowTemplateSchema, *, source: str = "runtime") -> WorkflowTemplate:
        """Create a runtime template from validated schema."""
        steps: list[str | list[str]] = []
        for step in schema.pipeline:
            if isinstance(step, str):
                steps.append(step)
            elif isinstance(step, ParallelStepSchema):
                steps.append(list(step.parallel))
            else:
                raise ValueError(f"Unsupported workflow step type: {type(step).__name__}")
        return cls(
            name=schema.name,
            description=schema.description,
            pipeline_steps=steps,
            required_tools=list(schema.required_tools),
            required_middleware=list(schema.required_middleware),
            policy_overrides=dict(schema.policy_overrides),
            default_parameters=dict(schema.default_parameters),
            source=source,
        )

    def build_pipeline(self) -> AgentPipeline:
        """Build an AgentPipeline for orchestrator execution."""
        agents: list[BaseAgent | ParallelAgentGroup] = []
        for index, step in enumerate(self.pipeline_steps):
            if isinstance(step, str):
                agents.append(_agent_from_name(step))
                continue
            if isinstance(step, list):
                group_agents = [_agent_from_name(agent_name) for agent_name in step]
                agents.append(
                    ParallelAgentGroup(
                        agents=group_agents,
                        name=f"{self.name}-parallel-{index}",
                        dependencies=DependencyGraph(),
                    )
                )
                continue
            raise ValueError(f"Unsupported workflow step: {step!r}")
        return AgentPipeline(agents=agents, name=self.name, metadata={"template_name": self.name})

