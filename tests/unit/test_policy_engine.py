"""Tests for policy graph runtime and integration."""

from __future__ import annotations

import pytest

from kage.core.models import Session
from kage.core.policy import (
    PolicyAction,
    PolicyContext,
    PolicyDecision,
    PolicyEngine,
    PolicyRegistry,
    PolicyRule,
    PolicySeverity,
)
from kage.core.tools import ToolExecutionPlan, ToolRegistry, register_builtin_tools


class _AllowRule(PolicyRule):
    def __init__(self) -> None:
        super().__init__(rule_id="r.allow", description="allow", priority=50)

    def evaluate(self, _context: PolicyContext) -> PolicyDecision:
        return PolicyDecision.allow(reason="allow", rule_id=self.rule_id)


class _AskRule(PolicyRule):
    def __init__(self) -> None:
        super().__init__(rule_id="r.ask", description="ask", priority=40)

    def evaluate(self, _context: PolicyContext) -> PolicyDecision:
        return PolicyDecision.ask(reason="ask", rule_id=self.rule_id)


class _DenyRule(PolicyRule):
    def __init__(self) -> None:
        super().__init__(rule_id="r.deny", description="deny", priority=60)

    def evaluate(self, _context: PolicyContext) -> PolicyDecision:
        return PolicyDecision.deny(reason="deny", rule_id=self.rule_id)


def _tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    return registry


def test_rule_priority_resolution() -> None:
    registry = PolicyRegistry()
    registry.register(_AllowRule())
    registry.register(_AskRule())
    decision = registry.evaluate(PolicyContext(tool_name="builtin.session.note", execution_phase="tool"))
    assert decision.decision == PolicyAction.ASK
    assert decision.rule_id == "r.ask"


def test_conflict_handling_prefers_strictest() -> None:
    registry = PolicyRegistry()
    registry.register(_AllowRule())
    registry.register(_DenyRule())
    decision = registry.evaluate(PolicyContext(tool_name="builtin.session.note", execution_phase="tool"))
    assert decision.decision == PolicyAction.DENY
    assert decision.rule_id == "r.deny"


def test_decision_propagation_from_engine() -> None:
    registry = PolicyRegistry()
    registry.register(_DenyRule())
    engine = PolicyEngine(registry=registry)
    decision = engine.evaluate(
        PolicyContext(
            tool_name="builtin.session.note",
            execution_phase="tool",
            session_id="s1",
            session_metadata={"turn_id": 3},
        )
    )
    assert decision.decision == PolicyAction.DENY
    assert decision.reason == "deny"


async def test_tool_execution_interception_denies_outside_workspace(tmp_path) -> None:
    registry = _tool_registry()
    outside = tmp_path.parent / "outside.txt"
    plan = ToolExecutionPlan(
        tool_name="builtin.fs.write",
        arguments={"path": str(outside), "content": "blocked"},
    )
    with pytest.raises(Exception) as exc:
        await registry.execute(
            plan,
            context={
                "workspace_root": tmp_path,
                "session_metadata": {},
                "session": Session(),
                "turn_id": 11,
            },
        )
    assert "denied by policy" in str(exc.value)


async def test_trace_emission_for_policy_decision(tmp_path) -> None:
    session = Session()
    registry = _tool_registry()
    plan = ToolExecutionPlan(
        tool_name="builtin.shell.run",
        arguments={"command": "echo policy"},
    )
    await registry.execute(
        plan,
        context={
            "workspace_root": tmp_path,
            "session_metadata": {"turn_id": 12},
            "session": session,
            "turn_id": 12,
        },
    )
    policy_events = [event for event in session.trace.get_turn(12) if event.event_type == "policy_decision"]
    assert policy_events
    assert policy_events[-1].payload["decision"] in {"ask", "deny", "allow"}


def test_rule_overrides_and_group_disable() -> None:
    engine = PolicyEngine()
    engine.set_group_enabled("mcp", False)
    context = PolicyContext(
        tool_name="mcp.demo.scan",
        execution_phase="tool",
        session_metadata={"allowed_mcp_servers": []},
    )
    decision = engine.evaluate(context)
    assert decision.decision in {PolicyAction.ALLOW, PolicyAction.ASK}

    engine.override_rule(
        "policy.dangerous_tool_confirmation",
        PolicyDecision(
            decision=PolicyAction.DENY,
            reason="override",
            rule_id="policy.dangerous_tool_confirmation",
            severity=PolicySeverity.ERROR,
            requires_confirmation=False,
            sandbox_required=True,
        ),
    )
    decision2 = engine.evaluate(
        PolicyContext(
            tool_name="builtin.shell.run",
            execution_phase="tool",
            dangerous=True,
            requires_approval=True,
        )
    )
    assert decision2.decision == PolicyAction.DENY

