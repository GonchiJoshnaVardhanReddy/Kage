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
    no_args_is_help=False,
    rich_markup_mode="rich",
    invoke_without_command=True,
)


def version_callback(value: bool) -> None:
    """Display version information."""
    if value:
        console.print(KAGE_LOGO_SMALL)
        console.print(f"[muted]Version: {__version__}[/muted]")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
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
    if ctx.invoked_subcommand is None:
        # No subcommand - show intro banner
        console.print(KAGE_LOGO)
        console.print()
        console.print(f"[muted]Version {__version__}[/muted]")
        console.print()
        console.print("[header]Quick Start[/header]")
        console.print("  [command]kage setup[/command]     Run first-time setup wizard")
        console.print("  [command]kage chat[/command]      Start interactive session")
        console.print("  [command]kage --help[/command]    Show all commands")
        console.print()
        console.print("[muted]For authorized security testing only.[/muted]")


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
    output: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file for export.",
    ),
) -> None:
    """Manage penetration testing sessions."""
    import asyncio

    from kage.persistence import SessionStorage

    storage = SessionStorage()

    if action == "list":
        sessions = asyncio.run(storage.list_sessions(limit=20))

        if not sessions:
            console.print("[muted]No sessions found.[/muted]")
            return

        from rich.table import Table
        table = Table(title="Sessions", header_style="table.header")
        table.add_column("ID", style="highlight")
        table.add_column("Updated", style="muted")
        table.add_column("Scope", style="info")
        table.add_column("Msgs", style="muted")
        table.add_column("Cmds", style="muted")
        table.add_column("Findings", style="muted")

        for s in sessions:
            table.add_row(
                s["id"][:8],
                s.get("updated_at", "")[:10],
                s.get("scope_summary", "-")[:30],
                str(s.get("message_count", 0)),
                str(s.get("command_count", 0)),
                str(s.get("finding_count", 0)),
            )

        console.print(table)
        console.print()
        console.print("[muted]Use 'kage session resume <id>' to resume a session.[/muted]")

    elif action == "resume":
        if not session_id:
            console.print("[error]Session ID required.[/error]")
            raise typer.Exit(1)

        # Launch chat with session ID
        config = KageConfig.load()

        from kage.cli.ui.themes import KAGE_LOGO

        console.clear()
        console.print(KAGE_LOGO)

        from kage.cli.commands.chat import chat_loop
        chat_loop(console, config, session_id=session_id, scope=None)

    elif action == "export":
        if not session_id:
            console.print("[error]Session ID required.[/error]")
            raise typer.Exit(1)

        from pathlib import Path
        output_path = Path(output) if output else Path(f"session_{session_id[:8]}.md")
        fmt = "markdown" if output_path.suffix == ".md" else "json"

        success = asyncio.run(storage.export_session(session_id, output_path, fmt))

        if success:
            console.print(f"[success]Exported to: {output_path}[/success]")
        else:
            console.print(f"[error]Session not found: {session_id}[/error]")

    elif action == "delete":
        if not session_id:
            console.print("[error]Session ID required.[/error]")
            raise typer.Exit(1)

        from rich.prompt import Confirm
        if Confirm.ask(f"[warning]Delete session {session_id[:8]}?[/warning]", default=False):
            success = asyncio.run(storage.delete(session_id))
            if success:
                console.print("[success]Session deleted.[/success]")
            else:
                console.print(f"[error]Session not found: {session_id}[/error]")

    else:
        console.print(f"[error]Unknown action: {action}[/error]")
        console.print("[muted]Available actions: list, resume, export, delete[/muted]")
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
    template: str | None = typer.Option(
        None,
        "--template",
        "-t",
        help="Template to use (e.g., owasp/report.md.j2).",
    ),
) -> None:
    """Generate penetration testing reports."""
    import asyncio
    from pathlib import Path

    from kage.persistence import SessionStorage
    from kage.reporting import ReportExporter, get_default_filename

    storage = SessionStorage()

    if action == "generate":
        # Need a session ID
        if not session_id:
            # Try to get the most recent session
            sessions = asyncio.run(storage.list_sessions(limit=1))
            if not sessions:
                console.print("[error]No sessions found. Specify a session with --session.[/error]")
                raise typer.Exit(1)
            session_id = sessions[0]["id"]
            console.print(f"[info]Using most recent session: {session_id[:8]}[/info]")

        # Load session
        session = asyncio.run(storage.load(session_id))
        if not session:
            console.print(f"[error]Session not found: {session_id}[/error]")
            raise typer.Exit(1)

        # Determine output path
        if output:
            output_path = Path(output)
        else:
            filename = get_default_filename(session, format)
            output_path = Path.cwd() / filename

        # Generate report
        console.print(f"[info]Generating {format} report...[/info]")

        try:
            exporter = ReportExporter()
            result_path = asyncio.run(
                exporter.export(session, output_path, format, template)
            )
            console.print(f"[success]Report generated: {result_path}[/success]")

            # Show summary
            from kage.reporting import FindingStats
            stats = FindingStats(session.findings)
            console.print()
            console.print(f"[muted]Session: {session.id[:8]}[/muted]")
            console.print(f"[muted]Findings: {stats.total} (Critical: {stats.critical}, High: {stats.high}, Medium: {stats.medium})[/muted]")
            console.print(f"[muted]Risk Rating: {stats.risk_rating}[/muted]")

        except Exception as e:
            console.print(f"[error]Failed to generate report: {e}[/error]")
            raise typer.Exit(1)

    elif action == "list":
        # List available templates
        from kage.reporting import ReportEngine
        engine = ReportEngine()
        templates = engine.list_templates()

        if not templates:
            console.print("[muted]No templates found.[/muted]")
            return

        console.print("[header]Available Report Templates[/header]")
        console.print()
        for tmpl in templates:
            console.print(f"  • {tmpl}")
        console.print()
        console.print("[muted]Use --template to specify a template.[/muted]")

    elif action == "view":
        # View a generated report
        if not output:
            console.print("[error]Specify report file with --output.[/error]")
            raise typer.Exit(1)

        report_path = Path(output)
        if not report_path.exists():
            console.print(f"[error]Report not found: {output}[/error]")
            raise typer.Exit(1)

        # Open in default browser/viewer
        import webbrowser
        webbrowser.open(str(report_path.absolute()))
        console.print(f"[success]Opened: {report_path}[/success]")

    else:
        console.print(f"[error]Unknown action: {action}[/error]")
        console.print("[muted]Available actions: generate, list, view[/muted]")
        raise typer.Exit(1)


# Import and register plugin subcommand app
from kage.cli.commands.plugin import plugin_app

app.add_typer(plugin_app, name="plugin")

# Import and register hack mode command
from kage.cli.commands.hack import hack_app

app.add_typer(hack_app, name="hack")


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
