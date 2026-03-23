"""Dinosaur animation side panel for split-layout runtime rendering."""

from __future__ import annotations

from rich.panel import Panel
from rich.text import Text


def build_dinosaur_panel(*, frame: str, status: str) -> Panel:
    """Render the dinosaur panel for the active animation frame/state."""
    content = Text()
    content.append(frame, style="highlight")
    content.append("\n")
    content.append(status, style="muted")
    return Panel(
        content,
        title="[panel.title]Companion[/panel.title]",
        border_style="panel.border",
        padding=(0, 1),
    )


def build_dinosaur_compact_label(*, frame: str, status: str) -> str:
    """Render compact fallback label when right panel is collapsed."""
    compact = status.strip().lower() or "idle"
    icon = frame.strip().splitlines()[0].strip() if frame.strip() else "🦖"
    return f"[{icon} {compact}]"

