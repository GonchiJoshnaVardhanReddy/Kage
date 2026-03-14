"""Tool registry runtime for deterministic schema-based dispatch."""

from __future__ import annotations

import builtins
import copy
import json
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from pydantic import TypeAdapter, ValidationError

from kage.core.observability import TraceSeverity, recorder_from_context
from kage.core.policy import PolicyAction, PolicyEngine
from kage.core.tools.models import (
    ToolExecutionError,
    ToolExecutionPlan,
    ToolExecutionResult,
    ToolRegistryError,
    ToolSchema,
    ToolValidationError,
)


@dataclass(slots=True)
class ToolValidationResult:
    """Result of argument validation against a tool schema."""

    valid: bool
    arguments: dict[str, Any]
    errors: list[str]


class ToolRegistry:
    """In-memory registry of executable tool schemas."""

    def __init__(self) -> None:
        self._schemas: OrderedDict[str, ToolSchema] = OrderedDict()
        self._json_cache: dict[str, TypeAdapter[Any]] = {}
        self._policy_engine = PolicyEngine()

    def register(self, tool_schema: ToolSchema) -> None:
        """Register (or replace) a tool schema by fully-qualified tool name."""
        self._schemas[tool_schema.name] = tool_schema
        self._json_cache.pop(tool_schema.name, None)

    def unregister(self, tool_name: str) -> bool:
        """Remove a registered tool."""
        existed = tool_name in self._schemas
        if existed:
            del self._schemas[tool_name]
            self._json_cache.pop(tool_name, None)
        return existed

    def get(self, tool_name: str) -> ToolSchema | None:
        """Get one tool schema by name."""
        return self._schemas.get(tool_name)

    def list(self) -> builtins.list[ToolSchema]:
        """List all tools in registration order."""
        return list(self._schemas.values())

    def expose_to_llm(self) -> builtins.list[dict[str, object]]:
        """Return OpenAI-compatible function-tool schema payloads."""
        exposed: builtins.list[dict[str, object]] = []
        for schema in self._schemas.values():
            exposed.append(
                {
                    "type": "function",
                    "function": {
                        "name": schema.name,
                        "description": schema.description,
                        "parameters": copy.deepcopy(schema.parameter_schema),
                    },
                }
            )
        return exposed

    def validate_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolValidationResult:
        """Validate and normalize arguments for a tool schema."""
        schema = self.get(tool_name)
        if not schema:
            raise ToolRegistryError(f"Unknown tool: {tool_name}")
        if not isinstance(arguments, dict):
            raise ToolValidationError(f"Arguments for '{tool_name}' must be an object")

        properties = schema.parameter_schema.get("properties", {})
        required = set(schema.parameter_schema.get("required", []))

        errors: list[str] = []
        for field in sorted(required):
            if field not in arguments:
                errors.append(f"Missing required argument: {field}")

        additional_allowed = schema.parameter_schema.get("additionalProperties", True)
        if additional_allowed is False:
            unknown = sorted(key for key in arguments if key not in properties)
            for field in unknown:
                errors.append(f"Unexpected argument: {field}")

        try:
            adapter = self._json_cache.get(tool_name)
            if adapter is None:
                adapter = TypeAdapter(dict[str, Any])
                self._json_cache[tool_name] = adapter
            normalized_args = adapter.validate_python(arguments)
        except ValidationError as exc:
            errors.extend(msg.get("msg", "Invalid arguments") for msg in exc.errors())
            normalized_args = arguments

        return ToolValidationResult(valid=len(errors) == 0, arguments=normalized_args, errors=errors)

    async def execute(
        self,
        plan: ToolExecutionPlan,
        context: dict[str, Any] | None = None,
    ) -> ToolExecutionResult:
        """Execute one tool plan via schema-bound executor."""
        recorder = recorder_from_context(context, component="tool_registry")
        turn_id = 0
        if isinstance(context, dict):
            turn_id = int(context.get("turn_id", 0))

        if recorder is not None:
            recorder.record(
                event_type="tool_selected",
                turn_id=turn_id,
                payload={"tool_name": plan.tool_name, "origin": plan.origin.value},
            )
        schema = self.get(plan.tool_name)
        if not schema:
            if recorder is not None:
                recorder.record(
                    event_type="tool_failed",
                    turn_id=turn_id,
                    severity=TraceSeverity.ERROR,
                    payload={"tool_name": plan.tool_name, "error": "unknown tool"},
                )
            raise ToolExecutionError(f"Unknown tool in execution plan: {plan.tool_name}")
        if not schema.executor_binding.executor:
            if recorder is not None:
                recorder.record(
                    event_type="tool_failed",
                    turn_id=turn_id,
                    severity=TraceSeverity.ERROR,
                    payload={"tool_name": plan.tool_name, "error": "missing executor"},
                )
            raise ToolExecutionError(f"Tool '{plan.tool_name}' has no executor binding")

        validation = self.validate_arguments(plan.tool_name, plan.arguments)
        if not validation.valid:
            if recorder is not None:
                recorder.record(
                    event_type="tool_failed",
                    turn_id=turn_id,
                    severity=TraceSeverity.WARNING,
                    payload={"tool_name": plan.tool_name, "error": "; ".join(validation.errors)},
                )
            raise ToolValidationError(
                f"Invalid arguments for '{plan.tool_name}': {'; '.join(validation.errors)}"
            )

        plan_for_exec = plan.model_copy(update={"arguments": validation.arguments})
        executor = schema.executor_binding.executor

        call_context = context or {}
        policy_metadata = call_context if isinstance(call_context, dict) else {}
        if "session_id" not in policy_metadata:
            session_obj = policy_metadata.get("session")
            session_id = getattr(session_obj, "id", None)
            if isinstance(session_id, str):
                policy_metadata = {**policy_metadata, "session_id": session_id}
        if "session_metadata" in policy_metadata and isinstance(
            policy_metadata.get("session_metadata"), dict
        ):
            policy_metadata["session_metadata"].setdefault("turn_id", turn_id)
        policy_decision = self._policy_engine.evaluate_tool_execution(
            tool_name=plan.tool_name,
            arguments=plan_for_exec.arguments,
            metadata=policy_metadata,
            dangerous=schema.permissions.dangerous,
            requires_approval=(plan.approval_required or schema.permissions.requires_approval),
            tool_tags=list(schema.permissions.tags),
            tool_scopes=list(schema.permissions.scopes),
        )
        if policy_decision.decision == PolicyAction.DENY:
            if recorder is not None:
                recorder.record(
                    event_type="tool_failed",
                    turn_id=turn_id,
                    severity=TraceSeverity.ERROR,
                    payload={
                        "tool_name": plan.tool_name,
                        "error": f"policy denied ({policy_decision.rule_id}): {policy_decision.reason}",
                    },
                )
            raise ToolExecutionError(
                f"Tool '{plan.tool_name}' denied by policy ({policy_decision.rule_id}): "
                f"{policy_decision.reason}"
            )
        if policy_decision.decision == PolicyAction.ASK:
            if recorder is not None:
                recorder.record(
                    event_type="tool_selected",
                    turn_id=turn_id,
                    severity=TraceSeverity.WARNING,
                    payload={
                        "tool_name": plan.tool_name,
                        "policy_requires_confirmation": True,
                        "policy_rule_id": policy_decision.rule_id,
                    },
                )
            plan_for_exec = plan_for_exec.model_copy(update={"approval_required": True})

        try:
            if recorder is not None:
                recorder.record(
                    event_type="tool_executed",
                    turn_id=turn_id,
                    payload={"tool_name": plan.tool_name, "arguments": plan_for_exec.arguments},
                )
            raw_result = executor(plan_for_exec, call_context)
        except Exception as exc:
            if recorder is not None:
                recorder.record(
                    event_type="tool_failed",
                    turn_id=turn_id,
                    severity=TraceSeverity.ERROR,
                    payload={"tool_name": plan.tool_name, "error": str(exc)},
                )
            raise ToolExecutionError(f"Executor for '{plan.tool_name}' failed: {exc}") from exc

        result = await ToolExecutionResult.normalize(raw_result)
        if recorder is not None:
            recorder.record(
                event_type="tool_completed",
                turn_id=turn_id,
                payload={
                    "tool_name": plan.tool_name,
                    "success": result.success,
                    "error": result.error or "",
                },
            )
        if not result.success and result.error:
            if recorder is not None:
                recorder.record(
                    event_type="tool_retried",
                    turn_id=turn_id,
                    severity=TraceSeverity.WARNING,
                    payload={
                        "tool_name": plan.tool_name,
                        "reason": "failure_result_returned",
                        "retry_suggested": True,
                    },
                )
            raise ToolExecutionError(result.error)
        return result

    def to_json(self) -> str:
        """Serialize registered schemas for diagnostics."""
        return json.dumps([schema.model_dump(mode="json") for schema in self.list()])

