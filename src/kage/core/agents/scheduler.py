"""Parallel agent scheduler with dependency-aware execution."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from kage.utils import utcnow

from .agent import AgentResult, AgentTerminationSignal, BaseAgent
from .context import AgentContext, AgentExecutionRecord
from .memory import WorkflowMemory

AgentDependencyRef = str | type[BaseAgent] | BaseAgent


def _name_from_ref(ref: AgentDependencyRef) -> str:
    if isinstance(ref, str):
        return ref
    if isinstance(ref, BaseAgent):
        return ref.name
    return str(getattr(ref, "name", getattr(ref, "__name__", "")))


@dataclass(slots=True)
class DependencyGraph:
    """Dependency graph for agents within a parallel group."""

    dependencies: dict[AgentDependencyRef, list[AgentDependencyRef]] = field(default_factory=dict)

    def resolve(self, agents: list[BaseAgent]) -> dict[str, set[str]]:
        """Resolve graph references to normalized agent-name dependencies."""
        known = {agent.name for agent in agents}
        resolved: dict[str, set[str]] = {agent.name: set() for agent in agents}
        for node_ref, dep_refs in self.dependencies.items():
            node_name = _name_from_ref(node_ref)
            if node_name not in known:
                continue
            for dep_ref in dep_refs:
                dep_name = _name_from_ref(dep_ref)
                if dep_name in known and dep_name != node_name:
                    resolved[node_name].add(dep_name)
        return resolved

    def topological_batches(self, agents: list[BaseAgent]) -> list[list[BaseAgent]]:
        """Return dependency-respecting execution batches."""
        order = {agent.name: index for index, agent in enumerate(agents)}
        by_name = {agent.name: agent for agent in agents}
        pending = self.resolve(agents)
        batches: list[list[BaseAgent]] = []

        while pending:
            ready_names = [name for name, deps in pending.items() if not deps]
            ready_names.sort(key=lambda name: order.get(name, 0))
            if not ready_names:
                raise ValueError("Cycle detected in parallel agent dependency graph")

            batches.append([by_name[name] for name in ready_names])
            for done in ready_names:
                pending.pop(done, None)
            for deps in pending.values():
                deps.difference_update(ready_names)

        return batches


@dataclass(slots=True)
class ParallelAgentGroup:
    """A dependency-aware parallel execution group inside a pipeline."""

    agents: list[BaseAgent]
    name: str = "parallel-group"
    dependencies: DependencyGraph | dict[AgentDependencyRef, list[AgentDependencyRef]] | None = None

    def dependency_graph(self) -> DependencyGraph:
        if isinstance(self.dependencies, DependencyGraph):
            return self.dependencies
        if isinstance(self.dependencies, dict):
            return DependencyGraph(dependencies=self.dependencies)
        return DependencyGraph()


@dataclass(slots=True)
class ParallelAgentExecution:
    """Execution payload for one parallel agent run."""

    agent: BaseAgent
    context: AgentContext
    started_at: Any
    completed_at: Any
    result: AgentResult | None
    success: bool
    terminated_early: bool
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MergedAgentResult:
    """Merged output for a completed parallel group."""

    success: bool
    terminated_early: bool
    outputs: list[dict[str, Any]]
    errors: list[str]
    history: list[AgentExecutionRecord]
    merged_memory: WorkflowMemory
    results_by_agent: dict[str, AgentResult]


def _merge_workflow_memory(target: WorkflowMemory, source: WorkflowMemory, *, agent_name: str) -> None:
    for finding in source.findings:
        if finding not in target.findings:
            target.findings.append(finding)

    for note in source.notes:
        if note not in target.notes:
            target.notes.append(note)

    for target_item in source.targets:
        if target_item not in target.targets:
            target.targets.append(target_item)

    for key, value in source.artifacts.items():
        if key not in target.artifacts:
            target.artifacts[key] = value
            continue
        if target.artifacts[key] == value:
            continue
        conflict_key = f"{key}__{agent_name}"
        target.artifacts[conflict_key] = value

    for key, score in source.confidence_scores.items():
        current = target.confidence_scores.get(key)
        if current is None or score > current:
            target.confidence_scores[key] = score

    for output in source.intermediate_outputs:
        target.intermediate_outputs.append(output)


def aggregate_results(
    executions: list[ParallelAgentExecution],
    *,
    base_memory: WorkflowMemory,
    base_history_len: int,
    execution_order: list[str],
) -> MergedAgentResult:
    """Aggregate results from parallel agent executions deterministically."""
    order = {name: index for index, name in enumerate(execution_order)}
    ordered = sorted(executions, key=lambda item: order.get(item.agent.name, 10_000))

    merged_memory = deepcopy(base_memory)
    outputs: list[dict[str, Any]] = []
    errors: list[str] = []
    history: list[AgentExecutionRecord] = []
    results_by_agent: dict[str, AgentResult] = {}
    terminated_early = False

    for execution in ordered:
        history.extend(execution.context.history[base_history_len:])
        _merge_workflow_memory(merged_memory, execution.context.memory, agent_name=execution.agent.name)

        if execution.result is not None:
            outputs.append(execution.result.output)
            results_by_agent[execution.agent.name] = execution.result
            if execution.result.termination == AgentTerminationSignal.STOP_PIPELINE:
                terminated_early = True

        if execution.errors:
            errors.extend(execution.errors)
            terminated_early = True
        if execution.terminated_early:
            terminated_early = True

    return MergedAgentResult(
        success=len(errors) == 0,
        terminated_early=terminated_early,
        outputs=outputs,
        errors=errors,
        history=history,
        merged_memory=merged_memory,
        results_by_agent=results_by_agent,
    )


@dataclass(slots=True)
class ParallelAgentScheduler:
    """Schedules and executes parallel agent groups with dependency fanout/fanin."""

    async def execute_group(
        self,
        *,
        group: ParallelAgentGroup,
        parent_context: AgentContext,
        step_index: int,
        total_steps: int,
        turn_id: int,
        recorder: Any,
        execute_agent_step: Any,
        pipeline_name: str,
    ) -> MergedAgentResult:
        recorder.record(
            event_type="parallel_group_started",
            turn_id=turn_id,
            payload={
                "group_name": group.name,
                "agent_count": len(group.agents),
                "pipeline_name": pipeline_name,
            },
        )

        try:
            batches = group.dependency_graph().topological_batches(group.agents)
        except ValueError as exc:
            recorder.record(
                event_type="parallel_group_completed",
                turn_id=turn_id,
                payload={
                    "group_name": group.name,
                    "success": False,
                    "error": str(exc),
                    "pipeline_name": pipeline_name,
                },
            )
            return MergedAgentResult(
                success=False,
                terminated_early=True,
                outputs=[],
                errors=[str(exc)],
                history=[],
                merged_memory=deepcopy(parent_context.memory),
                results_by_agent={},
            )

        working_memory = deepcopy(parent_context.memory)
        all_executions: list[ParallelAgentExecution] = []
        group_terminated = False

        for batch_index, batch in enumerate(batches):
            tasks = [
                self._run_parallel_agent(
                    agent=agent,
                    parent_context=parent_context,
                    step_index=step_index,
                    total_steps=total_steps,
                    turn_id=turn_id,
                    recorder=recorder,
                    execute_agent_step=execute_agent_step,
                    memory_snapshot=working_memory,
                    group_name=group.name,
                )
                for agent in batch
            ]
            batch_executions = await asyncio.gather(*tasks)
            all_executions.extend(batch_executions)

            batch_merged = aggregate_results(
            batch_executions,
            base_memory=working_memory,
            base_history_len=len(parent_context.history),
            execution_order=[agent.name for agent in batch],
        )
            working_memory = batch_merged.merged_memory
            recorder.record(
                event_type="parallel_merge_completed",
                turn_id=turn_id,
                payload={
                    "group_name": group.name,
                    "batch_index": batch_index,
                    "merged_outputs": len(batch_merged.outputs),
                    "error_count": len(batch_merged.errors),
                },
            )
            if batch_merged.terminated_early:
                group_terminated = True
                break

        merged = aggregate_results(
            all_executions,
            base_memory=deepcopy(parent_context.memory),
            base_history_len=len(parent_context.history),
            execution_order=[agent.name for agent in group.agents],
        )
        merged = MergedAgentResult(
            success=merged.success and not group_terminated,
            terminated_early=merged.terminated_early or group_terminated,
            outputs=merged.outputs,
            errors=merged.errors,
            history=merged.history,
            merged_memory=working_memory,
            results_by_agent=merged.results_by_agent,
        )

        recorder.record(
            event_type="parallel_group_completed",
            turn_id=turn_id,
            payload={
                "group_name": group.name,
                "success": merged.success,
                "terminated_early": merged.terminated_early,
                "output_count": len(merged.outputs),
                "error_count": len(merged.errors),
                "pipeline_name": pipeline_name,
            },
        )
        return merged

    async def _run_parallel_agent(
        self,
        *,
        agent: BaseAgent,
        parent_context: AgentContext,
        step_index: int,
        total_steps: int,
        turn_id: int,
        recorder: Any,
        execute_agent_step: Any,
        memory_snapshot: WorkflowMemory,
        group_name: str,
    ) -> ParallelAgentExecution:
        local_metadata = dict(parent_context.metadata)
        local_metadata["current_agent"] = agent.name
        local_metadata["total_steps"] = total_steps
        local_metadata["parallel_group"] = group_name
        local_metadata["agent_tool_access_scope"] = list(agent.tool_access_scope)
        local_context = AgentContext(
            session=parent_context.session,
            registry=parent_context.registry,
            memory=deepcopy(memory_snapshot),
            metadata=local_metadata,
        )
        local_context.current_step_index = step_index
        local_context.history = [deepcopy(record) for record in parent_context.history]

        started_at = utcnow()
        recorder.record(
            event_type="parallel_agent_started",
            turn_id=turn_id,
            payload={"group_name": group_name, "agent_name": agent.name},
        )
        result, terminated_early, errors = await execute_agent_step(
            agent=agent,
            context=local_context,
            step_index=step_index,
        )
        completed_at = utcnow()
        recorder.record(
            event_type="parallel_agent_completed",
            turn_id=turn_id,
            duration_ms=(completed_at - started_at).total_seconds() * 1000.0,
            payload={
                "group_name": group_name,
                "agent_name": agent.name,
                "success": len(errors) == 0,
                "terminated_early": terminated_early,
                "error_count": len(errors),
            },
        )
        return ParallelAgentExecution(
            agent=agent,
            context=local_context,
            started_at=started_at,
            completed_at=completed_at,
            result=result,
            success=len(errors) == 0,
            terminated_early=terminated_early,
            errors=errors,
        )

