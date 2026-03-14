"""Startup banner animation for Kage."""

from __future__ import annotations

import time

from rich.console import Console

# Kage ASCII frames for animation
KAGE_FRAMES = [
    # Frame 1 - empty/glitch
    "[bright_black]"
    "    ░░  ░░ ░░░░░  ░░░░░░ ░░░░░░░\n"
    "    ░░ ░░  ░░  ░░ ░░     ░░     \n"
    "    ░░░░   ░░░░░  ░░  ░░ ░░░░░  \n"
    "    ░░ ░░  ░░  ░░ ░░   ░ ░░     \n"
    "    ░░  ░░ ░░  ░░ ░░░░░░ ░░░░░░░"
    "[/bright_black]",
    # Frame 2 - partial reveal
    "[red]"
    "    ▓▓  ▓▓ ▓▓▓▓▓  ▓▓▓▓▓▓ ▓▓▓▓▓▓▓\n"
    "    ▓▓ ▓▓  ▓▓  ▓▓ ▓▓     ▓▓     \n"
    "    ▓▓▓▓   ▓▓▓▓▓  ▓▓  ▓▓ ▓▓▓▓▓  \n"
    "    ▓▓ ▓▓  ▓▓  ▓▓ ▓▓   ▓ ▓▓     \n"
    "    ▓▓  ▓▓ ▓▓  ▓▓ ▓▓▓▓▓▓ ▓▓▓▓▓▓▓"
    "[/red]",
    # Frame 3 - full logo
    "[bright_red bold]"
    "    ██╗  ██╗ █████╗  ██████╗ ███████╗\n"
    "    ██║ ██╔╝██╔══██╗██╔════╝ ██╔════╝\n"
    "    █████╔╝ ███████║██║  ███╗█████╗  \n"
    "    ██╔═██╗ ██╔══██║██║   ██║██╔══╝  \n"
    "    ██║  ██╗██║  ██║╚██████╔╝███████╗\n"
    "    ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝"
    "[/bright_red bold]",
]

# Tagline frames
TAGLINE_FRAMES = [
    "[bright_black]    ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░[/bright_black]",
    "[cyan]    ── AI-Powered Penetration Testing ──[/cyan]",
    "[bright_cyan bold]    ⚡ AI-Powered Penetration Testing ⚡[/bright_cyan bold]",
]

# Ninja star loading frames
LOADING_FRAMES = ["✦", "✧", "✦", "✧"]


def show_startup_banner(
    console: Console,
    provider: str = "ollama",
    model: str = "unknown",
) -> None:
    """Show the Kage startup banner (static, no animation)."""
    console.print()
    console.print(KAGE_FRAMES[-1])  # Final logo only
    console.print()
    console.print(TAGLINE_FRAMES[-1])  # Final tagline
    console.print()
    console.print(
        "    [bright_cyan]I am [bold]Kage[/bold][/bright_cyan]"
        "[cyan] — your AI pentest assistant[/cyan]"
    )
    console.print(
        f"    [bright_black]Powered by [white]{provider}[/white]"
        f" / [white]{model}[/white][/bright_black]"
    )
    console.print(
        "    [bright_black]Type [white]/help[/white] for commands"
        " • [white]/exit[/white] to quit[/bright_black]"
    )
    console.print()
    console.print("[bright_black]    ─────────────────────────────────────────[/bright_black]")
    console.print()


def play_startup_animation(
    console: Console,
    provider: str = "ollama",
    model: str = "unknown",
) -> None:
    """Play the Kage startup animation with identity intro.

    Deprecated: Use show_startup_banner() instead.
    """
    show_startup_banner(console, provider, model)


def _type_identity(
    console: Console,
    provider: str,
    model: str,
) -> None:
    """Display the Kage identity message with a typing effect."""
    lines = [
        (
            "    [bright_cyan]I am [bold]Kage[/bold][/bright_cyan]"
            "[cyan] — your AI pentest assistant[/cyan]"
        ),
        f"    [bright_black]Powered by [white]{provider}[/white] / [white]{model}[/white][/bright_black]",
        "    [bright_black]Type [white]/help[/white] for commands • [white]/exit[/white] to quit[/bright_black]",
    ]

    for line in lines:
        console.print(line)
        time.sleep(0.08)


def _show_static_banner(
    console: Console,
    provider: str,
    model: str,
) -> None:
    """Show a static banner when animation is not supported."""
    console.print()
    console.print(KAGE_FRAMES[-1])  # Final logo frame
    console.print()
    console.print(TAGLINE_FRAMES[-1])  # Final tagline
    console.print()
    console.print(
        "    [bright_cyan]I am [bold]Kage[/bold][/bright_cyan]"
        "[cyan] — your AI pentest assistant[/cyan]"
    )
    console.print(
        f"    [bright_black]Powered by [white]{provider}[/white]"
        f" / [white]{model}[/white][/bright_black]"
    )
    console.print(
        "    [bright_black]Type [white]/help[/white] for commands"
        " • [white]/exit[/white] to quit[/bright_black]"
    )
    console.print()
