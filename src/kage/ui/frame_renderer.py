"""Frame layout composer for cinematic split UI."""

from __future__ import annotations

from rich.columns import Columns
from rich.panel import Panel

from .layout import SplitLayoutConfig, render_split_layout


def render_layout(
    *,
    left_panel: Panel,
    center_panel: Panel,
    right_panel: Panel,
    terminal_width: int,
    config: SplitLayoutConfig | None = None,
    compact_right_label: str | None = None,
) -> Columns:
    """Compose persistent split frame from side panels and center panel."""
    return render_split_layout(
        left_panel=left_panel,
        center_panel=center_panel,
        right_panel=right_panel,
        terminal_width=terminal_width,
        config=config,
        compact_right_label=compact_right_label,
    )

