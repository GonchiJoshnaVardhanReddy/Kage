"""Integration-ish tests for chat + tool registry lifecycle compatibility."""

from __future__ import annotations

from rich.console import Console

from kage.cli.commands.chat import ChatSession
from kage.cli.ui.themes import KAGE_THEME
from kage.core.hooks import HookEvent
from kage.core.tools import ToolExecutionPlan
from kage.persistence.config import KageConfig


def _make_session() -> ChatSession:
    return ChatSession(console=Console(record=True, theme=KAGE_THEME), config=KageConfig())


def test_hook_context_provider_exposes_tool_registry() -> None:
    session = _make_session()
    payload = session._tool_registry_context()
    assert payload["available"] is True
    assert payload["tool_count"] >= 4
    assert "builtin.shell.run" in payload["tools"]


def test_pre_command_hook_still_blocks_shell_execution(monkeypatch) -> None:
    session = _make_session()

    def block_hook(_payload: dict) -> dict:
        return {"continue_pipeline": False}

    session._hooks.register(event=HookEvent.PRE_COMMAND_RUN, callback=block_hook, name="blocker")
    session._pending_tool_plans = [
        ToolExecutionPlan(tool_name="builtin.shell.run", arguments={"command": "echo blocked"})
    ]

    monkeypatch.setattr(
        "kage.cli.commands.chat.ChatSession._ensure_tool_installed",
        lambda _self, _tool_name: True,
    )
    monkeypatch.setattr(
        "kage.cli.ui.prompts.prompt_command_approval",
        lambda *_args, **_kwargs: "3",
    )

    session._run_pending_tool_plans()
    assert session.session.commands
    assert session.session.commands[-1].status.value == "rejected"


def test_tool_plan_pre_and_post_hooks_fire() -> None:
    session = _make_session()
    seen: list[tuple[str, str]] = []

    def pre_hook(payload: dict) -> dict:
        seen.append(("pre", str(payload.get("command", ""))))
        return {"continue_pipeline": True}

    def post_hook(payload: dict) -> dict:
        seen.append(("post", str(payload.get("command", ""))))
        return {"continue_pipeline": True}

    session._hooks.register(event=HookEvent.PRE_COMMAND_RUN, callback=pre_hook, name="pre-capture")
    session._hooks.register(event=HookEvent.POST_COMMAND_RUN, callback=post_hook, name="post-capture")
    session._pending_tool_plans = [
        ToolExecutionPlan(tool_name="builtin.session.note", arguments={"text": "captured"}),
    ]
    session._run_pending_tool_plans()
    assert ("pre", "builtin.session.note") in seen
    assert ("post", "builtin.session.note") in seen


def test_show_suggested_commands_handles_tool_plans() -> None:
    session = _make_session()
    session._pending_tool_plans = [
        ToolExecutionPlan(tool_name="builtin.session.note", arguments={"text": "abc"}),
    ]
    session._show_suggested_commands()
    rendered = session.console.export_text()
    assert "Suggested Commands" in rendered
    assert "builtin.session.note" in rendered

