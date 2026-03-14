"""Agent context passed across orchestration steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from inspect import isawaitable
from typing import Any

from kage.core.hooks import HookEvent
from kage.core.models import Session
from kage.core.tools import (
    ToolExecutionOrigin,
    ToolExecutionPlan,
    ToolExecutionResult,
    ToolRegistry,
)
from kage.utils import utcnow

from .memory import WorkflowMemory


@dataclass(slots=True)
class AgentExecutionRecord:
    """One execution record for agent run history."""

    step_index: int
    agent_name: str
    started_at: datetime
    completed_at: datetime
    success: bool
    message: str | None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    tool_result: ToolExecutionResult | None = None
    error: str | None = None


@dataclass(slots=True)
class AgentContext:
    """Runtime context shared by agents in one workflow pipeline."""

    session: Session
    registry: ToolRegistry
    memory: WorkflowMemory = field(default_factory=WorkflowMemory)
    history: list[AgentExecutionRecord] = field(default_factory=list)
    current_step_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        """Execute one tool through ToolRegistry and track execution history."""
        started_at = utcnow()
        hook_dispatch_raw = self.metadata.get("hook_dispatch")
        hook_dispatch = hook_dispatch_raw if callable(hook_dispatch_raw) else None

        if hook_dispatch is not None and self.metadata.get("hooks_pre_dispatched") is not True:
            pre_result = hook_dispatch(
                HookEvent.PRE_COMMAND_RUN,
                {
                    "session_id": self.session.id,
                    "turn_id": int(self.metadata.get("turn_id", 0)),
                    "command": tool_name,
                    "description": str(self.metadata.get("description", "")),
                    "route_tool": tool_name,
                    "route_reasoning": "AgentContext ToolRegistry dispatch",
                    "phase": "agent_pipeline",
                    "step_index": self.current_step_index + 1,
                    "total_steps": int(self.metadata.get("total_steps", 0)),
                    "metadata": {"tool_arguments": arguments},
                },
            )
            if isawaitable(pre_result):
                pre_result = await pre_result

            continue_pipeline = True
            if isinstance(pre_result, dict):
                continue_pipeline = bool(pre_result.get("continue_pipeline", True))
            else:
                continue_pipeline = bool(getattr(pre_result, "continue_pipeline", True))
            if continue_pipeline is False:
                completed_at = utcnow()
                self.history.append(
                    AgentExecutionRecord(
                        step_index=self.current_step_index,
                        agent_name=self.metadata.get("current_agent", "unknown-agent"),
                        started_at=started_at,
                        completed_at=completed_at,
                        success=False,
                        message="tool blocked by hook",
                        tool_name=tool_name,
                        tool_arguments=arguments,
                        error="tool blocked by PRE_COMMAND_RUN hook",
                    )
                )
                raise PermissionError(f"tool blocked by PRE_COMMAND_RUN hook: {tool_name}")
        try:
            result = await self.registry.execute(
                ToolExecutionPlan(
                    tool_name=tool_name,
                    arguments=arguments,
                    origin=ToolExecutionOrigin.AGENT,
                ),
                context={**self.metadata, "session": self.session},
            )
        except Exception as exc:
            completed_at = utcnow()
            if hook_dispatch is not None and self.metadata.get("hooks_post_dispatched") is not True:
                post_result = hook_dispatch(
                    HookEvent.POST_COMMAND_RUN,
                    {
                        "session_id": self.session.id,
                        "turn_id": int(self.metadata.get("turn_id", 0)),
                        "command": tool_name,
                        "route_tool": tool_name,
                        "status": "failed",
                        "exit_code": 1,
                        "timed_out": False,
                        "duration_s": 0.0,
                        "stdout_chars": 0,
                        "stderr_chars": len(str(exc)),
                    },
                )
                if isawaitable(post_result):
                    await post_result
            self.history.append(
                AgentExecutionRecord(
                    step_index=self.current_step_index,
                    agent_name=self.metadata.get("current_agent", "unknown-agent"),
                    started_at=started_at,
                    completed_at=completed_at,
                    success=False,
                    message="tool execution failed",
                    tool_name=tool_name,
                    tool_arguments=arguments,
                    error=str(exc),
                )
            )
            raise

        completed_at = utcnow()
        if hook_dispatch is not None and self.metadata.get("hooks_post_dispatched") is not True:
            post_result = hook_dispatch(
                HookEvent.POST_COMMAND_RUN,
                {
                    "session_id": self.session.id,
                    "turn_id": int(self.metadata.get("turn_id", 0)),
                    "command": tool_name,
                    "route_tool": tool_name,
                    "status": "completed" if result.success else "failed",
                    "exit_code": 0 if result.success else 1,
                    "timed_out": False,
                    "duration_s": 0.0,
                    "stdout_chars": len(result.output or ""),
                    "stderr_chars": len(result.error or ""),
                },
            )
            if isawaitable(post_result):
                await post_result
        self.history.append(
            AgentExecutionRecord(
                step_index=self.current_step_index,
                agent_name=self.metadata.get("current_agent", "unknown-agent"),
                started_at=started_at,
                completed_at=completed_at,
                success=result.success,
                message="tool execution completed",
                tool_name=tool_name,
                tool_arguments=arguments,
                tool_result=result,
            )
        )
        return result

