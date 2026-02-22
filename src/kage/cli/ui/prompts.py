"""Rich UI prompt components for Kage."""

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.text import Text

from kage.core.models import Command


def prompt_user_input(console: Console) -> str:
    """Display the user input prompt."""
    console.print()
    return Prompt.ask("[prompt]kage[/prompt][prompt.arrow]>[/prompt.arrow]")


def prompt_command_approval(console: Console, command: Command) -> bool:
    """Prompt user to approve or reject a command."""
    console.print()

    # Show command details
    cmd_text = Text()
    cmd_text.append("Command: ", style="subtitle")
    cmd_text.append(command.command, style="command")
    console.print(cmd_text)

    if command.description:
        desc_text = Text()
        desc_text.append("Purpose: ", style="subtitle")
        desc_text.append(command.description, style="muted")
        console.print(desc_text)

    env_text = Text()
    env_text.append("Environment: ", style="subtitle")
    env_text.append(command.environment.value, style="info")
    console.print(env_text)

    console.print()

    return Confirm.ask(
        "[warning]Execute this command?[/warning]",
        default=False,
        console=console,
    )


def prompt_scope_warning(console: Console, target: str, command: str) -> bool:
    """Warn about potential out-of-scope action."""
    console.print()

    warning_panel = Panel(
        Text.from_markup(
            f"[warning]Potential out-of-scope target detected![/warning]\n\n"
            f"Target: [ip]{target}[/ip]\n"
            f"Command: [command]{command}[/command]\n\n"
            f"[muted]This target may not be within your defined scope.[/muted]"
        ),
        title="[unsafe]⚠ SCOPE WARNING[/unsafe]",
        border_style="danger",
    )
    console.print(warning_panel)

    return Confirm.ask(
        "[danger]Proceed anyway?[/danger]",
        default=False,
        console=console,
    )


def prompt_safe_mode_warning(console: Console, command: str, reason: str) -> bool:
    """Warn about dangerous command in safe mode."""
    console.print()

    warning_panel = Panel(
        Text.from_markup(
            f"[danger]Dangerous command blocked by Safe Mode![/danger]\n\n"
            f"Command: [command]{command}[/command]\n"
            f"Reason: [warning]{reason}[/warning]\n\n"
            f"[muted]Safe Mode prevents potentially destructive operations.[/muted]"
        ),
        title="[unsafe]🛡 SAFE MODE[/unsafe]",
        border_style="danger",
    )
    console.print(warning_panel)

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
    console.print("[assistant.thinking]Thinking...[/assistant.thinking]", end="\r")


def clear_thinking(console: Console) -> None:
    """Clear thinking indicator."""
    console.print(" " * 20, end="\r")
