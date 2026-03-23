"""Workflow executor that runs templates through AgentOrchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kage.core.agents import AgentContext, AgentOrchestrator, OrchestrationResult
from kage.core.observability import TraceSeverity, recorder_for_session

from .registry import WorkflowRegistry, WorkflowRegistryError


@dataclass(slots=True)
class WorkflowExecutor:
    """Executes named workflow templates through AgentOrchestrator."""

    orchestrator: AgentOrchestrator
    registry: WorkflowRegistry

    async def run(
        self,
        workflow_name: str,
        *,
        context: AgentContext,
        parameters: dict[str, Any] | None = None,
    ) -> OrchestrationResult:
        """Run one registered workflow and return orchestration result."""
        turn_id = int(context.metadata.get("turn_id", 0))
        recorder = recorder_for_session(context.session, component="workflow_executor")
        template = self.registry.get(workflow_name)
        if template is None:
            recorder.record(
                event_type="workflow_failed",
                turn_id=turn_id,
                severity=TraceSeverity.ERROR,
                payload={"workflow_name": workflow_name, "error": "unknown workflow template"},
            )
            raise WorkflowRegistryError(f"Unknown workflow template: {workflow_name}")

        try:
            self.registry.ensure_valid(template)
        except Exception as exc:
            recorder.record(
                event_type="workflow_failed",
                turn_id=turn_id,
                severity=TraceSeverity.ERROR,
                payload={"workflow_name": template.name, "error": str(exc)},
            )
            raise
        resolved_parameters = {**template.default_parameters, **(parameters or {})}

        recorder.record(
            event_type="workflow_started",
            turn_id=turn_id,
            payload={
                "workflow_name": template.name,
                "required_tools": list(template.required_tools),
                "required_middleware": self.registry.resolve_middleware_requirements(
                    template, parameters=resolved_parameters
                ),
            },
        )

        pipeline = template.build_pipeline()
        context.metadata = {
            **context.metadata,
            "workflow_name": template.name,
            "workflow_parameters": resolved_parameters,
            "policy_overrides": dict(template.policy_overrides),
            **resolved_parameters,
        }

        try:
            result = await self.orchestrator.run(pipeline, context)
        except Exception as exc:
            recorder.record(
                event_type="workflow_failed",
                turn_id=turn_id,
                severity=TraceSeverity.ERROR,
                payload={"workflow_name": template.name, "error": str(exc)},
            )
            raise

        recorder.record(
            event_type="workflow_completed",
            turn_id=turn_id,
            payload={
                "workflow_name": template.name,
                "success": result.success,
                "terminated_early": result.terminated_early,
                "error_count": len(result.errors),
            },
        )
        if not result.success:
            recorder.record(
                event_type="workflow_failed",
                turn_id=turn_id,
                severity=TraceSeverity.ERROR,
                payload={"workflow_name": template.name, "errors": list(result.errors)},
            )
        return result

