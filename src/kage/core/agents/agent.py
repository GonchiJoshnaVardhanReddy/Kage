"""Base contracts for agent runtime orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from kage.core.tools import ToolExecutionResult

if TYPE_CHECKING:
    from .context import AgentContext


class AgentTerminationSignal(str, Enum):
    """Termination controls returned by an agent."""

    CONTINUE = "continue"
    STOP_PIPELINE = "stop_pipeline"


@dataclass(slots=True)
class AgentResult:
    """Structured result for one agent step."""

    success: bool = True
    message: str | None = None
    output: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    tool_results: list[ToolExecutionResult] = field(default_factory=list)
    termination: AgentTerminationSignal = AgentTerminationSignal.CONTINUE


class BaseAgent:
    """Base class for workflow agents."""

    name: str = "base-agent"
    description: str = "Base agent"
    tool_access_scope: list[str] = []

    async def run(self, context: AgentContext) -> AgentResult:
        """Run one agent step against shared context."""
        raise NotImplementedError("Agents must implement run(context)")


class PlannerAgent(BaseAgent):
    """Example planner that decides the next tool invocation."""

    name = "planner-agent"
    description = "Plans next tool call for workflow execution"
    tool_access_scope = ["builtin.shell"]

    async def run(self, context: AgentContext) -> AgentResult:
        command_raw = context.metadata.get("planned_command", "echo orchestrated")
        command = command_raw if isinstance(command_raw, str) and command_raw.strip() else "echo orchestrated"
        tool_call = {"tool_name": "builtin.shell.run", "arguments": {"command": command}}
        context.memory.add_artifact("planned_tool_call", tool_call)
        context.memory.add_note(f"Planner selected tool builtin.shell.run for command: {command}")
        context.memory.set_confidence("planner", 0.8)
        return AgentResult(
            success=True,
            message="planning complete",
            output={"planned_tool": "builtin.shell.run", "command": command},
        )


class ShellExecutorAgent(BaseAgent):
    """Example executor that invokes builtin.shell.run through ToolRegistry."""

    name = "shell-executor-agent"
    description = "Executes planned shell tool via ToolRegistry"
    tool_access_scope = ["builtin.shell"]

    async def run(self, context: AgentContext) -> AgentResult:
        planned = context.memory.artifacts.get("planned_tool_call")
        tool_name = "builtin.shell.run"
        arguments: dict[str, Any] = {"command": "echo orchestrated"}

        if isinstance(planned, dict):
            raw_tool_name = planned.get("tool_name")
            raw_arguments = planned.get("arguments")
            if isinstance(raw_tool_name, str) and raw_tool_name:
                tool_name = raw_tool_name
            if isinstance(raw_arguments, dict):
                arguments = raw_arguments

        return AgentResult(
            success=True,
            message="executing planned tool",
            output={"tool_name": tool_name, "arguments": arguments},
            tool_calls=[(tool_name, arguments)],
        )


class ReporterAgent(BaseAgent):
    """Example reporter that summarizes workflow activity."""

    name = "reporter-agent"
    description = "Summarizes workflow results into shared memory"
    tool_access_scope = []

    async def run(self, context: AgentContext) -> AgentResult:
        tool_records = [record for record in context.history if record.tool_name is not None]
        total = len(tool_records)
        succeeded = len([record for record in tool_records if record.success])
        summary = f"Workflow executed {total} tool call(s); {succeeded} succeeded."
        context.memory.add_note(summary)
        context.memory.add_artifact(
            "report",
            {
                "summary": summary,
                "tool_calls": total,
                "tool_successes": succeeded,
            },
        )
        context.memory.set_confidence("reporter", 0.9)
        return AgentResult(
            success=True,
            message="report generated",
            output={"summary": summary, "tool_calls": total, "tool_successes": succeeded},
        )

