"""Trace export helpers for diagnostics and replay tooling."""

from __future__ import annotations

import json

from .session_trace import SessionTrace


def export_json(trace: SessionTrace) -> str:
    """Export full trace as formatted JSON."""
    return json.dumps(
        {
            "events": [event.model_dump(mode="json") for event in trace.events],
        },
        indent=2,
    )


def export_jsonl(trace: SessionTrace) -> str:
    """Export trace events as JSONL."""
    lines = [json.dumps(event.model_dump(mode="json")) for event in trace.events]
    return "\n".join(lines)

