"""Hack mode CLI command."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.prompt import Prompt

from kage.cli.ui.themes import KAGE_THEME
from kage.persistence.config import KageConfig

# Console with theme
console = Console(theme=KAGE_THEME)

# Hack command app
hack_app = typer.Typer(
    name="hack",
    help="Autonomous penetration testing mode.",
    no_args_is_help=False,
)


@hack_app.callback(invoke_without_command=True)
def hack(
    ctx: typer.Context,  # noqa: ARG001
    target: str | None = typer.Argument(
        None,
        help="Target IP, domain, or URL to test.",
    ),
    scope: list[str] | None = typer.Option(
        None,
        "--scope",
        "-s",
        help="Additional targets in scope (can specify multiple).",
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        "-p",
        help="LLM provider to use.",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="Model name to use.",
    ),
    report_format: str = typer.Option(
        "html",
        "--format",
        "-f",
        help="Report format: markdown, html, pdf",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip authorization warning (use with caution!).",
    ),
) -> None:
    """
    Start autonomous penetration testing.

    HACK MODE runs a full penetration test automatically:

    1. PLANNING - Creates attack strategy
    2. RECON - Network/host reconnaissance
    3. ENUMERATION - Service & vulnerability enumeration
    4. EXPLOITATION - Tests discovered vulnerabilities
    5. REPORTING - Generates detailed report

    Requires written authorization to test target!

    Examples:

        kage hack 10.10.10.1

        kage hack example.com --scope api.example.com --scope admin.example.com

        kage hack 192.168.1.0/24 --format pdf
    """
    # If no target provided, prompt for it
    if not target:
        console.print()
        console.print("[bold cyan]KAGE HACK MODE[/bold cyan]")
        console.print("[dim]Autonomous penetration testing[/dim]")
        console.print()

        target = Prompt.ask(
            "[bold]Enter target[/bold] (IP, domain, or URL)",
        )

        if not target:
            console.print("[error]No target specified.[/error]")
            raise typer.Exit(1)

        # Ask for additional scope
        console.print()
        console.print("[dim]You can add additional targets to the scope.[/dim]")
        console.print("[dim]Press Enter with empty input when done.[/dim]")
        console.print()

        scope = scope or []
        while True:
            additional = Prompt.ask(
                "[bold]Additional scope target[/bold] (or press Enter to continue)",
                default="",
            )
            if not additional:
                break
            scope.append(additional)

    # Load config
    config = KageConfig.load()

    # Override config with CLI options
    if provider:
        config.llm.provider = provider
    if model:
        config.llm.model = model
    config.hack_mode.report_format = report_format

    # Build full scope
    full_scope = [target]
    if scope:
        full_scope.extend(scope)

    # Run hack mode
    from kage.core.hackmode import run_hack_mode

    asyncio.run(run_hack_mode(
        console=console,
        config=config,
        target=target,
        scope=full_scope,
        skip_warning=yes,
    ))
