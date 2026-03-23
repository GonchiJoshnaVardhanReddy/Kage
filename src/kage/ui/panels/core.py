"""Core panel builders for runtime diagnostics and previews."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from kage.ui.progress import WorkflowProgress
from kage.ui.status import StatusBarState, format_status_line

if TYPE_CHECKING:
    from kage.core.observability import TraceEvent
    from kage.core.prompt.context import CompiledPrompt
    from kage.core.tools import ToolExecutionPlan


def build_tool_preview_panel(
    *,
    plan: ToolExecutionPlan,
    policy_decision: str | None = None,
    confidence_score: float | None = None,
) -> Panel:
    """Render a structured tool preview panel before execution."""
    table = Table.grid(padding=(0, 1))
    table.add_column(style="muted", width=12)
    table.add_column(style="command")
    table.add_row("Tool", plan.tool_name)
    table.add_row("Arguments", str(plan.arguments))
    table.add_row("Confidence", f"{(confidence_score or plan.confidence_score or 0.0):.2f}")
    table.add_row("Policy", policy_decision or ("ask" if plan.approval_required else "allow"))
    return Panel(
        table,
        title="[panel.title]Tool Preview[/panel.title]",
        border_style="panel.border",
        padding=(0, 1),
    )


def build_workflow_progress_panel(progress: WorkflowProgress) -> Panel:
    """Render pipeline execution progress with active step highlighting."""
    table = Table(show_header=True, header_style="table.header", border_style="muted", expand=True)
    table.add_column("Agent")
    table.add_column("State", justify="center")
    for line in progress.render_lines():
        parts = line.split()
        name = parts[0]
        state = parts[-1]
        style = "status.pending"
        if state == "running":
            style = "status.running"
        elif state == "completed":
            style = "status.completed"
        elif state == "failed":
            style = "status.failed"
        table.add_row(name, f"[{style}]{state}[/{style}]")
    return Panel(
        table,
        title="[panel.title]Workflow Progress[/panel.title]",
        border_style="panel.border",
        padding=(0, 1),
    )


def build_parallel_agent_panel(states: Mapping[str, str]) -> Panel:
    """Render parallel-agent status view."""
    table = Table(show_header=True, header_style="table.header", border_style="muted", expand=True)
    table.add_column("Agent")
    table.add_column("Status", justify="center")
    for agent_name in sorted(states):
        state = states[agent_name]
        style = "status.pending"
        if state == "running":
            style = "status.running"
        elif state == "completed":
            style = "status.completed"
        elif state == "failed":
            style = "status.failed"
        table.add_row(agent_name, f"[{style}]{state}[/{style}]")
    return Panel(
        table,
        title="[panel.title]Parallel Agents[/panel.title]",
        border_style="panel.border",
        padding=(0, 1),
    )


def build_trace_debug_panel(events: list[TraceEvent]) -> Panel:
    """Render a compact trace debug panel for recent runtime events."""
    table = Table(show_header=True, header_style="table.header", border_style="muted", expand=True)
    table.add_column("Time", style="muted", width=12)
    table.add_column("Event", style="info")
    table.add_column("Component", style="subtitle")
    table.add_column("Payload", style="muted")
    for event in events[-12:]:
        payload = str(event.payload)[:120]
        table.add_row(
            event.timestamp.strftime("%H:%M:%S"),
            event.event_type,
            event.component,
            payload,
        )
    return Panel(
        table,
        title="[panel.title]Trace Debug[/panel.title]",
        border_style="panel.border",
        padding=(0, 1),
    )


def build_prompt_diagnostics_panel(compiled_prompt: CompiledPrompt) -> Panel:
    """Render prompt-layer diagnostics with token contribution estimates."""
    table = Table(show_header=True, header_style="table.header", border_style="muted", expand=True)
    table.add_column("Layer", style="info")
    table.add_column("Chars", justify="right")
    table.add_column("Tokens~", justify="right")
    for layer in compiled_prompt.layers:
        chars = len(layer.content)
        tokens = max(1, chars // 4)
        table.add_row(layer.name, str(chars), str(tokens))
    dropped = ", ".join(compiled_prompt.dropped_layers) if compiled_prompt.dropped_layers else "-"
    summary = Group(
        table,
        Text(f"Dropped: {dropped}", style="muted"),
        Text(f"Total Tokens~: {compiled_prompt.token_count_estimate}", style="info"),
    )
    return Panel(
        summary,
        title="[panel.title]Prompt Diagnostics[/panel.title]",
        border_style="panel.border",
        padding=(0, 1),
    )


def build_palette_panel(query: str, matches: list[tuple[str, str]]) -> Panel:
    """Render slash-command palette with fuzzy-matched entries."""
    table = Table(show_header=True, header_style="table.header", border_style="muted", expand=True)
    table.add_column("Command", style="command")
    table.add_column("Description", style="muted")
    for command, description in matches:
        table.add_row(command, description)
    title_query = query if query else "/"
    return Panel(
        table,
        title=f"[panel.title]Command Palette ({title_query})[/panel.title]",
        border_style="panel.border",
        padding=(0, 1),
    )


def build_status_bar_panel(state: StatusBarState) -> Panel:
    """Render persistent-like status footer panel."""
    return Panel(
        Text(format_status_line(state), style="muted"),
        border_style="muted",
        padding=(0, 1),
    )


def build_policy_decision_panel(decision: str, reason: str, details: dict[str, Any] | None = None) -> Panel:
    """Render one policy decision panel."""
    style = "safe" if decision == "allow" else "warning"
    if decision == "deny":
        style = "danger"
    detail_text = str(details or {})
    content = Text.from_markup(
        f"[{style}]Decision:[/{style}] {decision}\n"
        f"[muted]Reason:[/muted] {reason}\n"
        f"[muted]Details:[/muted] {detail_text}"
    )
    return Panel(
        content,
        title="[panel.title]Policy Decision[/panel.title]",
        border_style="panel.border",
        padding=(0, 1),
    )

