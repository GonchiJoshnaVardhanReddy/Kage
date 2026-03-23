"""Trace-driven dinosaur animation controller."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Literal

from kage.core.observability import TraceEvent

DinoState = Literal["idle", "thinking", "executing", "running", "error", "success"]


@dataclass(slots=True)
class DinoAnimator:
    """Frame controller for dinosaur companion animation."""

    state: DinoState = "idle"
    parallel_active: bool = False
    _frame_index: int = 0
    _last_advance_at: float = field(default_factory=monotonic)
    _last_latency_ms: float | None = None
    _frames: dict[DinoState, tuple[str, ...]] = field(
        default_factory=lambda: {
            "idle": ("🦖", "🦕"),
            "thinking": ("🦖 .", "🦖 ..", "🦖 ..."),
            "executing": ("🦖 >", "🦖 >>"),
            "running": ("🦖 ~", "🦖 ~~", "🦖 ~~~"),
            "error": ("🦖 !", "🦖 !!"),
            "success": ("🦖 ✓", "🦖 ✔"),
        }
    )

    def map_event(self, event: TraceEvent) -> None:
        """Update animation state from a runtime trace event."""
        event_type = event.event_type
        if event.duration_ms is not None:
            self._last_latency_ms = float(event.duration_ms)

        if event_type in {"prompt_compiled", "agent_started"}:
            self.state = "thinking"
        elif event_type == "tool_selected":
            self.state = "executing"
        elif event_type in {"tool_executed", "workflow_started"}:
            self.state = "running"
        elif event_type in {"tool_completed", "parallel_group_completed"}:
            self.state = "idle"
        elif event_type in {"workflow_completed", "parallel_merge_completed"}:
            self.state = "success"
        elif event_type in {"tool_failed", "workflow_failed"}:
            self.state = "error"

        if event_type == "parallel_group_started":
            self.parallel_active = True
            self.state = "running"
        elif event_type == "parallel_group_completed":
            self.parallel_active = False

    def _interval_seconds(self, *, provider: str | None = None) -> float:
        """Choose animation pacing based on provider/latency/parallel state."""
        interval = 0.35
        provider_value = (provider or "").lower()
        if provider_value in {"ollama", "lmstudio"}:
            interval = 0.45
        elif provider_value in {"openai"}:
            interval = 0.25

        if self._last_latency_ms is not None:
            if self._last_latency_ms > 1000:
                interval = min(interval, 0.20)
            elif self._last_latency_ms < 200:
                interval = max(interval, 0.50)

        if self.parallel_active:
            interval = min(interval, 0.20)
        return interval

    def current_frame(self, *, provider: str | None = None) -> str:
        """Return a frame with low-CPU time-based advancement."""
        frames = self._frames[self.state]
        now = monotonic()
        if now - self._last_advance_at >= self._interval_seconds(provider=provider):
            self._frame_index = (self._frame_index + 1) % len(frames)
            self._last_advance_at = now
        return frames[self._frame_index]

    def status_label(self) -> str:
        """Return the textual status for the current state."""
        labels: dict[DinoState, str] = {
            "idle": "waiting...",
            "thinking": "thinking...",
            "executing": "executing...",
            "running": "running workflow...",
            "error": "error!",
            "success": "completed!",
        }
        return labels[self.state]

