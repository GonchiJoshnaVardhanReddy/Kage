"""Agent orchestrator runtime with sequential + parallel group scheduling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kage.core.hooks import HookEvent, HookManager
from kage.core.memory import default_compactor, get_or_create_memory_store, persist_memory_store
from kage.core.observability import TraceSeverity, recorder_for_session
from kage.utils import utcnow

from .agent import AgentResult, AgentTerminationSignal, BaseAgent
from .context import AgentContext, AgentExecutionRecord
from .pipeline import AgentPipeline, OrchestrationResult
from .scheduler import ParallelAgentGroup, ParallelAgentScheduler


@dataclass(slots=True)
class AgentOrchestrator:
    """Executes one agent pipeline sequentially with optional parallel groups."""

    hooks: HookManager | None = None
    scheduler: ParallelAgentScheduler = field(default_factory=ParallelAgentScheduler)

    async def run(self, pipeline: AgentPipeline, context: AgentContext) -> OrchestrationResult:
        """Execute an agent pipeline and return aggregate result."""
        started_at = utcnow()
        turn_id = int(context.metadata.get("turn_id", 0))
        recorder = recorder_for_session(context.session, component="agent_orchestrator")
        recorder.record(
            event_type="agent_started",
            turn_id=turn_id,
            payload={"pipeline_name": pipeline.name, "total_steps": len(pipeline.agents)},
        )
        errors: list[str] = []
        outputs: list[dict[str, Any]] = []
        terminated_early = False

        for step_index, step in enumerate(pipeline.agents):
            context.current_step_index = step_index
            context.metadata["total_steps"] = len(pipeline.agents)

            if isinstance(step, ParallelAgentGroup):
                merged = await self.scheduler.execute_group(
                    group=step,
                    parent_context=context,
                    step_index=step_index,
                    total_steps=len(pipeline.agents),
                    turn_id=turn_id,
                    recorder=recorder,
                    execute_agent_step=self._execute_one_agent_step,
                    pipeline_name=pipeline.name,
                )
                context.history.extend(merged.history)
                outputs.extend(merged.outputs)
                context.memory = merged.merged_memory
                if merged.errors:
                    errors.extend(merged.errors)
                if merged.terminated_early:
                    terminated_early = True
                    break
                continue

            agent = step
            context.metadata["current_agent"] = agent.name
            context.metadata["agent_tool_access_scope"] = list(agent.tool_access_scope)
            agent_result, step_terminated, step_errors = await self._execute_one_agent_step(
                agent=agent,
                context=context,
                step_index=step_index,
            )
            if agent_result is not None:
                outputs.append(agent_result.output)
            if step_errors:
                errors.extend(step_errors)
            if step_terminated:
                terminated_early = True
                break

        completed_at = utcnow()
        memory_store = get_or_create_memory_store(context.session)
        compactor = default_compactor(memory_store)
        transcript_excerpts: list[str] = []
        for output in outputs[-8:]:
            if isinstance(output, dict):
                transcript_excerpts.append(str(output))
        compactor.compact(
            session=context.session,
            workflow_memory=context.memory,
            transcript_excerpts=transcript_excerpts,
            turn_id=turn_id,
            trigger="workflow_terminated" if terminated_early else "agent_pipeline_completed",
        )
        persist_memory_store(context.session, memory_store)
        recorder.record(
            event_type="agent_completed",
            turn_id=turn_id,
            duration_ms=(completed_at - started_at).total_seconds() * 1000.0,
            payload={
                "pipeline_name": pipeline.name,
                "success": len(errors) == 0,
                "terminated_early": terminated_early,
            },
        )
        if terminated_early:
            recorder.record(
                event_type="workflow_terminated",
                turn_id=turn_id,
                payload={"pipeline_name": pipeline.name, "reason": "early_termination"},
            )
        return OrchestrationResult(
            success=(len(errors) == 0),
            pipeline_name=pipeline.name,
            terminated_early=terminated_early,
            started_at=started_at,
            completed_at=completed_at,
            history=list(context.history),
            aggregated_outputs=outputs,
            memory=context.memory,
            errors=errors,
        )

    async def _execute_one_agent_step(
        self,
        *,
        agent: BaseAgent,
        context: AgentContext,
        step_index: int,
    ) -> tuple[AgentResult | None, bool, list[str]]:
        turn_id = int(context.metadata.get("turn_id", 0))
        recorder = recorder_for_session(context.session, component="agent_orchestrator")
        step_started = utcnow()
        recorder.record(
            event_type="pipeline_step_started",
            turn_id=turn_id,
            payload={"step_index": step_index, "agent_name": agent.name},
        )
        recorder.record(
            event_type="agent_step_started",
            turn_id=turn_id,
            payload={"agent_name": agent.name, "step_index": step_index},
        )

        errors: list[str] = []
        terminated_early = False
        try:
            agent_result = await agent.run(context)
        except Exception as exc:
            step_completed = utcnow()
            duration_ms = (step_completed - step_started).total_seconds() * 1000.0
            context.history.append(
                AgentExecutionRecord(
                    step_index=step_index,
                    agent_name=agent.name,
                    started_at=step_started,
                    completed_at=step_completed,
                    success=False,
                    message="agent failed",
                    error=str(exc),
                )
            )
            recorder.record(
                event_type="pipeline_step_completed",
                turn_id=turn_id,
                duration_ms=duration_ms,
                severity=TraceSeverity.ERROR,
                payload={"step_index": step_index, "agent_name": agent.name, "success": False, "error": str(exc)},
            )
            recorder.record(
                event_type="agent_step_completed",
                turn_id=turn_id,
                duration_ms=duration_ms,
                severity=TraceSeverity.ERROR,
                payload={"agent_name": agent.name, "step_index": step_index, "success": False},
            )
            errors.append(f"{agent.name}: {exc}")
            return None, True, errors

        for tool_name, arguments in agent_result.tool_calls:
            pre_allowed = await self._dispatch_pre_command_hook(
                context=context,
                agent=agent,
                tool_name=tool_name,
                arguments=arguments,
            )
            if not pre_allowed:
                errors.append(f"{agent.name}: tool blocked by hook: {tool_name}")
                terminated_early = True
                break

            try:
                context.metadata["hooks_pre_dispatched"] = True
                context.metadata["hooks_post_dispatched"] = True
                tool_result = await context.execute_tool(tool_name, arguments)
            except Exception as exc:
                await self._dispatch_post_command_hook(
                    context=context,
                    tool_name=tool_name,
                    success=False,
                    error_text=str(exc),
                )
                errors.append(f"{agent.name}: tool failed: {tool_name}: {exc}")
                terminated_early = True
                break
            finally:
                context.metadata.pop("hooks_pre_dispatched", None)
                context.metadata.pop("hooks_post_dispatched", None)

            agent_result.tool_results.append(tool_result)
            await self._dispatch_post_command_hook(
                context=context,
                tool_name=tool_name,
                success=tool_result.success,
                error_text=tool_result.error or "",
            )
            context.memory.add_intermediate_output(
                {
                    "agent": agent.name,
                    "tool_name": tool_name,
                    "success": tool_result.success,
                    "output": tool_result.output,
                    "data": tool_result.data,
                }
            )

        step_completed = utcnow()
        duration_ms = (step_completed - step_started).total_seconds() * 1000.0
        context.history.append(
            AgentExecutionRecord(
                step_index=step_index,
                agent_name=agent.name,
                started_at=step_started,
                completed_at=step_completed,
                success=agent_result.success and not terminated_early and len(errors) == 0,
                message=agent_result.message,
            )
        )
        recorder.record(
            event_type="pipeline_step_completed",
            turn_id=turn_id,
            duration_ms=duration_ms,
            payload={
                "step_index": step_index,
                "agent_name": agent.name,
                "success": (agent_result.success and len(errors) == 0),
            },
        )
        recorder.record(
            event_type="agent_step_completed",
            turn_id=turn_id,
            duration_ms=duration_ms,
            payload={
                "agent_name": agent.name,
                "step_index": step_index,
                "success": (agent_result.success and len(errors) == 0),
            },
        )

        if agent_result.termination == AgentTerminationSignal.STOP_PIPELINE:
            recorder.record(
                event_type="termination_signal",
                turn_id=turn_id,
                severity=TraceSeverity.WARNING,
                payload={"agent_name": agent.name, "signal": agent_result.termination.value},
            )
            terminated_early = True

        if terminated_early:
            recorder.record(
                event_type="workflow_terminated",
                turn_id=turn_id,
                severity=TraceSeverity.WARNING,
                payload={"agent_name": agent.name, "reason": "tool_failure_or_block"},
            )
        return agent_result, terminated_early, errors

    async def _dispatch_pre_command_hook(
        self,
        *,
        context: AgentContext,
        agent: BaseAgent,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> bool:
        if self.hooks is None:
            return True
        pre_metadata: dict[str, Any] = {"tool_arguments": arguments, "agent_name": agent.name}
        if "description" in context.metadata:
            pre_metadata["description"] = context.metadata["description"]
        result = await self.hooks.dispatch(
            HookEvent.PRE_COMMAND_RUN,
            {
                "session_id": context.session.id,
                "turn_id": int(context.metadata.get("turn_id", 0)),
                "command": tool_name,
                "description": agent.description,
                "route_tool": tool_name,
                "route_reasoning": "AgentOrchestrator ToolRegistry dispatch",
                "phase": "agent_pipeline",
                "step_index": context.current_step_index + 1,
                "total_steps": int(context.metadata.get("total_steps", 0)),
                "metadata": pre_metadata,
            },
        )
        return result.continue_pipeline

    async def _dispatch_post_command_hook(
        self,
        *,
        context: AgentContext,
        tool_name: str,
        success: bool,
        error_text: str,
    ) -> None:
        if self.hooks is None:
            return
        await self.hooks.dispatch(
            HookEvent.POST_COMMAND_RUN,
            {
                "session_id": context.session.id,
                "turn_id": int(context.metadata.get("turn_id", 0)),
                "command": tool_name,
                "route_tool": tool_name,
                "status": "completed" if success else "failed",
                "exit_code": 0 if success else 1,
                "timed_out": False,
                "duration_s": 0.0,
                "stdout_chars": 0,
                "stderr_chars": len(error_text),
            },
        )

