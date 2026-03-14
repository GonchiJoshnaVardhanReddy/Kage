"""Structured tool call parsing helpers."""

from __future__ import annotations

import json
from typing import Any

from kage.core.models import Command
from kage.core.tools.models import ToolExecutionOrigin, ToolExecutionPlan


def plans_from_provider_tool_calls(
    tool_calls: list[dict[str, Any]] | None,
    *,
    default_origin: ToolExecutionOrigin = ToolExecutionOrigin.LLM,
) -> list[ToolExecutionPlan]:
    """Build execution plans from provider-native tool call payloads."""
    if not tool_calls:
        return []

    plans: list[ToolExecutionPlan] = []
    for call in tool_calls:
        function_data = call.get("function")
        if not isinstance(function_data, dict):
            continue

        name = function_data.get("name")
        if not isinstance(name, str) or not name:
            continue

        raw_args = function_data.get("arguments")
        parsed_args: dict[str, Any]
        if isinstance(raw_args, dict):
            parsed_args = raw_args
        elif isinstance(raw_args, str) and raw_args.strip():
            try:
                parsed = json.loads(raw_args)
            except json.JSONDecodeError:
                parsed_args = {}
            else:
                parsed_args = parsed if isinstance(parsed, dict) else {}
        else:
            parsed_args = {}

        plans.append(ToolExecutionPlan(tool_name=name, arguments=parsed_args, origin=default_origin))

    return plans


def plans_from_commands(
    commands: list[Command],
    *,
    origin: ToolExecutionOrigin = ToolExecutionOrigin.LLM,
) -> list[ToolExecutionPlan]:
    """Backwards-compatible conversion from shell commands to tool plans."""
    plans: list[ToolExecutionPlan] = []
    for command in commands:
        plans.append(
            ToolExecutionPlan(
                tool_name="builtin.shell.run",
                arguments={"command": command.command},
                origin=origin,
                description=command.description,
            )
        )
    return plans

