"""Session-level trace container with per-turn indexing."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .events import TraceEvent


class SessionTrace(BaseModel):
    """Holds structured events and derived runtime diagnostics for a session."""

    events: list[TraceEvent] = Field(default_factory=list)
    events_by_turn: dict[int, list[TraceEvent]] = Field(default_factory=dict)
    agent_pipeline_steps: list[TraceEvent] = Field(default_factory=list)
    tool_execution_history: list[TraceEvent] = Field(default_factory=list)
    prompt_layer_diagnostics: list[TraceEvent] = Field(default_factory=list)
    policy_decisions: list[TraceEvent] = Field(default_factory=list)

    def append(self, event: TraceEvent) -> None:
        """Append an event and update turn and diagnostic indices."""
        self.events.append(event)
        self.events_by_turn.setdefault(event.turn_id, []).append(event)

        if event.event_type.startswith("agent_") or event.event_type.startswith("pipeline_step_"):
            self.agent_pipeline_steps.append(event)
        if event.event_type.startswith("tool_"):
            self.tool_execution_history.append(event)
        if event.event_type.startswith("prompt_") or event.event_type.startswith("layer_"):
            self.prompt_layer_diagnostics.append(event)
        if event.event_type.startswith("policy_"):
            self.policy_decisions.append(event)

    def extend(self, events: list[TraceEvent]) -> None:
        """Append a batch of events in order."""
        for event in events:
            self.append(event)

    def get_turn(self, turn_id: int) -> list[TraceEvent]:
        """Return events recorded for one turn."""
        return list(self.events_by_turn.get(turn_id, []))

