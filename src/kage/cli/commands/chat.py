"""Interactive chat command for Kage."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel

from kage.ai.providers import create_provider
from kage.core.conversation import ConversationManager
from kage.core.models import Command, CommandStatus, Session, Target

if TYPE_CHECKING:
    from kage.persistence.config import KageConfig


class ChatSession:
    """Manages an interactive chat session."""

    def __init__(
        self,
        console: Console,
        config: KageConfig,
        session_id: str | None = None,
        scope: str | None = None,
    ) -> None:
        self.console = console
        self.config = config
        self.session = Session()
        self.running = True
        self.provider = None
        self.conversation: ConversationManager | None = None
        self._pending_commands: list[Command] = []
        self._session_storage = None
        self._auto_save = None
        self._resumed = False

        # Try to resume existing session
        if session_id:
            asyncio.run(self._try_resume_session(session_id))

        # Initialize scope if provided (only if not resumed)
        if scope and not self._resumed:
            self._parse_and_add_scope(scope)

        # Override safe mode from config (only if not resumed)
        if not self._resumed:
            self.session.safe_mode = config.security.safe_mode

    async def _try_resume_session(self, session_id: str) -> bool:
        """Try to resume an existing session."""
        from kage.persistence import SessionStorage

        self._session_storage = SessionStorage()

        # Try exact match first
        loaded = await self._session_storage.load(session_id)

        # Try partial match if exact fails
        if not loaded:
            sessions = await self._session_storage.list_sessions()
            for s in sessions:
                if s["id"].startswith(session_id):
                    loaded = await self._session_storage.load(s["id"])
                    break

        if loaded:
            self.session = loaded
            self._resumed = True
            self.console.print(f"[success]Resumed session: {self.session.id[:8]}[/success]")
            self.console.print(f"[muted]Messages: {len(self.session.messages)}, Commands: {len(self.session.commands)}[/muted]")
            return True

        self.console.print(f"[warning]Session not found: {session_id}[/warning]")
        self.console.print("[muted]Starting new session instead.[/muted]")
        return False

    def _parse_and_add_scope(self, scope_str: str) -> None:
        """Parse scope string and add targets."""
        import ipaddress

        parts = scope_str.split(",")
        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Determine target type
            target_type = "domain"
            try:
                ipaddress.ip_address(part)
                target_type = "ip"
            except ValueError:
                try:
                    ipaddress.ip_network(part, strict=False)
                    target_type = "cidr"
                except ValueError:
                    if part.startswith(("http://", "https://")):
                        target_type = "url"

            self.session.scope.targets.append(Target(value=part, target_type=target_type))

    async def _init_provider(self) -> bool:
        """Initialize the LLM provider."""
        try:
            self.provider = create_provider(self.config.llm)

            # Check connection
            self.console.print(
                "[assistant.thinking]Connecting to LLM...[/assistant.thinking]", end="\r"
            )
            connected = await self.provider.check_connection()
            self.console.print(" " * 40, end="\r")

            if not connected:
                self.console.print(
                    f"[error]Could not connect to {self.config.llm.provider} "
                    f"at {self.config.llm.base_url}[/error]"
                )
                self.console.print(
                    "[muted]Check that the service is running and try again.[/muted]"
                )
                return False

            # Initialize conversation manager
            self.conversation = ConversationManager(
                provider=self.provider,
                config=self.config,
                session=self.session,
            )

            return True

        except Exception as e:
            self.console.print(f"[error]Failed to initialize LLM provider: {e}[/error]")
            return False

    def _handle_slash_command(self, command: str) -> bool:
        """Handle slash commands. Returns True if should continue loop."""
        parts = command[1:].split(maxsplit=1)
        cmd = parts[0].lower()

        if cmd in ("exit", "quit", "q"):
            self.running = False
            self.console.print("[muted]Ending session...[/muted]")
            return False

        elif cmd == "help":
            self._show_help()

        elif cmd == "clear":
            self.console.clear()

        elif cmd == "scope":
            self._show_scope()

        elif cmd in ("safe", "safemode"):
            self.session.safe_mode = not self.session.safe_mode
            status = "enabled" if self.session.safe_mode else "disabled"
            style = "safe" if self.session.safe_mode else "unsafe"
            self.console.print(f"[{style}]Safe mode {status}[/{style}]")

        elif cmd == "findings":
            self._show_findings()

        elif cmd == "history":
            self._show_history()

        elif cmd == "status":
            self._show_status()

        elif cmd == "run":
            self._run_pending_commands()

        elif cmd == "commands":
            self._show_pending_commands()

        elif cmd == "save":
            self._save_session()

        elif cmd == "export":
            args = parts[1] if len(parts) > 1 else ""
            self._export_session(args)

        elif cmd == "model":
            self._change_model()

        elif cmd in ("hacker", "hack"):
            self._enter_hacker_mode()
            return False  # Exit chat loop to enter hack mode

        # Easter egg - hidden command
        elif command.lower() in ("/whoareyou", "/who are you", "/who are you?"):
            self._show_easter_egg()

        else:
            self.console.print(f"[error]Unknown command: /{cmd}[/error]")
            self.console.print("[muted]Type /help for available commands.[/muted]")

        return True

    def _show_help(self) -> None:
        """Display help information."""
        help_text = """
