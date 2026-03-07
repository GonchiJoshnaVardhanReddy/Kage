"""Startup banner animation for Kage."""

from __future__ import annotations

import sys
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


def play_startup_animation(
    console: Console,
    provider: str = "ollama",
    model: str = "unknown",
) -> None:
    """Play the Kage startup animation with identity intro."""
    # Check if terminal supports animation (not piped)
    if not sys.stdout.isatty():
        _show_static_banner(console, provider, model)
        return

    console.print()

    # Phase 1: Animate the logo (3 frames)
    for i, frame in enumerate(KAGE_FRAMES):
        # Move cursor up to overwrite previous frame (except first)
        if i > 0:
            console.print("\033[6A", end="")
        console.print(frame)
        time.sleep(0.15)

    console.print()

    # Phase 2: Animate the tagline
    for i, tagline in enumerate(TAGLINE_FRAMES):
        if i > 0:
            console.print("\033[1A", end="")
        console.print(tagline)
        time.sleep(0.12)

    console.print()

    # Phase 3: Identity intro with typing effect
    _type_identity(console, provider, model)

    console.print()
    console.print("[bright_black]    ─────────────────────────────────────────[/bright_black]")
    console.print()


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
