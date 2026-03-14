"""Helpers for reading/writing session traces from metadata."""

from __future__ import annotations

from typing import Any

from .events import TraceEvent
from .recorder import TraceRecorder
from .session_trace import SessionTrace

_TRACE_KEY = "_runtime_trace"
_TRACE_BY_SESSION: dict[str, SessionTrace] = {}
_PENDING_EVENTS_BY_SESSION: dict[str, list[TraceEvent]] = {}


def get_or_create_session_trace(metadata: dict[str, Any]) -> SessionTrace:
    """Resolve a SessionTrace object from session metadata."""
    existing = metadata.get(_TRACE_KEY)
    if isinstance(existing, SessionTrace):
        return existing

    trace = SessionTrace()
    if isinstance(existing, dict):
        raw_events = existing.get("events")
        if isinstance(raw_events, list):
            for raw_event in raw_events:
                if isinstance(raw_event, dict):
                    trace.append(TraceEvent(**raw_event))
    metadata[_TRACE_KEY] = trace
    return trace


def register_session_trace(session_id: str, trace: SessionTrace) -> None:
    """Register a session trace for lookup by session id."""
    _TRACE_BY_SESSION[session_id] = trace
    pending = _PENDING_EVENTS_BY_SESSION.pop(session_id, [])
    if pending:
        trace.extend(pending)


def get_registered_session_trace(session_id: str) -> SessionTrace | None:
    """Get a previously registered session trace by session id."""
    return _TRACE_BY_SESSION.get(session_id)


def queue_event_for_session(event: TraceEvent) -> None:
    """Queue an event until a session trace is registered."""
    pending = _PENDING_EVENTS_BY_SESSION.setdefault(event.session_id, [])
    pending.append(event)


def recorder_for_session(session: Any, *, component: str) -> TraceRecorder:
    """Create recorder bound to a session and register trace globally."""
    session_id = getattr(session, "id", None)
    trace = getattr(session, "trace", None)
    if not isinstance(session_id, str) or not isinstance(trace, SessionTrace):
        raise ValueError("session must expose id:str and trace:SessionTrace")
    register_session_trace(session_id, trace)
    return TraceRecorder(trace=trace, session_id=session_id, default_component=component)


def recorder_from_context(
    context: dict[str, Any] | None,
    *,
    component: str,
) -> TraceRecorder | None:
    """Resolve recorder from runtime context when available."""
    if not isinstance(context, dict):
        return None
    session = context.get("session")
    if session is not None:
        return recorder_for_session(session, component=component)
    return None


def recorder_for_session_id(session_id: str, *, component: str) -> TraceRecorder | None:
    """Resolve recorder from a known session id."""
    trace = get_registered_session_trace(session_id)
    if trace is None:
        return None
    return TraceRecorder(trace=trace, session_id=session_id, default_component=component)


def trace_to_metadata_payload(trace: SessionTrace) -> dict[str, Any]:
    """Serialize trace for JSON-compatible session metadata persistence."""
    return {
        "events": [event.model_dump(mode="json") for event in trace.events],
    }


def from_metadata_payload(payload: dict[str, Any]) -> SessionTrace:
    """Create SessionTrace from serialized payload."""
    trace = SessionTrace()
    raw_events = payload.get("events")
    if not isinstance(raw_events, list):
        return trace
    for raw_event in raw_events:
        if isinstance(raw_event, dict):
            trace.append(TraceEvent(**raw_event))
    return trace

