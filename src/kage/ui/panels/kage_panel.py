"""Kage identity side panel for split-layout runtime rendering."""

from __future__ import annotations

from dataclasses import dataclass

from rich.panel import Panel
from rich.table import Table


@dataclass(slots=True)
class KagePanelState:
    """State snapshot rendered in the persistent Kage identity panel."""

    provider: str = "-"
    model: str = "-"
    workflow: str = "-"
    policy_mode: str = "safe"
    session_id: str = "-"
    memory_usage: str = "0 block(s)"
    active_agent_step: str = "-"


def build_kage_panel(state: KagePanelState) -> Panel:
    """Render a compact persistent Kage identity panel."""
    table = Table.grid(padding=(0, 1))
    table.add_column(style="muted", width=9)
    table.add_column(style="info")
    table.add_row("provider", state.provider)
    table.add_row("model", state.model)
    table.add_row("workflow", state.workflow)
    table.add_row("policy", state.policy_mode)
    table.add_row("session", state.session_id)
    table.add_row("memory", state.memory_usage)
    table.add_row("agent", state.active_agent_step)
    return Panel(
        table,
        title="[panel.title]Kage[/panel.title]",
        border_style="panel.border",
        padding=(0, 1),
    )

