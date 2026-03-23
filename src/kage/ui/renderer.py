"""Mode-switchable terminal renderer subscribed to runtime trace events."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from kage.core.observability import TraceEvent

from .dino_animator import DinoAnimator
from .frame_renderer import render_layout
from .layout import SplitLayoutConfig
from .panels import (
    KagePanelState,
    build_dinosaur_compact_label,
    build_dinosaur_panel,
    build_kage_panel,
    build_palette_panel,
    build_parallel_agent_panel,
    build_policy_decision_panel,
    build_prompt_diagnostics_panel,
    build_status_bar_panel,
    build_tool_preview_panel,
    build_trace_debug_panel,
    build_workflow_progress_panel,
)
from .progress import WorkflowProgress
from .status import StatusBarState
from .stream import StreamState


class UIMode(str, Enum):
    """Supported terminal UI rendering modes."""

    PLAIN = "plain"
    RICH = "rich"
    DEBUG = "debug"
    JSON = "json"


@dataclass(slots=True)
class BaseUIRenderer:
    """Unified renderer for plain/rich/debug/json terminal experiences."""

    console: Console
    mode: UIMode = UIMode.RICH
    _trace_cursor: int = 0
    _stream: StreamState = field(default_factory=StreamState)
    _workflow_progress: WorkflowProgress = field(default_factory=WorkflowProgress)
    _parallel_states: dict[str, str] = field(default_factory=dict)
    _debug_enabled: bool = False
    _status_state: StatusBarState | None = None
    _kage_state: KagePanelState = field(default_factory=KagePanelState)
    _timeline: list[str] = field(default_factory=list)
    _dino_enabled: bool = True
    _dino_animator: DinoAnimator = field(default_factory=DinoAnimator)
    _split_layout: SplitLayoutConfig = field(default_factory=SplitLayoutConfig)
    _event_bus_handlers: list[Callable[[TraceEvent], None]] = field(default_factory=list)

    def render_stream_token(self, token: str) -> None:
        """Render one streaming token chunk."""
        self._stream.append(token)
        self.console.print(token, end="", highlight=False)

    def complete_stream(self) -> None:
        """Finalize a streamed response render."""
        self.console.print()

    def toggle_debug(self, enabled: bool | None = None) -> bool:
        """Toggle trace-debug rendering."""
        if enabled is None:
            self._debug_enabled = not self._debug_enabled
        else:
            self._debug_enabled = enabled
        return self._debug_enabled

    def set_dino_enabled(self, enabled: bool) -> None:
        """Enable/disable the dinosaur companion panel."""
        self._dino_enabled = enabled

    def is_dino_enabled(self) -> bool:
        """Return whether dinosaur panel rendering is enabled."""
        return self._dino_enabled

    def subscribe_event_bus(self, handler: Callable[[TraceEvent], None]) -> None:
        """Subscribe a trace-event callback to the renderer event bus."""
        self._event_bus_handlers.append(handler)

    def render_tool_preview(
        self,
        *,
        plan: Any,
        policy_decision: str | None = None,
        confidence_score: float | None = None,
    ) -> None:
        """Render structured tool preview panel."""
        if self.mode == UIMode.JSON:
            self.console.print(
                json.dumps(
                    {
                        "type": "tool_preview",
                        "tool": getattr(plan, "tool_name", ""),
                        "arguments": getattr(plan, "arguments", {}),
                        "confidence_score": confidence_score,
                        "policy_decision": policy_decision,
                    }
                ),
                highlight=False,
            )
            return
        if self.mode == UIMode.PLAIN:
            self.console.print(
                f"Tool: {getattr(plan, 'tool_name', '')} | Args: {getattr(plan, 'arguments', {})}"
            )
            return
        self.console.print(
            build_tool_preview_panel(
                plan=plan,
                policy_decision=policy_decision,
                confidence_score=confidence_score,
            )
        )

    def render_status_bar(self, state: StatusBarState) -> None:
        """Render status bar/footer."""
        self._status_state = state
        self._kage_state.provider = state.provider
        self._kage_state.model = state.model
        self._kage_state.workflow = state.active_workflow
        self._kage_state.policy_mode = state.policy_mode
        self._kage_state.session_id = state.session_id
        self._kage_state.memory_usage = state.memory_usage

        if self.mode == UIMode.JSON:
            self.console.print(
                json.dumps(
                    {
                        "type": "status",
                        "provider": state.provider,
                        "model": state.model,
                        "workflow": state.active_workflow,
                        "memory": state.memory_usage,
                        "policy_mode": state.policy_mode,
                        "session_id": state.session_id,
                    }
                ),
                highlight=False,
            )
            return
        if self.mode == UIMode.PLAIN:
            self.console.print(
                "[provider: "
                f"{state.provider} | model: {state.model} | workflow: {state.active_workflow} "
                f"| memory: {state.memory_usage} | safe-mode: {state.policy_mode} | session: {state.session_id}]"
            )
            return
        self._render_cinematic_frame()
        self.console.print(build_status_bar_panel(state))

    def render_workflow_progress(self) -> None:
        """Render workflow progress panel from tracked states."""
        if not self._workflow_progress.steps:
            return
        if self.mode == UIMode.PLAIN:
            for line in self._workflow_progress.render_lines():
                self.console.print(line)
            return
        if self.mode == UIMode.JSON:
            self.console.print(
                json.dumps(
                    {
                        "type": "workflow_progress",
                        "steps": [
                            {"name": step.name, "state": step.state}
                            for step in self._workflow_progress.steps
                        ],
                    }
                ),
                highlight=False,
            )
            return
        self.console.print(build_workflow_progress_panel(self._workflow_progress))

    def render_parallel_agents(self) -> None:
        """Render live parallel-agent status panel."""
        if not self._parallel_states:
            return
        if self.mode == UIMode.PLAIN:
            for agent_name in sorted(self._parallel_states):
                self.console.print(f"{agent_name:<16} {self._parallel_states[agent_name]}")
            return
        if self.mode == UIMode.JSON:
            self.console.print(
                json.dumps(
                    {"type": "parallel_agents", "states": dict(sorted(self._parallel_states.items()))}
                ),
                highlight=False,
            )
            return
        self.console.print(build_parallel_agent_panel(self._parallel_states))

    def render_palette(self, query: str, matches: list[tuple[str, str]]) -> None:
        """Render slash-command command palette results."""
        if self.mode == UIMode.PLAIN:
            for command, description in matches:
                self.console.print(f"{command} - {description}")
            return
        if self.mode == UIMode.JSON:
            self.console.print(
                json.dumps(
                    {
                        "type": "palette",
                        "query": query,
                        "matches": [{"command": command, "description": description} for command, description in matches],
                    }
                ),
                highlight=False,
            )
            return
        self.console.print(build_palette_panel(query, matches))

    def render_prompt_diagnostics(self, compiled_prompt: Any) -> None:
        """Render middleware/prompt-layer diagnostics view."""
        if self.mode == UIMode.PLAIN:
            self.console.print(f"Prompt token estimate: {compiled_prompt.token_count_estimate}")
            for layer in compiled_prompt.layers:
                self.console.print(f"- {layer.name}: {len(layer.content)} chars")
            return
        if self.mode == UIMode.JSON:
            self.console.print(
                json.dumps(
                    {
                        "type": "prompt_diagnostics",
                        "token_count_estimate": compiled_prompt.token_count_estimate,
                        "layers": [
                            {
                                "name": layer.name,
                                "chars": len(layer.content),
                                "tokens_estimate": max(1, len(layer.content) // 4),
                            }
                            for layer in compiled_prompt.layers
                        ],
                        "dropped_layers": list(compiled_prompt.dropped_layers),
                    }
                ),
                highlight=False,
            )
            return
        self._timeline.append("prompt_inspect (ui)")
        if len(self._timeline) > 10:
            del self._timeline[:-10]
        self.console.print(build_prompt_diagnostics_panel(compiled_prompt))

    def render_trace_debug(self, events: list[TraceEvent]) -> None:
        """Render trace-debug panel for recent events."""
        if self.mode == UIMode.PLAIN:
            for event in events[-12:]:
                self.console.print(f"{event.event_type} ({event.component}) {event.payload}")
            return
        if self.mode == UIMode.JSON:
            self.console.print(
                json.dumps(
                    {
                        "type": "trace_debug",
                        "events": [event.model_dump(mode="json") for event in events[-12:]],
                    }
                ),
                highlight=False,
            )
            return
        self.console.print(build_trace_debug_panel(events))

    def consume_trace_events(self, trace: Any, *, turn_id: int | None = None) -> list[TraceEvent]:
        """Consume newly appended trace events and render subscribed views."""
        events: list[TraceEvent] = []
        raw_events = getattr(trace, "events", [])
        if not isinstance(raw_events, list):
            return events
        if self._trace_cursor >= len(raw_events):
            return events
        new_events = raw_events[self._trace_cursor :]
        self._trace_cursor = len(raw_events)
        for raw_event in new_events:
            if not isinstance(raw_event, TraceEvent):
                continue
            if turn_id is not None and raw_event.turn_id != turn_id:
                continue
            events.append(raw_event)
            self._emit_event(raw_event)
            self._apply_event_state(raw_event)
            self._render_event_line(raw_event)

        if self.mode in {UIMode.RICH, UIMode.DEBUG}:
            self._render_cinematic_frame()
        if self.mode == UIMode.DEBUG or self._debug_enabled:
            self.render_trace_debug(events)
        return events

    def _emit_event(self, event: TraceEvent) -> None:
        """Publish one trace event to renderer event-bus subscribers."""
        self._dino_animator.map_event(event)
        for handler in self._event_bus_handlers:
            handler(event)

    def _apply_event_state(self, event: TraceEvent) -> None:
        event_type = event.event_type
        payload = event.payload
        agent_name = str(payload.get("agent_name", "")) if isinstance(payload, dict) else ""
        if event_type in {"pipeline_step_started", "agent_step_started"} and agent_name:
            self._workflow_progress.set_state(agent_name, "running")
            self._kage_state.active_agent_step = agent_name
        elif event_type in {"pipeline_step_completed", "agent_step_completed"} and agent_name:
            success = bool(payload.get("success", True)) if isinstance(payload, dict) else True
            self._workflow_progress.set_state(agent_name, "completed" if success else "failed")
            self._kage_state.active_agent_step = agent_name
        elif event_type == "parallel_agent_started" and agent_name:
            self._parallel_states[agent_name] = "running"
            self._kage_state.active_agent_step = agent_name
        elif event_type == "parallel_agent_completed" and agent_name:
            success = bool(payload.get("success", True)) if isinstance(payload, dict) else True
            self._parallel_states[agent_name] = "completed" if success else "failed"
            self._kage_state.active_agent_step = agent_name

        if event_type in {"workflow_started", "workflow_completed", "workflow_failed"} and isinstance(
            payload, dict
        ):
            workflow_name = str(payload.get("workflow_name", "")).strip()
            if workflow_name:
                self._kage_state.workflow = workflow_name

        self._timeline.append(f"{event.event_type} ({event.component})")
        if len(self._timeline) > 10:
            del self._timeline[:-10]

    def _render_event_line(self, event: TraceEvent) -> None:
        event_type = event.event_type
        payload = event.payload
        if self.mode in {UIMode.RICH, UIMode.DEBUG}:
            return
        if event_type == "policy_decision":
            decision = str(payload.get("decision", "unknown"))
            reason = str(payload.get("reason", ""))
            if self.mode == UIMode.RICH:
                self.console.print(build_policy_decision_panel(decision, reason, payload))
            else:
                self.console.print(f"policy: {decision} ({reason})")
            return

        if event_type in {
            "tool_selected",
            "tool_executed",
            "tool_completed",
            "workflow_started",
            "workflow_completed",
            "workflow_failed",
            "parallel_group_started",
            "parallel_group_completed",
            "parallel_merge_completed",
            "agent_step_started",
            "agent_step_completed",
            "memory_compaction_triggered",
        }:
            if self.mode == UIMode.JSON:
                self.console.print(
                    json.dumps({"type": "trace_event", "event": event.model_dump(mode="json")}),
                    highlight=False,
                )
            else:
                self.console.print(f"[muted]{event_type}[/muted] {payload}")

    def _build_center_panel(self) -> Panel:
        """Build center workflow/timeline panel for split-layout render."""
        timeline = self._timeline[-6:] if self._timeline else ["waiting for trace events..."]
        stream_text = self._stream.text[-600:] if self._stream.text else ""
        content: list[Any] = [
            Text("Workflow Timeline", style="panel.title"),
            *[Text(f"- {line}", style="muted") for line in timeline],
        ]
        if stream_text.strip():
            content.append(Text("\nStream", style="panel.title"))
            content.append(Text(stream_text, style="info"))
        if self._workflow_progress.steps:
            content.append(Text("\nProgress", style="panel.title"))
            for line in self._workflow_progress.render_lines():
                content.append(Text(line, style="muted"))
        if self._parallel_states:
            content.append(Text("\nParallel", style="panel.title"))
            for agent_name in sorted(self._parallel_states):
                content.append(Text(f"{agent_name}: {self._parallel_states[agent_name]}", style="muted"))
        return Panel(
            Group(*content),
            title="[panel.title]Runtime[/panel.title]",
            border_style="panel.border",
            padding=(0, 1),
        )

    def _render_cinematic_frame(self) -> None:
        """Render persistent split-layout cinematic frame."""
        if self.mode not in {UIMode.RICH, UIMode.DEBUG}:
            return
        if self._status_state is None:
            return

        left_panel = build_kage_panel(self._kage_state)
        center_panel = self._build_center_panel()
        dino_frame = self._dino_animator.current_frame(
            provider=self._status_state.provider if self._status_state else None
        )
        dino_status = self._dino_animator.status_label()
        right_panel = (
            build_dinosaur_panel(frame=dino_frame, status=dino_status)
            if self._dino_enabled
            else Panel(Text("disabled", style="muted"), title="[panel.title]Companion[/panel.title]")
        )
        compact_label = (
            build_dinosaur_compact_label(frame=dino_frame, status=dino_status)
            if self._dino_enabled
            else "[🦖 off]"
        )
        layout_renderable = render_layout(
            left_panel=left_panel,
            center_panel=center_panel,
            right_panel=right_panel,
            terminal_width=self.console.size.width,
            config=self._split_layout,
            compact_right_label=compact_label,
        )
        self.console.print(layout_renderable)


def create_renderer(*, mode: UIMode, console: Console) -> BaseUIRenderer:
    """Create renderer by UI mode."""
    return BaseUIRenderer(console=console, mode=mode)

