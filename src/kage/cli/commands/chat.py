"""Interactive chat command for Kage."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from kage.ai.base import LLMConfig as AILLMConfig
from kage.ai.providers import create_provider
from kage.core.conversation import ConversationManager
from kage.core.models import Command, CommandStatus, Message, MessageRole, Session, Target

if TYPE_CHECKING:
    from kage.persistence.config import KageConfig


class ChatSession:
    """Manages an interactive chat session."""

    def __init__(
        self,
        console: Console,
        config: "KageConfig",
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

        # Initialize scope if provided
        if scope:
            self._parse_and_add_scope(scope)

        # Override safe mode from config
        self.session.safe_mode = config.security.safe_mode

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
[command]/scope[/command]       - Show current scope
[command]/safe[/command]        - Toggle safe mode
[command]/findings[/command]    - List discovered findings
[command]/history[/command]     - Show command history
[command]/status[/command]      - Show session status
[command]/commands[/command]    - Show pending commands
[command]/run[/command]         - Execute pending commands

[header]Tips[/header]

• Describe what you want to achieve, and I'll suggest commands
• All commands require your approval before execution
• Use safe mode to prevent dangerous operations
• Define your scope to prevent accidental out-of-scope testing
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

    def _run_pending_commands(self) -> None:
        """Execute pending commands with approval."""
        if not self._pending_commands:
            self.console.print("[muted]No pending commands.[/muted]")
            return

        from rich.prompt import Confirm

        for cmd in self._pending_commands[:]:
            self.console.print()
            self.console.print(f"[command]$ {cmd.command}[/command]")
            if cmd.description:
                self.console.print(f"[muted]{cmd.description}[/muted]")

            if self.config.security.require_approval:
                if not Confirm.ask("[warning]Execute?[/warning]", default=False):
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
        """Execute a single command."""
        import subprocess

        cmd.status = CommandStatus.RUNNING
        cmd.started_at = datetime.utcnow()

        self.console.print("[status.running]Running...[/status.running]")

        try:
            result = subprocess.run(
                cmd.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=cmd.timeout,
            )

            cmd.exit_code = result.returncode
            cmd.stdout = result.stdout
            cmd.stderr = result.stderr
            cmd.status = CommandStatus.COMPLETED
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

            self.console.print(
                f"[status.completed]Completed (exit: {result.returncode})[/status.completed]"
            )

        except subprocess.TimeoutExpired:
            cmd.status = CommandStatus.TIMEOUT
            cmd.completed_at = datetime.utcnow()
            self.console.print("[error]Command timed out[/error]")

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
    config: "KageConfig",
    session_id: str | None = None,
    scope: str | None = None,
) -> None:
    """Start the interactive chat loop."""
    session = ChatSession(console, config, session_id, scope)
    session.run()
