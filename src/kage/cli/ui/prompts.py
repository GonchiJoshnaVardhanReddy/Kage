"""Rich UI prompt components for Kage."""

from __future__ import annotations

from enum import Enum
from time import perf_counter

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.text import Text

from kage.cli.ui.panels import (
    create_danger_confirmation_box,
    create_diff_box,
    create_plan_tracker_panel,
)
from kage.core.models import Command


class ApprovalChoice(str, Enum):
    """User approval choices for command execution."""

    ALWAYS = "1"
    APPROVE_TOOL = "2"
    RUN_ONCE = "3"
    CANCEL = "4"


class FileCreateApprovalChoice(str, Enum):
    """User approval choices for file creation."""

    ALWAYS_ASK = "1"
    APPROVE_ONCE = "2"
    AUTO_APPROVE_CREATES = "3"
    CANCEL = "4"


SPINNER_FRAMES = ["⠋", "⠙", "⠸", "⠴", "⠦", "⠇"]


def prompt_user_input(console: Console) -> str:
    """Display the user input prompt."""
    console.print()
    return Prompt.ask("[prompt]kage[/prompt][prompt.arrow]>[/prompt.arrow]")


def prompt_command_approval(
    console: Console,
    command: Command,
    session_approved_all: bool = False,
    session_approved_tools: set[str] | None = None,
) -> ApprovalChoice:
    """Prompt user to approve or reject a command with granular options.

    Returns the user's choice. If the command was pre-approved via session
    preferences (always-approve or tool-approve), returns automatically.
    """
    # Auto-approve if user chose "always approve" this session
    if session_approved_all:
        return ApprovalChoice.RUN_ONCE

    # Auto-approve if user approved this tool type
    if session_approved_tools:
        tool = command.command.strip().split()[0].lower() if command.command.strip() else ""
        if tool in session_approved_tools:
            return ApprovalChoice.RUN_ONCE

    console.print()

    # Build the approval panel
    lines = []
    lines.append(f"[command]{command.command}[/command]")
    if command.description:
        lines.append(f"[muted]{command.description}[/muted]")
    lines.append(f"[subtitle]Environment:[/subtitle] [info]{command.environment.value}[/info]")

    console.print(Panel(
        "\n".join(lines),
        title="[warning]⚡ AI wants to run[/warning]",
        border_style="yellow",
        padding=(1, 2),
    ))

    console.print()
    console.print("[bold]Options:[/bold]")
    console.print("  [green][1][/green] Always approve (this session)")
    console.print("  [cyan][2][/cyan] Approve this tool")
    console.print("  [yellow][3][/yellow] Run this command only")
    console.print("  [red][4][/red] Cancel")
    console.print()

    choice = Prompt.ask(
        "[prompt]Choose[/prompt]",
        choices=["1", "2", "3", "4"],
        default="4",
        console=console,
    )

    return ApprovalChoice(choice)


def prompt_file_approval(
    console: Console,
    action: str,
    file_path: str,
    content_preview: str | None = None,
) -> bool:
    """Prompt user to approve a file operation.

    Args:
        console: Rich console.
        action: The operation type (create, write, edit).
        file_path: Target file path.
        content_preview: Optional truncated content preview.
    """
    console.print()

    lines = []
    lines.append(f"[subtitle]Action:[/subtitle] [warning]{action}[/warning]")
    lines.append(f"[subtitle]File:[/subtitle] [command]{file_path}[/command]")

    console.print(
        Panel(
            "\n".join(lines),
            title="[warning]File Operation[/warning]",
            border_style="yellow",
            padding=(1, 2),
        )
    )

    if content_preview:
        console.print(create_diff_box(file_path, content_preview, action))

    return Confirm.ask(
        "[warning]Approve?[/warning]",
        default=False,
        console=console,
    )


def prompt_file_create_approval(
    console: Console,
    file_path: str,
    content_preview: str | None = None,
) -> FileCreateApprovalChoice:
    """Prompt user to approve file creation with session-level options."""
    console.print()

    lines = []
    lines.append("[subtitle]Action:[/subtitle] [warning]create[/warning]")
    lines.append(f"[subtitle]File:[/subtitle] [command]{file_path}[/command]")
    if content_preview:
        preview = content_preview[:1200] + ("..." if len(content_preview) > 1200 else "")
        lines.append(f"\n[muted]{preview}[/muted]")

    console.print(Panel(
        "\n".join(lines),
        title="[warning]📄 AI wants to create file[/warning]",
        border_style="yellow",
        padding=(1, 2),
    ))

    console.print()
    console.print("[bold]Options:[/bold]")
    console.print("  [cyan][1][/cyan] Always ask")
    console.print("  [yellow][2][/yellow] Approve once")
    console.print("  [green][3][/green] Auto-approve file creates (this session)")
    console.print("  [red][4][/red] Cancel")
    console.print()

    choice = Prompt.ask(
        "[prompt]Choose[/prompt]",
        choices=["1", "2", "3", "4"],
        default="1",
        console=console,
    )
    return FileCreateApprovalChoice(choice)


