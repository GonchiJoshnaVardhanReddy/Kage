"""Diff-style preview and approval rendering for filesystem edits."""

from __future__ import annotations

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.syntax import Syntax

from .layout import map_keypress


def render_diff_panel(file_path: str, unified_diff: str) -> Panel:
    """Render syntax-highlighted diff panel."""
    syntax = Syntax(
        unified_diff[:8000],
        "diff",
        theme="monokai",
        line_numbers=False,
        word_wrap=True,
    )
    return Panel(
        syntax,
        title=f"[panel.title]Diff Preview: {file_path}[/panel.title]",
        border_style="warning",
        padding=(0, 1),
    )


def prompt_diff_approval(
    console: Console,
    *,
    file_path: str,
    unified_diff: str,
    allow_edit_option: bool = True,
) -> str:
    """Show diff panel and return approval action: y/n/edit."""
    renderable: RenderableType = render_diff_panel(file_path, unified_diff)
    console.print(renderable)
    choices = ["y", "n", "edit"] if allow_edit_option else ["y", "n"]
    selected = choices.index("n" if "n" in choices else choices[0])

    while True:
        hint = "/".join(choices)
        raw = console.input(f"Approve? ({hint}) [{choices[selected]}]: ").strip()
        if not raw:
            return choices[selected]

        action = map_keypress(raw)
        if action == "move_up":
            selected = (selected - 1) % len(choices)
            console.print(f"[muted]Selected: {choices[selected]}[/muted]")
            continue
        if action == "move_down":
            selected = (selected + 1) % len(choices)
            console.print(f"[muted]Selected: {choices[selected]}[/muted]")
            continue
        if action == "confirm":
            return choices[selected]
        if action == "cancel":
            return "n"

        normalized = raw.lower()
        if normalized in choices:
            return normalized
        console.print(f"[muted]Choose one of: {hint}[/muted]")

