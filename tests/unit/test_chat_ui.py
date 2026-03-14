"""Tests for chat UI rendering helpers."""

from __future__ import annotations

from rich.console import Console

from kage.cli.commands.chat import ChatSession
from kage.cli.ui.themes import KAGE_THEME
from kage.core.models import Command
from kage.persistence.config import KageConfig


def _make_session() -> tuple[ChatSession, Console]:
    console = Console(record=True, width=120, theme=KAGE_THEME)
    return ChatSession(console=console, config=KageConfig()), console


def test_show_help_includes_core_commands() -> None:
    session, console = _make_session()
    session._show_help()
    output = console.export_text()
    assert "/help" in output
    assert "/hacker" in output
    assert "/commands" not in output
    assert "/run" not in output
    assert "/history" not in output
    assert "/doctor" not in output


def test_status_and_suggested_commands_render() -> None:
    session, console = _make_session()
    session._pending_commands.append(Command(command="echo hello"))
    session._show_status()
    session._show_suggested_commands()
    output = console.export_text()
    assert "Status" in output
    assert "Suggested Commands" in output
