"""Tests for cinematic split-layout panels and dinosaur animation wiring."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from kage.cli.ui.themes import KAGE_THEME
from kage.core.observability import TraceEvent
from kage.ui.dino_animator import DinoAnimator
from kage.ui.layout import SplitLayoutConfig, render_split_layout
from kage.ui.panels import KagePanelState, build_dinosaur_panel, build_kage_panel
from kage.ui.renderer import UIMode, create_renderer
from kage.ui.status import build_status_state


def test_panel_rendering_order() -> None:
    left = Panel("left")
    center = Panel("center")
    right = Panel("right")
    layout = render_split_layout(
        left_panel=left,
        center_panel=center,
        right_panel=right,
        terminal_width=140,
        config=SplitLayoutConfig(left_width=24, right_width=24),
    )
    assert len(layout.renderables) == 3
    assert layout.renderables[0] is left
    assert layout.renderables[1] is center
    assert layout.renderables[2] is right


def test_terminal_resize_fallback_compacts_right_panel() -> None:
    left = Panel("left")
    center = Panel("center")
    right = Panel("right")
    layout = render_split_layout(
        left_panel=left,
        center_panel=center,
        right_panel=right,
        terminal_width=70,
        config=SplitLayoutConfig(min_total_width_for_side_panels=90),
        compact_right_label="[🦖 running]",
    )
    assert len(layout.renderables) == 3
    assert str(layout.renderables[2]) == "[🦖 running]"


def test_dino_state_switching_from_trace_events() -> None:
    animator = DinoAnimator()
    session_id = "session-1"
    events = [
        TraceEvent(event_type="prompt_compiled", session_id=session_id, component="test"),
        TraceEvent(event_type="tool_selected", session_id=session_id, component="test"),
        TraceEvent(event_type="tool_executed", session_id=session_id, component="test"),
        TraceEvent(event_type="tool_failed", session_id=session_id, component="test"),
        TraceEvent(event_type="workflow_completed", session_id=session_id, component="test"),
    ]
    for event in events:
        animator.map_event(event)
    assert animator.state == "success"


def test_trace_driven_renderer_updates_panels() -> None:
    console = Console(record=True, width=140, theme=KAGE_THEME)
    renderer = create_renderer(mode=UIMode.RICH, console=console)
    state = build_status_state(
        provider="ollama",
        model="llama3",
        session_id="abcdef123456",
        session_metadata={"workflow_name": "recon_scan", "memory_blocks": [{}, {}]},
        safe_mode=True,
    )
    renderer.render_status_bar(state)
    trace = type("TraceLike", (), {"events": []})()
    trace.events.append(
        TraceEvent(
            event_type="agent_step_started",
            session_id="s1",
            turn_id=1,
            component="agent",
            payload={"agent_name": "PlannerAgent"},
        )
    )
    renderer.consume_trace_events(trace, turn_id=1)
    output = console.export_text()
    assert "Kage" in output
    assert "PlannerAgent" in output


def test_animation_loop_stability() -> None:
    animator = DinoAnimator()
    frame1 = animator.current_frame(provider="openai")
    frame2 = animator.current_frame(provider="openai")
    assert isinstance(frame1, str)
    assert isinstance(frame2, str)
    assert frame1
    assert frame2


def test_kage_panel_rendering_contains_identity_fields() -> None:
    console = Console(record=True, width=120, theme=KAGE_THEME)
    panel = build_kage_panel(
        KagePanelState(
            provider="ollama",
            model="llama3",
            workflow="recon_scan",
            policy_mode="safe",
            session_id="abc12345",
            memory_usage="12 block(s)",
            active_agent_step="PlannerAgent",
        )
    )
    console.print(panel)
    rendered = console.export_text()
    assert "ollama" in rendered
    assert "PlannerAgent" in rendered


def test_dinosaur_panel_renders_frame_and_status() -> None:
    panel = build_dinosaur_panel(frame="🦖", status="running workflow...")
    rendered = str(panel.renderable)
    assert "🦖" in rendered
    assert "running workflow..." in rendered