[header]Available Commands[/header]

[command]/help[/command]        - Show this help message
[command]/exit[/command]        - End the session
[command]/clear[/command]       - Clear the screen
[command]/model[/command]       - Change LLM model/provider
[command]/hacker[/command]      - Enter autonomous hack mode
[command]/scope[/command]       - Show current scope
[command]/safe[/command]        - Toggle safe mode
[command]/findings[/command]    - List discovered findings
[command]/history[/command]     - Show command history
[command]/status[/command]      - Show session status
[command]/commands[/command]    - Show pending commands
[command]/run[/command]         - Execute pending commands
[command]/save[/command]        - Save current session
[command]/export [path][/command] - Export session to file

[header]Tips[/header]

• Describe what you want to achieve, and I'll suggest commands
• All commands require your approval before execution
• Use safe mode to prevent dangerous operations
• Define your scope to prevent accidental out-of-scope testing
• Sessions auto-save periodically
"""
        self.console.print(help_text)

    def _show_scope(self) -> None:
        """Display current scope."""
        from kage.cli.ui.panels import create_scope_panel

        self.console.print(create_scope_panel(self.session.scope))

    def _show_findings(self) -> None:
        """Display findings."""
        if not self.session.findings:
            self.console.print("[muted]No findings recorded yet.[/muted]")
            return

        from kage.cli.ui.panels import create_finding_panel

        for finding in self.session.findings:
            self.console.print(create_finding_panel(finding))

    def _show_history(self) -> None:
        """Display command history."""
        if not self.session.commands:
            self.console.print("[muted]No commands executed yet.[/muted]")
            return

        from rich.table import Table

        table = Table(title="Command History", header_style="table.header")
        table.add_column("ID", style="muted")
        table.add_column("Command", style="command")
        table.add_column("Status", style="info")
        table.add_column("Exit Code", style="muted")

        for cmd in self.session.commands[-20:]:
            table.add_row(
                cmd.id[:8],
                cmd.command[:50] + ("..." if len(cmd.command) > 50 else ""),
                cmd.status.value,
                str(cmd.exit_code) if cmd.exit_code is not None else "-",
            )

        self.console.print(table)

    def _show_status(self) -> None:
        """Display session status."""
        from kage.cli.ui.panels import create_status_panel

        self.console.print(
            create_status_panel(
                safe_mode=self.session.safe_mode,
                scope=self.session.scope,
                session_id=self.session.id,
                provider=self.config.llm.provider,
                model=self.config.llm.model,
            )
        )

    def _show_pending_commands(self) -> None:
        """Show commands pending approval."""
        if not self._pending_commands:
            self.console.print("[muted]No pending commands.[/muted]")
            return

        self.console.print("[header]Pending Commands[/header]")
        for i, cmd in enumerate(self._pending_commands, 1):
            self.console.print(f"  [{i}] [command]{cmd.command}[/command]")
            if cmd.description:
                self.console.print(f"      [muted]{cmd.description}[/muted]")

    def _save_session(self) -> None:
        """Save the current session."""
        from kage.persistence import SessionStorage

        if not self._session_storage:
            self._session_storage = SessionStorage()

        path = asyncio.run(self._session_storage.save(self.session))
        self.console.print(f"[success]Session saved: {self.session.id[:8]}[/success]")
        self.console.print(f"[muted]Path: {path}[/muted]")

    def _export_session(self, args: str) -> None:
        """Export the current session to a file."""
        from pathlib import Path

        from kage.persistence import SessionStorage

        if not self._session_storage:
            self._session_storage = SessionStorage()

        # Determine output path and format
        if args:
            output_path = Path(args)
        else:
            output_path = Path(f"session_{self.session.id[:8]}.md")

        fmt = "markdown" if output_path.suffix == ".md" else "json"

        success = asyncio.run(
            self._session_storage.export_session(self.session.id, output_path, fmt)
        )

        if success:
            self.console.print(f"[success]Exported to: {output_path}[/success]")
        else:
            # Save first then export
            asyncio.run(self._session_storage.save(self.session))
            success = asyncio.run(
                self._session_storage.export_session(self.session.id, output_path, fmt)
            )
            if success:
                self.console.print(f"[success]Exported to: {output_path}[/success]")
            else:
                self.console.print("[error]Failed to export session[/error]")

    def _show_easter_egg(self) -> None:
        """Display the hidden easter egg."""
        joker_card = """
