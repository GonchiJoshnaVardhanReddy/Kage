"""Async-safe trace recorder with batch buffering and flush support."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from .events import TraceEvent, TraceSeverity
from .session_trace import SessionTrace


@dataclass(slots=True)
class TraceRecorder:
    """Records structured runtime events into a SessionTrace container."""

    trace: SessionTrace
    session_id: str
    default_component: str = "runtime"
    _metadata: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _buffer: list[TraceEvent] = field(default_factory=list, init=False, repr=False)

    def attach_metadata(self, metadata: dict[str, Any]) -> None:
        """Attach shared metadata included in subsequently recorded events."""
        self._metadata.update(metadata)

    def _build_event(
        self,
        *,
        event_type: str,
        turn_id: int = 0,
        component: str | None = None,
        payload: dict[str, Any] | None = None,
        severity: TraceSeverity = TraceSeverity.INFO,
        duration_ms: float | None = None,
    ) -> TraceEvent:
        merged_payload = dict(self._metadata)
        if payload:
            merged_payload.update(payload)
        return TraceEvent(
            event_type=event_type,
            session_id=self.session_id,
            turn_id=turn_id,
            component=component or self.default_component,
            payload=merged_payload,
            severity=severity,
            duration_ms=duration_ms,
        )

    def record(
        self,
        *,
        event_type: str,
        turn_id: int = 0,
        component: str | None = None,
        payload: dict[str, Any] | None = None,
        severity: TraceSeverity = TraceSeverity.INFO,
        duration_ms: float | None = None,
    ) -> TraceEvent:
        """Record one event synchronously."""
        event = self._build_event(
            event_type=event_type,
            turn_id=turn_id,
            component=component,
            payload=payload,
            severity=severity,
            duration_ms=duration_ms,
        )
        self.trace.append(event)
        return event

    async def record_async(
        self,
        *,
        event_type: str,
        turn_id: int = 0,
        component: str | None = None,
        payload: dict[str, Any] | None = None,
        severity: TraceSeverity = TraceSeverity.INFO,
        duration_ms: float | None = None,
    ) -> TraceEvent:
        """Record one event with async lock safety for concurrent pipelines."""
        event = self._build_event(
            event_type=event_type,
            turn_id=turn_id,
            component=component,
            payload=payload,
            severity=severity,
            duration_ms=duration_ms,
        )
        async with self._lock:
            self.trace.append(event)
        return event

    async def add_to_batch(
        self,
        *,
        event_type: str,
        turn_id: int = 0,
        component: str | None = None,
        payload: dict[str, Any] | None = None,
        severity: TraceSeverity = TraceSeverity.INFO,
        duration_ms: float | None = None,
    ) -> None:
        """Buffer one event for future flush."""
        event = self._build_event(
            event_type=event_type,
            turn_id=turn_id,
            component=component,
            payload=payload,
            severity=severity,
            duration_ms=duration_ms,
        )
        async with self._lock:
            self._buffer.append(event)

    async def flush_batch(self) -> int:
        """Flush buffered events to trace preserving buffered order."""
        async with self._lock:
            if not self._buffer:
                return 0
            pending = list(self._buffer)
            self._buffer.clear()
            self.trace.extend(pending)
            return len(pending)