def prompt_plan_approval(
    console: Console,
    steps: list[tuple[int, str, str | None]],
    description: str | None = None,
) -> str:
    """Display a multi-step execution plan and ask for approval.

    Args:
        console: Rich console.
        steps: List of (index, command, description) tuples.
        description: Optional plan description.

    Returns:
        User choice: "run", "edit", or "cancel".
    """
    console.print()

    console.print(create_plan_tracker_panel(steps, description or "Execution Plan"))

    console.print()
    console.print("[bold]Options:[/bold]")
    console.print("  [green]run[/green]    — Execute all steps")
    console.print("  [yellow]edit[/yellow]   — Remove steps before running")
    console.print("  [red]cancel[/red] — Discard the plan")
    console.print()

    choice = Prompt.ask(
        "[prompt]Choose[/prompt]",
        choices=["run", "edit", "cancel"],
        default="cancel",
        console=console,
    )
    return choice


def prompt_plan_edit(console: Console, total_steps: int) -> list[int]:
    """Ask which steps to remove from the plan.

    Returns list of 1-based step indices to remove.
    """
    console.print()
    raw = Prompt.ask(
        "[prompt]Steps to remove (comma-separated, e.g. 2,3)[/prompt]",
        console=console,
    )

    to_remove = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part)
            if 1 <= idx <= total_steps:
                to_remove.append(idx)

    return to_remove


def prompt_scope_definition(console: Console, target: str) -> str:
    """Prompt user to define scope when none exists.

    Returns user choice: "add", "define", or "skip".
    """
    console.print()

    console.print(Panel(
        Text.from_markup(
            f"[warning]No scope defined for this session.[/warning]\n\n"
            f"Detected target: [ip]{target}[/ip]\n\n"
            f"[muted]Scope restricts which hosts can be targeted.[/muted]"
        ),
        title="[warning]🎯 Scope Required[/warning]",
        border_style="yellow",
        padding=(1, 2),
    ))

    console.print()
    console.print("[bold]Options:[/bold]")
    console.print(f"  [green]add[/green]    — Add [ip]{target}[/ip] to scope")
    console.print("  [yellow]define[/yellow] — Enter full scope manually")
    console.print("  [red]skip[/red]   — Run without scope")
    console.print()

    return Prompt.ask(
        "[prompt]Choose[/prompt]",
        choices=["add", "define", "skip"],
        default="add",
        console=console,
    )


def prompt_scope_input(console: Console) -> str:
    """Ask user to enter scope targets."""
    console.print()
    return Prompt.ask(
        "[prompt]Enter scope (comma-separated IPs, CIDRs, domains)[/prompt]",
        console=console,
    )


def prompt_scope_authorization(console: Console, target: str) -> bool:
    """Ask user to confirm authorization when scope is not explicitly defined."""
    console.print()
    console.print(Panel(
        Text.from_markup(
            f"[warning]Target detected:[/warning] [ip]{target}[/ip]\n\n"
            "[warning]No scope defined.[/warning]\n"
            "Please confirm this target is authorized for testing."
        ),
        title="[warning]🎯 Authorization Check[/warning]",
        border_style="yellow",
        padding=(1, 2),
    ))
    return Confirm.ask(
        "[warning]Authorized target?[/warning]",
        default=False,
        console=console,
    )


def prompt_scope_warning(console: Console, target: str, command: str) -> bool:
    """Warn about potential out-of-scope action."""
    console.print()

    console.print(
        create_danger_confirmation_box(
            f"Potential out-of-scope target detected: {target}",
            command=command,
        )
    )
    console.print("[muted]This target may not be within your defined scope.[/muted]")

    return Confirm.ask(
        "[danger]Proceed anyway?[/danger]",
        default=False,
        console=console,
    )


def prompt_safe_mode_warning(console: Console, command: str, reason: str) -> bool:
    """Warn about dangerous command in safe mode."""
    console.print()

    console.print(
        create_danger_confirmation_box(
            f"Dangerous command blocked by Safe Mode ({reason})",
            command=command,
        )
    )
    console.print("[muted]Safe Mode prevents potentially destructive operations.[/muted]")

    return Confirm.ask(
        "[danger]Override Safe Mode and execute?[/danger]",
        default=False,
        console=console,
    )


def prompt_first_run(console: Console) -> bool:
    """Ask if user wants to run setup wizard."""
    console.print()
    return Confirm.ask(
        "[info]First time running Kage. Run setup wizard?[/info]",
        default=True,
        console=console,
    )


def show_thinking(console: Console) -> None:
    """Show thinking indicator."""
    frame = SPINNER_FRAMES[int(perf_counter() * 8) % len(SPINNER_FRAMES)]
    console.print(f"[assistant.thinking]{frame} Thinking...[/assistant.thinking]", end="\r")


def clear_thinking(console: Console) -> None:
    """Clear thinking indicator."""
    console.print(" " * 20, end="\r")