[bold red]    ┌─────────────────────┐[/bold red]
[bold red]    │ ♠                 ♠ │[/bold red]
[bold red]    │                     │[/bold red]
[bold red]    │      [yellow]▄▄▄▄▄▄▄[/yellow]       │[/bold red]
[bold red]    │     [yellow]█[/yellow][white]▀[/white] [cyan]◉[/cyan] [white]▀[/white][yellow]█[/yellow]      │[/bold red]
[bold red]    │     [yellow]█[/yellow] [red]◡◡◡[/red] [yellow]█[/yellow]      │[/bold red]
[bold red]    │      [yellow]███████[/yellow]       │[/bold red]
[bold red]    │     [green]╔═══════╗[/green]      │[/bold red]
[bold red]    │     [green]║ JOKER ║[/green]      │[/bold red]
[bold red]    │     [green]╚═══════╝[/green]      │[/bold red]
[bold red]    │                     │[/bold red]
[bold red]    │ ♠                 ♠ │[/bold red]
[bold red]    └─────────────────────┘[/bold red]
"""
        self.console.print(joker_card)
        self.console.print()
        self.console.print(
            "[italic cyan]\"Jack of all trades. Master of none, "
            "but oftentimes better than a master of one.\"[/italic cyan]"
        )
        self.console.print()

    def _change_model(self) -> None:
        """Change LLM model/provider interactively."""
        from rich.prompt import Confirm, Prompt

        self.console.print()
        self.console.print("[header]Change LLM Model[/header]")
        self.console.print()

        # Show current settings
        self.console.print(f"[info]Current: {self.config.llm.provider} / {self.config.llm.model}[/info]")
        self.console.print()

        # Provider selection
        self.console.print("[bold]Select Provider:[/bold]")
        self.console.print("  [cyan]1[/cyan] - Ollama (local)")
        self.console.print("  [cyan]2[/cyan] - LM Studio (local)")
        self.console.print("  [cyan]3[/cyan] - OpenAI (API key)")
        self.console.print("  [cyan]4[/cyan] - Custom API")
        self.console.print()

        choice = Prompt.ask(
            "[bold]Provider[/bold]",
            choices=["1", "2", "3", "4"],
            default="1",
        )

        provider = "ollama"
        base_url = "http://localhost:11434"
        api_key = None

        if choice == "1":
            provider = "ollama"
            base_url = Prompt.ask(
                "[bold]Ollama URL[/bold]",
                default="http://localhost:11434",
            )
        elif choice == "2":
            provider = "lmstudio"
            base_url = Prompt.ask(
                "[bold]LM Studio URL[/bold]",
                default="http://localhost:1234/v1",
            )
        elif choice == "3":
            provider = "openai"
            base_url = "https://api.openai.com/v1"
            api_key = Prompt.ask("[bold]OpenAI API Key[/bold]", password=True)
        elif choice == "4":
            provider = Prompt.ask("[bold]Provider name[/bold]", default="openai")
            base_url = Prompt.ask("[bold]API Base URL[/bold]")
            if Confirm.ask("[bold]Requires API key?[/bold]", default=False):
                api_key = Prompt.ask("[bold]API Key[/bold]", password=True)

        # Model name
        self.console.print()
        if provider == "ollama":
            self.console.print("[dim]Common models: llama3.1, codellama, mistral, mixtral[/dim]")
        elif provider == "openai":
            self.console.print("[dim]Common models: gpt-4, gpt-4-turbo, gpt-3.5-turbo[/dim]")

        model = Prompt.ask(
            "[bold]Model name[/bold]",
            default=self.config.llm.model,
        )

        # Update config
        self.config.llm.provider = provider
        self.config.llm.base_url = base_url
        self.config.llm.model = model
        if api_key:
            self.config.llm.api_key = api_key

        # Save config
        if Confirm.ask("[bold]Save to config file?[/bold]", default=True):
            self.config.save()
            self.console.print("[success]Configuration saved![/success]")

        # Reinitialize provider
        self.console.print()
        self.console.print("[info]Reconnecting to LLM...[/info]")

        if asyncio.run(self._init_provider()):
            self.console.print(f"[success]Now using: {provider} / {model}[/success]")
        else:
            self.console.print("[error]Failed to connect. Check settings.[/error]")

    def _enter_hacker_mode(self) -> None:
        """Enter autonomous hack mode."""
        from rich.prompt import Prompt

        self.console.print()
        self.console.print("[bold red]🔥 ENTERING HACK MODE 🔥[/bold red]")
        self.console.print()

        # Get target
        target = Prompt.ask(
            "[bold]Enter target[/bold] (IP, domain, or URL)",
        )

        if not target:
            self.console.print("[error]No target specified.[/error]")
            return

        # Get additional scope
        self.console.print()
        self.console.print("[dim]Add additional targets to scope (press Enter when done):[/dim]")

        scope = [target]
        while True:
            additional = Prompt.ask(
                "[bold]Additional scope[/bold]",
                default="",
            )
            if not additional:
                break
            scope.append(additional)

        # Save current session before entering hack mode
        self._save_session()

        # Close current provider
        if self.provider:
            asyncio.run(self.provider.close())

        # Run hack mode
        from kage.core.hackmode import run_hack_mode

        self.console.clear()
        asyncio.run(run_hack_mode(
            console=self.console,
            config=self.config,
            target=target,
            scope=scope,
            skip_warning=False,
        ))

    def _run_pending_commands(self) -> None:
        """Execute pending commands with approval workflow."""
        if not self._pending_commands:
            self.console.print("[muted]No pending commands.[/muted]")
            return

        from rich.prompt import Confirm

        from kage.security import ApprovalDecision, ApprovalWorkflow

        # Create approval workflow
        workflow = ApprovalWorkflow(
            scope=self.session.scope,
            safe_mode_enabled=self.session.safe_mode,
            require_approval=self.config.security.require_approval,
            scope_enforcement=self.config.security.scope_enforcement,
        )

        for cmd in self._pending_commands[:]:
            self.console.print()
            self.console.print(f"[command]$ {cmd.command}[/command]")
            if cmd.description:
                self.console.print(f"[muted]{cmd.description}[/muted]")

            # Run through approval workflow
            result = asyncio.run(workflow.evaluate(cmd))

            # Handle blocked commands
            if result.decision == ApprovalDecision.BLOCKED:
                self.console.print()
                self.console.print(
                    Panel(
                        f"[danger]{result.reason}[/danger]",
                        title="[unsafe]🛡 BLOCKED BY SAFE MODE[/unsafe]",
                        border_style="danger",
                    )
                )
                cmd.status = CommandStatus.REJECTED
                self.session.commands.append(cmd)
                self._pending_commands.remove(cmd)
                continue

            # Show warnings
            if result.warnings:
                self.console.print()
                for warning in result.warnings:
                    self.console.print(f"[warning]{warning}[/warning]")
                self.console.print()

            # Get user approval
            if result.decision == ApprovalDecision.NEEDS_CONFIRMATION:
                if not Confirm.ask("[warning]Execute anyway?[/warning]", default=False):
                    cmd.status = CommandStatus.REJECTED
                    self.session.commands.append(cmd)
                    self._pending_commands.remove(cmd)
                    self.console.print("[muted]Skipped[/muted]")
                    continue

            # Execute command
            cmd.status = CommandStatus.APPROVED
            asyncio.run(self._execute_command(cmd))
            self._pending_commands.remove(cmd)

    async def _execute_command(self, cmd: Command) -> None:
        """Execute a single command using the executor."""
        from kage.executor import LocalExecutor

        cmd.status = CommandStatus.RUNNING
        cmd.started_at = datetime.utcnow()

        self.console.print("[status.running]Running...[/status.running]")

        executor = LocalExecutor()

        try:
            result = await executor.execute(cmd.command, timeout=cmd.timeout)

            cmd.exit_code = result.exit_code
            cmd.stdout = result.stdout
            cmd.stderr = result.stderr
            cmd.status = CommandStatus.COMPLETED if not result.timed_out else CommandStatus.TIMEOUT
            cmd.completed_at = datetime.utcnow()

            # Display output
            if result.stdout:
                output_text = result.stdout[:2000]
                if len(result.stdout) > 2000:
                    output_text += "..."
                self.console.print(
                    Panel(
                        output_text,
                        title="[panel.title]Output[/panel.title]",
                        border_style="panel.border",
                    )
                )

            if result.stderr:
                self.console.print(
                    Panel(
                        result.stderr[:1000],
                        title="[error]Errors[/error]",
                        border_style="danger",
                    )
                )

            if result.timed_out:
                self.console.print("[error]Command timed out[/error]")
            else:
                self.console.print(
                    f"[status.completed]Completed (exit: {result.exit_code})[/status.completed]"
                )

        except Exception as e:
            cmd.status = CommandStatus.FAILED
            cmd.stderr = str(e)
            cmd.completed_at = datetime.utcnow()
            self.console.print(f"[error]Failed: {e}[/error]")

        # Add to session history
        self.session.commands.append(cmd)

    async def _process_message(self, user_input: str) -> None:
        """Process a user message and generate response."""
        if not self.conversation:
            self.console.print("[error]AI not connected. Restart session.[/error]")
            return

        self.console.print()
        self.console.print("[assistant]KAGE:[/assistant] ", end="")

        try:
            response_text, commands = await self.conversation.send_message(
                user_input,
                on_chunk=lambda c: self.console.print(c, end="", highlight=False),
            )
            self.console.print()  # Newline after streaming

            # Store any suggested commands
            if commands:
                self._pending_commands.extend(commands)
                self.console.print()
                self.console.print(
                    f"[info]{len(commands)} command(s) suggested. "
                    f"Use /commands to view, /run to execute.[/info]"
                )

        except Exception as e:
            self.console.print()
            self.console.print(f"[error]Error: {e}[/error]")

    def run(self) -> None:
        """Run the interactive chat loop."""
        # Initialize provider
        if not asyncio.run(self._init_provider()):
            return

        self.console.print("[success]Connected to LLM.[/success]")
        self.console.print()

        while self.running:
            try:
                # Get user input
                self.console.print()
                user_input = self.console.input(
                    "[prompt]kage[/prompt][prompt.arrow]>[/prompt.arrow] "
                )

                if not user_input.strip():
                    continue

                # Handle slash commands
                if user_input.startswith("/"):
                    if not self._handle_slash_command(user_input):
                        break
                    continue

                # Process regular message
                asyncio.run(self._process_message(user_input))

            except KeyboardInterrupt:
                self.console.print()
                self.console.print("[muted]Use /exit to end session.[/muted]")
            except EOFError:
                break

        # Cleanup
        if self.provider:
            asyncio.run(self.provider.close())

        self.console.print()
        self.console.print("[info]Session ended.[/info]")
        self.console.print(f"[muted]Session ID: {self.session.id}[/muted]")


def chat_loop(
    console: Console,
    config: KageConfig,
    session_id: str | None = None,
    scope: str | None = None,
) -> None:
    """Start the interactive chat loop."""
    session = ChatSession(console, config, session_id, scope)
    session.run()
