"""Main CLI application for Kage."""

from __future__ import annotations

import typer
from rich.console import Console

from kage.cli.ui.themes import KAGE_LOGO, KAGE_LOGO_SMALL, KAGE_THEME
from kage.persistence.config import KageConfig
from kage.version import __version__

# Create main console with theme
console = Console(theme=KAGE_THEME)

# Main CLI app
app = typer.Typer(
    name="kage",
    help="AI-powered penetration testing CLI assistant.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def version_callback(value: bool) -> None:
    """Display version information."""
    if value:
        console.print(KAGE_LOGO_SMALL)
        console.print(f"[muted]Version: {__version__}[/muted]")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Kage - AI-powered penetration testing CLI assistant."""
    pass


@app.command()
def setup() -> None:
    """Run the first-time setup wizard."""
    from kage.cli.wizard import run_setup_wizard
    run_setup_wizard(console)


@app.command()
def chat(
    scope: str | None = typer.Option(
        None,
        "--scope",
        "-s",
        help="Target scope (IP, CIDR, or domain).",
    ),
    session_id: str | None = typer.Option(
        None,
        "--session",
        "-S",
        help="Resume existing session by ID.",
    ),
    safe_mode: bool | None = typer.Option(
        None,
        "--safe/--unsafe",
        help="Enable or disable safe mode.",
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        "-p",
        help="LLM provider to use (ollama, openai).",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="Model name to use.",
    ),
) -> None:
    """Start an interactive penetration testing session."""
    config = KageConfig.load()
    
    # Check first run
    if config.first_run:
        from kage.cli.ui.prompts import prompt_first_run
        if prompt_first_run(console):
            from kage.cli.wizard import run_setup_wizard
            config = run_setup_wizard(console)
        else:
            config.first_run = False
            config.save()
    
    # Override config with CLI options
    if provider:
        config.llm.provider = provider
    if model:
        config.llm.model = model
    if safe_mode is not None:
        config.security.safe_mode = safe_mode
    
    # Display header
    console.clear()
    console.print(KAGE_LOGO)
    
    from kage.cli.ui.panels import create_status_panel
    console.print(create_status_panel(
        safe_mode=config.security.safe_mode,
        scope=None,  # TODO: Load from session or parse from --scope
        session_id=session_id,
        provider=config.llm.provider,
        model=config.llm.model,
    ))
    
    console.print()
    console.print("[info]Type your message or [command]/help[/command] for commands.[/info]")
    console.print("[muted]Press Ctrl+C to exit.[/muted]")
    
    # Start chat loop
    from kage.cli.commands.chat import chat_loop
    chat_loop(console, config, session_id, scope)


@app.command()
def config_cmd(
    show: bool = typer.Option(
        False,
        "--show",
        help="Show current configuration.",
    ),
    edit: bool = typer.Option(
        False,
        "--edit",
        help="Open configuration in editor.",
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        help="Reset configuration to defaults.",
    ),
) -> None:
    """Manage Kage configuration."""
    config = KageConfig.load()
    
    if show or (not edit and not reset):
        import yaml
        console.print("[header]Current Configuration[/header]")
        console.print()
        console.print(yaml.dump(config.model_dump(mode="json"), default_flow_style=False))
        console.print()
        console.print(f"[muted]Config file: {config.get_config_path()}[/muted]")
    
    if reset:
        from rich.prompt import Confirm
        if Confirm.ask("[warning]Reset configuration to defaults?[/warning]", default=False):
            new_config = KageConfig()
            new_config.save()
            console.print("[success]Configuration reset.[/success]")


# Rename to avoid conflict with typer
app.command(name="config")(config_cmd)


@app.command()
def session(
    action: str = typer.Argument(
        ...,
        help="Action: list, resume, export, delete",
    ),
    session_id: str | None = typer.Argument(
        None,
        help="Session ID (for resume, export, delete).",
    ),
) -> None:
    """Manage penetration testing sessions."""
    if action == "list":
        console.print("[info]Session listing not yet implemented.[/info]")
    elif action == "resume":
        if not session_id:
            console.print("[error]Session ID required.[/error]")
            raise typer.Exit(1)
        # TODO: Implement session resume
        console.print(f"[info]Resuming session {session_id}...[/info]")
    elif action == "export":
        if not session_id:
            console.print("[error]Session ID required.[/error]")
            raise typer.Exit(1)
        console.print(f"[info]Exporting session {session_id}...[/info]")
    elif action == "delete":
        if not session_id:
            console.print("[error]Session ID required.[/error]")
            raise typer.Exit(1)
        console.print(f"[info]Deleting session {session_id}...[/info]")
    else:
        console.print(f"[error]Unknown action: {action}[/error]")
        raise typer.Exit(1)


@app.command()
def report(
    action: str = typer.Argument(
        "generate",
        help="Action: generate, list, view",
    ),
    session_id: str | None = typer.Option(
        None,
        "--session",
        "-S",
        help="Session ID to generate report from.",
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path.",
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Output format: markdown, html, pdf",
    ),
) -> None:
    """Generate penetration testing reports."""
    if action == "generate":
        console.print(f"[info]Generating {format} report...[/info]")
        # TODO: Implement report generation
    else:
        console.print(f"[error]Unknown action: {action}[/error]")
        raise typer.Exit(1)


@app.command()
def plugin(
    action: str = typer.Argument(
        "list",
        help="Action: list, info, enable, disable",
    ),
    plugin_name: str | None = typer.Argument(
        None,
        help="Plugin name.",
    ),
) -> None:
    """Manage Kage plugins."""
    if action == "list":
        console.print("[info]Plugin listing not yet implemented.[/info]")
    elif action == "info":
        if not plugin_name:
            console.print("[error]Plugin name required.[/error]")
            raise typer.Exit(1)
        console.print(f"[info]Plugin info: {plugin_name}[/info]")
    else:
        console.print(f"[error]Unknown action: {action}[/error]")
        raise typer.Exit(1)


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
