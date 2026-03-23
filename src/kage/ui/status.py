"""Status-bar state and rendering helpers for interactive UI modes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class StatusBarState:
    """Immutable status-bar snapshot for one render cycle."""

    provider: str
    model: str
    active_workflow: str
    memory_usage: str
    policy_mode: str
    session_id: str


def _memory_usage_label(metadata: dict[str, Any]) -> str:
    blocks = metadata.get("memory_blocks")
    if isinstance(blocks, list):
        return f"{len(blocks)} block(s)"
    return "0 block(s)"


def build_status_state(
    *,
    provider: str,
    model: str,
    session_id: str,
    session_metadata: dict[str, Any],
    safe_mode: bool,
    active_workflow: str | None = None,
) -> StatusBarState:
    """Build a status-bar snapshot from runtime/session state."""
    workflow = active_workflow or str(session_metadata.get("workflow_name") or "-")
    policy_mode = "safe" if safe_mode else "unsafe"
    memory_usage = _memory_usage_label(session_metadata)
    return StatusBarState(
        provider=provider,
        model=model,
        active_workflow=workflow,
        memory_usage=memory_usage,
        policy_mode=policy_mode,
        session_id=session_id[:8],
    )


def format_status_line(state: StatusBarState) -> str:
    """Format one compact status bar line."""
    return (
        "[provider: "
        f"{state.provider}"
        " | model: "
        f"{state.model}"
        " | workflow: "
        f"{state.active_workflow}"
        " | memory: "
        f"{state.memory_usage}"
        " | safe-mode: "
        f"{state.policy_mode}"
        " | session: "
        f"{state.session_id}]"
    )

