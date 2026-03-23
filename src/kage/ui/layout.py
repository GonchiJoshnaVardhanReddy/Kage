"""Layout and keyboard interaction helpers for terminal UI modes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rich.columns import Columns
from rich.panel import Panel
from rich.text import Text

KeyboardAction = Literal[
    "move_up",
    "move_down",
    "confirm",
    "cancel",
    "autocomplete",
    "history_search",
    "noop",
]


@dataclass(slots=True)
class LayoutFrame:
    """Simple layout frame for composable UI regions."""

    header: str = ""
    body: str = ""
    footer: str = ""

    def render(self) -> str:
        """Render a deterministic ASCII layout frame."""
        lines: list[str] = []
        if self.header:
            lines.append(self.header)
        if self.body:
            lines.append(self.body)
        if self.footer:
            lines.append(self.footer)
        return "\n".join(lines)


@dataclass(slots=True)
class SplitLayoutConfig:
    """Configuration for persistent split-layout rendering."""

    left_width: int = 24
    right_width: int = 24
    min_total_width_for_side_panels: int = 90


def _clamp(value: int, *, low: int, high: int) -> int:
    return max(low, min(high, value))


def render_split_layout(
    *,
    left_panel: Panel,
    center_panel: Panel,
    right_panel: Panel,
    terminal_width: int,
    config: SplitLayoutConfig | None = None,
    compact_right_label: str | None = None,
) -> Columns:
    """Render a persistent split layout with responsive right-panel collapse."""
    cfg = config or SplitLayoutConfig()
    left_width = _clamp(cfg.left_width, low=20, high=28)
    right_width = _clamp(cfg.right_width, low=20, high=28)
    center_min = 30
    show_right = terminal_width >= cfg.min_total_width_for_side_panels

    if show_right:
        center_width = max(center_min, terminal_width - left_width - right_width - 6)
        left_panel.width = left_width
        center_panel.width = center_width
        right_panel.width = right_width
        return Columns([left_panel, center_panel, right_panel], expand=False, equal=False)

    center_width = max(center_min, terminal_width - left_width - 4)
    left_panel.width = left_width
    center_panel.width = center_width
    compact = Text(compact_right_label or "[🦖 idle]", style="muted")
    return Columns([left_panel, center_panel, compact], expand=False, equal=False)


def map_keypress(key: str) -> KeyboardAction:
    """Map raw keypress text to a semantic keyboard action."""
    normalized = key.strip().lower()
    if normalized in {"up", "{up}", "k"}:
        return "move_up"
    if normalized in {"down", "{down}", "j"}:
        return "move_down"
    if normalized in {"enter", "{enter}", "return"}:
        return "confirm"
    if normalized in {"esc", "escape"}:
        return "cancel"
    if normalized in {"tab", "{tab}"}:
        return "autocomplete"
    if normalized in {"ctrl+r", "^r"}:
        return "history_search"
    return "noop"

