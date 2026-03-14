"""Tests for schema-based tool registry runtime."""

from __future__ import annotations

from pathlib import Path

import pytest

from kage.core.tools import (
    ToolExecutionPlan,
    ToolExecutionResult,
    ToolExecutorBinding,
    ToolExecutorKind,
    ToolRegistry,
    ToolSchema,
    ToolValidationError,
    plans_from_provider_tool_calls,
    register_builtin_tools,
)


def test_registration_ordering() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSchema(
            name="builtin.alpha.one",
            description="one",
            parameter_schema={"type": "object", "properties": {}, "required": []},
            executor_binding=ToolExecutorBinding(
                kind=ToolExecutorKind.BUILTIN, executor=lambda _plan, _ctx: ToolExecutionResult(success=True)
            ),
        )
    )
    registry.register(
        ToolSchema(
            name="plugin.recon.scan",
            description="scan",
            parameter_schema={"type": "object", "properties": {}, "required": []},
            executor_binding=ToolExecutorBinding(
                kind=ToolExecutorKind.PLUGIN, executor=lambda _plan, _ctx: ToolExecutionResult(success=True)
            ),
        )
    )
    names = [tool.name for tool in registry.list()]
    assert names == ["builtin.alpha.one", "plugin.recon.scan"]


def test_schema_validation_failure() -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    validation = registry.validate_arguments("builtin.fs.write", {"path": "a.txt"})
    assert validation.valid is False
    assert any("content" in error for error in validation.errors)


async def test_execution_dispatch_correctness_for_builtin_fs(tmp_path: Path) -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    plan = ToolExecutionPlan(
        tool_name="builtin.fs.write",
        arguments={"path": "note.txt", "content": "hello"},
    )
    result = await registry.execute(
        plan,
        context={"workspace_root": tmp_path, "session_metadata": {}},
    )
    assert result.success is True
    assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "hello"


async def test_argument_validation_failure_raises(tmp_path: Path) -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    plan = ToolExecutionPlan(tool_name="builtin.fs.read", arguments={})
    with pytest.raises(ToolValidationError):
        await registry.execute(plan, context={"workspace_root": tmp_path, "session_metadata": {}})


def test_expose_to_llm_contains_namespaced_tools() -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    exposed = registry.expose_to_llm()
    names = [entry["function"]["name"] for entry in exposed]
    assert "builtin.shell.run" in names
    assert "builtin.fs.read" in names
    assert "builtin.fs.write" in names
    assert "builtin.session.note" in names


def test_provider_tool_calls_to_plan_parsing() -> None:
    plans = plans_from_provider_tool_calls(
        [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "builtin.shell.run", "arguments": '{"command":"echo hi"}'},
            }
        ]
    )
    assert len(plans) == 1
    assert plans[0].tool_name == "builtin.shell.run"
    assert plans[0].arguments["command"] == "echo hi"

