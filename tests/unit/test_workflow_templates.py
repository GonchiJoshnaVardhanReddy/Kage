"""Tests for declarative workflow template runtime."""

from __future__ import annotations

from pathlib import Path

import pytest

from kage.core.agents import AgentContext, AgentOrchestrator
from kage.core.models import Session
from kage.core.prompt import MiddlewareRegistry, ReconContextMiddleware
from kage.core.tools import ToolRegistry, register_builtin_tools
from kage.core.workflows import (
    WorkflowExecutor,
    WorkflowLoader,
    WorkflowRegistry,
    WorkflowRegistryError,
    ensure_builtin_workflow_templates,
    register_plugin_workflows,
)
from kage.core.workflows.schema import WorkflowTemplateSchema
from kage.core.workflows.template import WorkflowTemplate
from kage.plugins.manager import PluginManager
from kage.plugins.schema import PluginSchema


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _recon_plugin_dir() -> Path:
    return _repo_root() / "plugins" / "recon"


def _workflow_context(turn_id: int = 41) -> AgentContext:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    session = Session()
    return AgentContext(
        session=session,
        registry=registry,
        metadata={"turn_id": turn_id, "workspace_root": _repo_root()},
    )


def test_template_loading_from_yaml(tmp_path: Path) -> None:
    builtins_dir = tmp_path / "builtins"
    ensure_builtin_workflow_templates(builtins_dir)
    loader = WorkflowLoader(builtin_dir=builtins_dir)
    template = loader.load("builtin_recon")
    assert template.name == "builtin_recon"
    assert template.pipeline_steps


async def test_pipeline_execution_through_executor(tmp_path: Path) -> None:
    workflow_file = tmp_path / "exec.yaml"
    workflow_file.write_text(
        """
name: exec_workflow
description: execution test
required_tools:
  - builtin.session.note
default_parameters:
  planned_command: echo exec-workflow
pipeline:
  - PlannerAgent
  - ReporterAgent
""".strip()
        + "\n",
        encoding="utf-8",
    )
    loader = WorkflowLoader()
    template = loader.load_from_file(workflow_file)

    context = _workflow_context(turn_id=42)
    middleware_registry = MiddlewareRegistry()
    registry = WorkflowRegistry(tool_registry=context.registry, middleware_registry=middleware_registry)
    registry.register(template)
    executor = WorkflowExecutor(orchestrator=AgentOrchestrator(), registry=registry)

    result = await executor.run("exec_workflow", context=context, parameters={"planned_command": "echo run42"})
    assert result.success is True
    events = [event.event_type for event in context.session.trace.get_turn(42)]
    assert "workflow_started" in events
    assert "workflow_completed" in events


def test_plugin_workflow_registration() -> None:
    schema = PluginSchema.from_yaml(_recon_plugin_dir() / "plugin.yaml")
    tools = ToolRegistry()
    register_builtin_tools(tools)
    middleware = MiddlewareRegistry()
    middleware.register(ReconContextMiddleware())
    registry = WorkflowRegistry(tool_registry=tools, middleware_registry=middleware)
    registered = register_plugin_workflows(
        schema=schema,
        plugin_dir=_recon_plugin_dir(),
        registry=registry,
    )
    assert "recon_scan" in registered
    assert registry.get("recon_scan") is not None


def test_dependency_validation() -> None:
    tools = ToolRegistry()
    register_builtin_tools(tools)
    registry = WorkflowRegistry(tool_registry=tools, middleware_registry=MiddlewareRegistry())
    schema = WorkflowTemplateSchema(
        name="invalid_dependencies",
        pipeline=["PlannerAgent"],
        required_tools=["missing.tool"],
        required_middleware=["missing_middleware"],
    )
    template = WorkflowTemplate.from_schema(schema)
    registry.register(template)
    with pytest.raises(WorkflowRegistryError):
        registry.ensure_valid(template)


async def test_trace_emission_correctness_for_loader_and_executor(tmp_path: Path) -> None:
    workflow_file = tmp_path / "trace.yaml"
    workflow_file.write_text(
        """
name: trace_workflow
description: trace test
required_tools:
  - builtin.session.note
pipeline:
  - PlannerAgent
""".strip()
        + "\n",
        encoding="utf-8",
    )
    template = WorkflowLoader().load_from_file(workflow_file)
    context = _workflow_context(turn_id=43)
    middleware_registry = MiddlewareRegistry()
    workflow_registry = WorkflowRegistry(
        tool_registry=context.registry,
        middleware_registry=middleware_registry,
    )
    workflow_registry.register(template)
    session = context.session
    recorder_events_before = len(session.trace.events)
    manager = PluginManager(
        plugin_dirs=[_repo_root() / "plugins"],
        sandbox_enabled=False,
        workflow_registry=workflow_registry,
    )
    manager.load_plugin(_recon_plugin_dir())
    manager.set_context(session)

    assert len(session.trace.events) >= recorder_events_before
    assert any(event.event_type == "workflow_loaded" for event in session.trace.events)
    result = await WorkflowExecutor(AgentOrchestrator(), workflow_registry).run(
        "trace_workflow",
        context=context,
    )
    assert result.success is True
    turn_events = [event.event_type for event in context.session.trace.get_turn(43)]
    assert "workflow_started" in turn_events
    assert "workflow_completed" in turn_events


async def test_workflow_failed_emission_on_validation_error() -> None:
    tools = ToolRegistry()
    register_builtin_tools(tools)
    middleware = MiddlewareRegistry()
    schema = WorkflowTemplateSchema(
        name="fail_workflow",
        pipeline=["PlannerAgent"],
        required_tools=["missing.tool"],
    )
    template = WorkflowTemplate.from_schema(schema)
    registry = WorkflowRegistry(tool_registry=tools, middleware_registry=middleware)
    registry.register(template)
    context = _workflow_context(turn_id=44)
    executor = WorkflowExecutor(AgentOrchestrator(), registry)
    with pytest.raises(WorkflowRegistryError):
        await executor.run("fail_workflow", context=context)
    event_types = [event.event_type for event in context.session.trace.get_turn(44)]
    assert "workflow_failed" in event_types

