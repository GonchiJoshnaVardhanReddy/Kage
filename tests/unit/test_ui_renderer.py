"""Tests for the new UI renderer runtime package."""

from __future__ import annotations

from rich.console import Console

from kage.cli.ui.themes import KAGE_THEME
from kage.core.models import Session
from kage.core.observability import TraceEvent
from kage.core.prompt.context import CompiledPrompt, PromptLayerOutput
from kage.core.tools import ToolExecutionPlan
from kage.ui.diff import render_diff_panel
from kage.ui.layout import map_keypress
from kage.ui.palette import SlashCommandPalette
from kage.ui.progress import WorkflowProgress
from kage.ui.renderer import UIMode, create_renderer
from kage.ui.status import build_status_state
from kage.ui.stream import stream_lines


def test_stream_rendering_correctness() -> None:
    assert stream_lines(["Hello", " ", "world"], width=20) == ["Hello world"]
    wrapped = stream_lines(["alpha", "beta", "gamma"], width=8)
    assert wrapped == ["alpha", "beta", "gamma"]


def test_diff_panel_formatting() -> None:
    panel = render_diff_panel("demo.py", "--- a/demo.py\n+++ b/demo.py\n+print('x')\n")
    assert "Diff Preview" in str(panel.title)


def test_diff_prompt_keyboard_navigation(monkeypatch) -> None:
    from kage.ui.diff import prompt_diff_approval

    console = Console(record=True, width=120, theme=KAGE_THEME)
    responses = iter(["{down}", "{enter}"])
    monkeypatch.setattr(console, "input", lambda _prompt="": next(responses))
    choice = prompt_diff_approval(
        console,
        file_path="demo.py",
        unified_diff="--- a/demo.py\n+++ b/demo.py\n+print('x')\n",
        allow_edit_option=True,
    )
    assert choice == "edit"


def test_workflow_progress_updates() -> None:
    progress = WorkflowProgress()
    progress.set_state("PlannerAgent", "running")
    progress.set_state("PlannerAgent", "completed")
    progress.set_state("ReconAgent", "waiting")
    lines = progress.render_lines()
    assert any("PlannerAgent" in line and "completed" in line for line in lines)
    assert any("ReconAgent" in line and "waiting" in line for line in lines)


def test_slash_palette_filtering() -> None:
    palette = SlashCommandPalette()
    matches = palette.search("trc")
    assert matches
    assert any("/trace" in item.command for item in matches)


def test_status_bar_updates() -> None:
    state = build_status_state(
        provider="ollama",
        model="llama3",
        session_id="12345678-abcd",
        session_metadata={"workflow_name": "recon_scan", "memory_blocks": [{}, {}]},
        safe_mode=True,
    )
    assert state.provider == "ollama"
    assert state.active_workflow == "recon_scan"
    assert state.memory_usage == "2 block(s)"
    assert state.policy_mode == "safe"
    assert state.session_id == "12345678"


def test_trace_panel_formatting() -> None:
    console = Console(record=True, width=120, theme=KAGE_THEME)
    renderer = create_renderer(mode=UIMode.DEBUG, console=console)
    session = Session()
    session.trace.append(
        TraceEvent(
            event_type="tool_selected",
            session_id=session.id,
            turn_id=1,
            component="test",
            payload={"tool_name": "builtin.session.note"},
        )
    )
    renderer.consume_trace_events(session.trace, turn_id=1)
    output = console.export_text()
    assert "tool_selected" in output
    assert "Trace Debug" in output


def test_renderer_prompt_diagnostics_and_status_output() -> None:
    console = Console(record=True, width=120, theme=KAGE_THEME)
    renderer = create_renderer(mode=UIMode.RICH, console=console)
    compiled = CompiledPrompt(
        system_prompt="demo",
        layers=[PromptLayerOutput(name="SystemLayer", priority=10, content="abc")],
        dropped_layers=["PluginLayer"],
        token_count_estimate=1,
    )
    renderer.render_prompt_diagnostics(compiled)
    state = build_status_state(
        provider="ollama",
        model="llama3",
        session_id="session-123456",
        session_metadata={},
        safe_mode=False,
    )
    renderer.render_status_bar(state)
    rendered = console.export_text()
    assert "Prompt Diagnostics" in rendered
    assert "provider:" in rendered


def test_renderer_tool_preview_and_json_mode() -> None:
    console = Console(record=True, width=120)
    renderer = create_renderer(mode=UIMode.JSON, console=console)
    plan = ToolExecutionPlan(
        tool_name="builtin.session.note",
        arguments={"text": "hello"},
        confidence_score=0.8,
    )
    renderer.render_tool_preview(plan=plan, policy_decision="allow", confidence_score=0.8)
    output = console.export_text()
    assert '"type": "tool_preview"' in output
    assert '"tool": "builtin.session.note"' in output


def test_keyboard_interaction_mapping() -> None:
    assert map_keypress("{up}") == "move_up"
    assert map_keypress("{down}") == "move_down"
    assert map_keypress("{enter}") == "confirm"
    assert map_keypress("escape") == "cancel"
    assert map_keypress("tab") == "autocomplete"
    assert map_keypress("ctrl+r") == "history_search"

