"""Policy evaluation engine with observability integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kage.core.observability import TraceSeverity, recorder_for_session_id

from .context import PolicyContext
from .decision import PolicyAction, PolicyDecision
from .registry import PolicyRegistry
from .rules import default_policy_rules


def _to_trace_severity(decision: PolicyAction) -> TraceSeverity:
    if decision == PolicyAction.DENY:
        return TraceSeverity.ERROR
    if decision == PolicyAction.ASK:
        return TraceSeverity.WARNING
    return TraceSeverity.INFO


@dataclass(slots=True)
class PolicyEngine:
    """Coordinates layered policy evaluation and emits trace diagnostics."""

    registry: PolicyRegistry = field(default_factory=PolicyRegistry)
    _group_overrides: dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.registry.list_rules():
            self.registry.register_many(default_policy_rules())

    def override_rule(self, rule_id: str, decision: PolicyDecision) -> None:
        self.registry.set_override(rule_id, decision)

    def set_group_enabled(self, group: str, enabled: bool) -> None:
        self._group_overrides[group] = enabled
        if enabled:
            self.registry.enable_group(group)
        else:
            self.registry.disable_group(group)

    def evaluate(self, context: PolicyContext) -> PolicyDecision:
        decision = self.registry.evaluate(context)
        self._emit_policy_trace(context=context, decision=decision)
        return decision

    @staticmethod
    def context_from_tool_execution(
        *,
        tool_name: str,
        arguments: dict[str, Any],
        metadata: dict[str, Any],
        dangerous: bool,
        requires_approval: bool,
        tool_tags: list[str],
        tool_scopes: list[str],
    ) -> PolicyContext:
        session_metadata_raw = metadata.get("session_metadata", {})
        session_metadata = session_metadata_raw if isinstance(session_metadata_raw, dict) else {}
        filesystem_path = arguments.get("path")
        filesystem_path_str = filesystem_path if isinstance(filesystem_path, str) else None
        network_target = PolicyEngine._extract_network_target(arguments)
        return PolicyContext(
            tool_name=tool_name,
            execution_phase=str(metadata.get("phase", "tool_execution")),
            agent_name=metadata.get("current_agent") if isinstance(metadata.get("current_agent"), str) else None,
            session_id=metadata.get("session_id") if isinstance(metadata.get("session_id"), str) else None,
            session_metadata=session_metadata,
            filesystem_path=filesystem_path_str,
            network_target=network_target,
            plugin_source=PolicyEngine._extract_plugin_source(tool_name, metadata),
            mcp_server=PolicyEngine._extract_mcp_server(tool_name, metadata),
            workspace_root=metadata.get("workspace_root"),
            arguments=arguments,
            tool_tags=tool_tags,
            tool_scopes=tool_scopes,
            dangerous=dangerous,
            requires_approval=requires_approval,
            metadata={
                "agent_tool_access_scope": metadata.get("agent_tool_access_scope", []),
                "turn_id": metadata.get("turn_id", 0),
            },
        )

    def evaluate_tool_execution(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        metadata: dict[str, Any],
        dangerous: bool,
        requires_approval: bool,
        tool_tags: list[str],
        tool_scopes: list[str],
    ) -> PolicyDecision:
        """Convenience API for evaluating one tool execution context."""
        context = self.context_from_tool_execution(
            tool_name=tool_name,
            arguments=arguments,
            metadata=metadata,
            dangerous=dangerous,
            requires_approval=requires_approval,
            tool_tags=tool_tags,
            tool_scopes=tool_scopes,
        )
        return self.evaluate(context)

    @staticmethod
    def _extract_network_target(arguments: dict[str, Any]) -> str | None:
        for key in ("target", "host", "url", "address"):
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _extract_plugin_source(tool_name: str, metadata: dict[str, Any]) -> str | None:
        explicit = metadata.get("plugin_source")
        if isinstance(explicit, str) and explicit:
            return explicit
        if tool_name.startswith("plugin."):
            parts = tool_name.split(".")
            if len(parts) >= 3:
                return parts[1]
        return None

    @staticmethod
    def _extract_mcp_server(tool_name: str, metadata: dict[str, Any]) -> str | None:
        explicit = metadata.get("mcp_server")
        if isinstance(explicit, str) and explicit:
            return explicit
        if tool_name.startswith("mcp."):
            parts = tool_name.split(".")
            if len(parts) >= 3:
                return parts[1]
        return None

    def _emit_policy_trace(self, *, context: PolicyContext, decision: PolicyDecision) -> None:
        if context.session_id is None:
            return
        recorder = recorder_for_session_id(context.session_id, component="policy_engine")
        if recorder is None:
            return
        turn_id_raw = context.metadata.get("turn_id", context.session_metadata.get("turn_id", 0))
        turn_id = turn_id_raw if isinstance(turn_id_raw, int) else 0
        recorder.record(
            event_type="policy_decision",
            turn_id=turn_id,
            severity=_to_trace_severity(decision.decision),
            payload={
                "tool_name": context.tool_name,
                "decision": decision.decision.value,
                "reason": decision.reason,
                "rule_id": decision.rule_id,
                "requires_confirmation": decision.requires_confirmation,
                "sandbox_required": decision.sandbox_required,
            },
        )

