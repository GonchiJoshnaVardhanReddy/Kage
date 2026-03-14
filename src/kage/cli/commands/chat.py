"""Interactive chat command for Kage."""

from __future__ import annotations

import asyncio
import os
import platform
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel

from kage.ai.base import LLMConfig, LLMMessage
from kage.ai.providers import create_provider
from kage.core.conversation import ConversationManager
from kage.core.intent import SECURITY_TOOLS, Intent, classify_intent
from kage.core.models import Command, CommandStatus, ExecutionEnvironment, Session, Target
from kage.core.planner import ExecutionPlan
from kage.core.router import CommandRouter, ExecutorType, RouteResult
from kage.mcp import KaliToolsAdvisor, MCPManager
from kage.security.output_parser import parse_tool_output
from kage.security.tool_checker import check_tool_installed, get_install_suggestion
from kage.utils import utcnow

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

        # Approval preferences (per-session memory)
        self._approved_all: bool = False
        self._approved_tools: set[str] = set()
        self._auto_approve_file_create: bool = False
        self.workspace_root: Path = Path.cwd().resolve()

        # Command router
        self._router = CommandRouter(
            kali_available=config.kali.enabled and bool(config.kali.servers),
        )

        # Kali executor (lazy init)
        self._kali_executor = None
        self._mcp_manager: MCPManager | None = None
        self._kali_tools_advisor: KaliToolsAdvisor | None = None

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
            self.console.print(
                f"[muted]Messages: {len(self.session.messages)}, Commands: {len(self.session.commands)}[/muted]"
            )
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

            # Close the client after connection check so it gets recreated
            # fresh on the next asyncio.run() call (each asyncio.run creates
            # a new event loop, stale clients from prior loops cause empty responses)
            await self.provider.close()

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

    def _is_linux(self) -> bool:
        """Return True when running on Linux."""
        return os.name != "nt" and platform.system().lower() == "linux"

    def _ensure_linux_kali_mcp_servers(self) -> None:
        """Ensure Linux has built-in Kali MCP server entries."""
        if not self._is_linux():
            return

        from kage.persistence.config import MCPServerConfig

        existing = {server.name for server in self.config.mcp.servers}

        if "kali_tools_docs" not in existing:
            self.config.mcp.servers.append(
                MCPServerConfig(
                    name="kali_tools_docs",
                    transport="stdio",
                    command="kali-tools-mcp",
                    auto_start=True,
                )
            )

        if "kali_execution" not in existing:
            self.config.mcp.servers.append(
                MCPServerConfig(
                    name="kali_execution",
                    transport="sse",
                    url="http://127.0.0.1:5000",
                    auto_start=True,
                )
            )

    async def _init_mcp(self) -> None:
        """Initialize MCP manager and Kali tools advisor."""
        if not self.config.mcp.enabled:
            return

        self._ensure_linux_kali_mcp_servers()
        self._mcp_manager = MCPManager(self.config.mcp)
        try:
            await self._mcp_manager.start()
            self._kali_tools_advisor = KaliToolsAdvisor(self._mcp_manager)
        except Exception as e:
            self.console.print(f"[warning]MCP initialization failed: {e}[/warning]")
            self._mcp_manager = None
            self._kali_tools_advisor = None

    def _is_within_workspace(self, path: Path) -> bool:
        """Check whether a path is inside the current workspace root."""
        try:
            path.relative_to(self.workspace_root)
            return True
        except ValueError:
            return False

    def _resolve_workspace_path(self, path_str: str) -> Path | None:
        """Resolve a user path and enforce workspace-only access."""
        raw = Path(path_str).expanduser()
        resolved = (raw if raw.is_absolute() else self.workspace_root / raw).resolve()
        if self._is_within_workspace(resolved):
            return resolved
        self.console.print(
            f"[error]Access outside workspace is blocked: {resolved}[/error]\n"
            f"[muted]Workspace: {self.workspace_root}[/muted]"
        )
        return None

    def _log_action(self, action: str, target: str) -> None:
        """Emit a concise step log line."""
        self.console.print(f"[info]● {action} {target}[/info]")

    def _summarize_command_result(self, cmd: Command) -> str:
        """Create a concise, user-facing command execution summary."""
        if cmd.status == CommandStatus.TIMEOUT:
            return "Command timed out before completion."
        if cmd.status == CommandStatus.FAILED:
            return f"Command failed. {cmd.stderr[:140] if cmd.stderr else 'Check error output for details.'}"
        if cmd.exit_code not in (None, 0):
            return f"Command exited with code {cmd.exit_code}."

        stdout_lines = len((cmd.stdout or "").splitlines())
        stderr_lines = len((cmd.stderr or "").splitlines())
        if stdout_lines == 0 and stderr_lines == 0:
            return "Command completed successfully with no output."
        return (
            f"Command completed successfully (exit {cmd.exit_code}). "
            f"Output: {stdout_lines} stdout line(s), {stderr_lines} stderr line(s)."
        )

    def _remember_security_target(self, target: str) -> None:
        """Store discovered targets in session memory."""
        mem = self.session.metadata.setdefault("security_memory", {})
        targets = mem.setdefault("targets", [])
        if target not in targets:
            targets.append(target)

    def _remember_security_result(self, command: Command, tool_name: str | None = None) -> None:
        """Store security command output snippets in session memory."""
        mem = self.session.metadata.setdefault("security_memory", {})
        recon = mem.setdefault("recon_results", [])
        recon.append(
            {
                "command": command.command,
                "status": command.status.value,
                "exit_code": command.exit_code,
                "stdout_preview": (command.stdout or "")[:500],
                "stderr_preview": (command.stderr or "")[:300],
            }
        )
        # Keep memory bounded.
        if len(recon) > 20:
            del recon[:-20]

        if tool_name:
            parsed_store = mem.setdefault("parsed_outputs", [])
            parsed_source = command.stdout or command.stderr or ""
            parsed_result = parse_tool_output(tool_name, parsed_source)
            if parsed_result.get("supported"):
                parsed_store.append(parsed_result)
                if len(parsed_store) > 20:
                    del parsed_store[:-20]

    def _ensure_tool_installed(self, tool_name: str) -> bool:
        """Ensure a command-line tool is installed before execution."""
        from rich.prompt import Confirm

        check = check_tool_installed(tool_name)
        if check["installed"]:
            return True

        suggestion = get_install_suggestion(tool_name)
        self.console.print()
        self.console.print(f"[warning]Tool '{tool_name}' is not installed.[/warning]")
        self.console.print(f"[muted]Suggested installation: {suggestion}[/muted]")

        # Keep behavior explicit and safe: ask before auto-install.
        if not self._is_linux():
            self.console.print("[muted]Auto-install is only supported on Linux.[/muted]")
            return False

        if not Confirm.ask("[warning]Install tool now?[/warning]", default=False):
            return False

        from kage.executor import LocalExecutor

        install_cmd = f"sudo apt install -y {tool_name}"
        self.console.print(f"[info]Installing via: {install_cmd}[/info]")
        result = asyncio.run(LocalExecutor().execute(install_cmd, timeout=900))
        if result.stdout:
            self.console.print(result.stdout[:1200], highlight=False)
        if result.stderr:
            self.console.print(f"[warning]{result.stderr[:600]}[/warning]", highlight=False)

        post = check_tool_installed(tool_name)
        if not post["installed"]:
            self.console.print(f"[error]Installation failed or '{tool_name}' still unavailable.[/error]")
            return False

        self.console.print(f"[success]Tool '{tool_name}' is installed at {post['path']}[/success]")
        return True

    async def _build_security_mcp_context(self, user_input: str) -> str | None:
        """Use Kali docs MCP to gather tool guidance for security requests."""
        if not self._is_linux():
            return None
        if not self._kali_tools_advisor or not self._kali_tools_advisor.is_available():
            return None

        workflow = await self._kali_tools_advisor.recommend_tools(user_input)
        if not workflow.has_recommendations:
            return None

        lines = [
            "Kali docs lookup workflow:",
            f"1) search_kali_tools(query={workflow.query!r})",
        ]

        context_parts = [
            "Use the following Kali MCP documentation context when proposing commands.",
        ]

        for idx, rec in enumerate(workflow.recommendations, start=1):
            lines.append(f"{idx + 1}) tool: {rec.tool_name} — {rec.rationale}")
            lines.append(f"   get_tool_usage({rec.tool_name!r}) used for syntax.")
            if rec.suggested_command:
                lines.append(f"   suggested command: {rec.suggested_command}")
            context_parts.append(f"Tool: {rec.tool_name}")
            if rec.details:
                context_parts.append(f"Details: {rec.details[:600]}")
            if rec.usage:
                context_parts.append(f"Usage: {rec.usage[:800]}")

        self.console.print()
        self.console.print("[info]Kali Tools MCP workflow[/info]")
        for line in lines:
            self.console.print(f"[muted]{line}[/muted]")

        mem = self.session.metadata.setdefault("security_memory", {})
        mem["last_kali_tools"] = [rec.tool_name for rec in workflow.recommendations]

        return "\n".join(context_parts)

    # Available slash commands for autocomplete
    COMMANDS = {
        "help": "Show this help message",
        "exit": "End the session",
        "clear": "Clear the screen",
        "model": "Change LLM model/provider",
        "mcp": "Manage MCP servers (Docker)",
        "hacker": "Enter autonomous hack mode",
        "hack": "Enter autonomous hack mode",
        "scope": "Show current scope",
        "safe": "Toggle safe mode",
        "findings": "List discovered findings",
        "history": "Show command history",
        "status": "Show session status",
        "commands": "Show pending commands",
        "run": "Execute pending commands",
        "save": "Save session (use: /save or /save <name>)",
        "load": "Load a saved session (use: /load <name>)",
        "saves": "List all saved sessions",
        "export": "Export session to file",
        "import": "Import a session from file",
    }

    def _setup_completer(self) -> None:
        """Set up tab completion for slash commands."""
        try:
            import readline

            commands = ["/" + cmd for cmd in self.COMMANDS]

            def completer(text: str, state: int) -> str | None:
                options = [c for c in commands if c.startswith(text)]
                return options[state] if state < len(options) else None

            readline.set_completer(completer)
            # macOS uses libedit which needs different binding
            if "libedit" in (readline.__doc__ or ""):
                readline.parse_and_bind("bind ^I rl_complete")
            else:
                readline.parse_and_bind("tab: complete")
        except ImportError:
            pass  # readline not available on Windows

    def _suggest_commands(self, partial: str) -> list[str]:
        """Get command suggestions based on partial input."""
        partial = partial.lower()
        matches = []
        for cmd, desc in self.COMMANDS.items():
            if cmd.startswith(partial):
                matches.append((cmd, desc))
        return matches

    def _show_suggestions(self, partial: str) -> None:
        """Display command suggestions."""
        matches = self._suggest_commands(partial)
        if not matches:
            self.console.print(f"[error]No commands matching '/{partial}'[/error]")
            self.console.print("[muted]Type /help for available commands.[/muted]")
            return

        self.console.print()
        self.console.print("[header]Did you mean:[/header]")
        for cmd, desc in matches:
            self.console.print(f"  [command]/{cmd}[/command] - [muted]{desc}[/muted]")
        self.console.print()

    def _handle_slash_command(self, command: str) -> bool:
        """Handle slash commands. Returns True if should continue loop."""
        # Easter egg — check before parsing (supports multi-word slash input)
        if self._is_who_command(command):
            self._show_easter_egg()
            return True

        parts = command[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        # Check for exact command match first
        exact_commands = [
            "exit",
            "quit",
            "q",
            "help",
            "clear",
            "scope",
            "safe",
            "safemode",
            "findings",
            "history",
            "status",
            "run",
            "commands",
            "save",
            "load",
            "saves",
            "export",
            "import",
            "model",
            "mcp",
            "hacker",
            "hack",
        ]

        if cmd not in exact_commands:
            # Show suggestions for partial matches
            self._show_suggestions(cmd)
            return True

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
            self._save_session(args if args else None)

        elif cmd == "load":
            if args:
                self._load_session(args)
            else:
                self._list_saves()
                self.console.print()
                self.console.print("[muted]Usage: /load <name>[/muted]")

        elif cmd == "saves":
            self._list_saves()

        elif cmd == "export":
            self._export_session(args)

        elif cmd == "import":
            if args:
                self._import_session(args)
            else:
                self.console.print("[muted]Usage: /import <path>[/muted]")

        elif cmd == "model":
            self._change_model()

        elif cmd == "mcp":
            self._manage_mcp()

        elif cmd in ("hacker", "hack"):
            self._enter_hacker_mode()
            return False  # Exit chat loop to enter hack mode

        return True

    @staticmethod
    def _is_who_command(command: str) -> bool:
        """Check if a slash command is asking about Kage's identity."""
        normalized = re.sub(r"[^a-z]", "", command.lower())
        return normalized in (
            "whoareyou",
            "whoru",
            "whoami",
            "aboutkage",
            "about",
            "identity",
            "whoisthis",
            "whatareyou",
            "whatsthis",
        )

    # Patterns that indicate the user is asking about Kage's identity
    _IDENTITY_PATTERNS = [
        r"\bwho\s+are\s+you\b",
        r"\bwhat\s+are\s+you\b",
        r"\bwhat\s+is\s+kage\b",
        r"\btell\s+me\s+about\s+(yourself|kage)\b",
        r"\bwhat\s+can\s+you\s+do\b",
        r"\bwhat\s+do\s+you\s+do\b",
        r"\bintroduce\s+yourself\b",
        r"\bdescribe\s+yourself\b",
        r"\byour\s+name\b",
        r"\bwhat\s+is\s+your\s+name\b",
        r"\bwho\s+r\s+u\b",
        r"\bwho\s+is\s+this\b",
    ]

    def _is_identity_question(self, text: str) -> bool:
        """Check if the user is asking about Kage's identity."""
        lower = text.strip().lower()
        return any(re.search(p, lower) for p in self._IDENTITY_PATTERNS)

    def _show_identity(self) -> None:
        """Display Kage's identity information."""
        self.console.print()
        self.console.print("[assistant]KAGE:[/assistant]")
        self.console.print()

        identity = Panel(
            "[bold cyan]I am Kage[/bold cyan] — your AI-powered penetration testing assistant.\n\n"
            "I help security professionals with:\n"
            "  [green]•[/green] Authorized security assessments & red team ops\n"
            "  [green]•[/green] Bug bounty hunting & vulnerability analysis\n"
            "  [green]•[/green] CTF challenges & exploitation guidance\n"
            "  [green]•[/green] Reconnaissance, enumeration & post-exploitation\n"
            "  [green]•[/green] Security report generation & findings management\n\n"
            f"[muted]Powered by {self.config.llm.provider} / {self.config.llm.model}[/muted]\n"
            "[muted]Type /help for commands • /whoareyou for a surprise[/muted]",
            title="[bold red]⚡ K A G E ⚡[/bold red]",
            border_style="red",
            padding=(1, 2),
        )
        self.console.print(identity)
        self.console.print()

    def _show_help(self) -> None:
        """Display help information."""
        help_text = """
[header]Available Commands[/header]

[command]/help[/command]          - Show this help message
[command]/exit[/command]          - End the session
[command]/clear[/command]         - Clear the screen
[command]/model[/command]         - Change LLM model/provider
[command]/mcp[/command]           - Manage MCP servers (Docker)
[command]/hacker[/command]        - Enter autonomous hack mode

[header]Session Management[/header]

[command]/save[/command]          - Save session with auto-generated ID
[command]/save <name>[/command]   - Save session with custom name
[command]/load <name>[/command]   - Load a saved session by name
[command]/saves[/command]         - List all saved sessions
[command]/export [path][/command] - Export session to file
[command]/status[/command]        - Show session status

[header]Security & Scope[/header]

[command]/scope[/command]         - Show current scope
[command]/safe[/command]          - Toggle safe mode
[command]/findings[/command]      - List discovered findings

[header]Commands & History[/header]

[command]/commands[/command]      - Show pending commands
[command]/run[/command]           - Execute pending commands
[command]/history[/command]       - Show command history

[header]Natural Language File Tools[/header]

Use plain language for file operations:
• "show server.py"
• "list files in src"
• "create app.py"
• "add logging to server.py"

[header]Tips[/header]

• Type partial commands to see suggestions (e.g., /h → /help, /history, /hack)
• Kage uses internal file tools automatically from natural language
• Use /save <name> to name your sessions for easy recall
• Use /load <name> to continue where you left off
"""
        self.console.print(help_text)

    def _extract_file_path_from_text(self, text: str) -> str | None:
        """Extract a likely file path from user text."""
        quoted = re.search(r"""["']([^"']+\.[\w]+)["']""", text)
        if quoted:
            return quoted.group(1).strip()

        path_like = re.search(
            r"(?<!\S)([.\w\\/\-]+?\.[a-zA-Z0-9]{1,8})(?!\S)",
            text,
        )
        if path_like:
            return path_like.group(1).strip()

        return None

    async def _ai_edit_file(self, path_str: str, request: str) -> bool:
        """Perform an AI-driven file edit with diff preview and approval."""
        import difflib

        from kage.cli.ui.prompts import prompt_file_approval

        file_path = self._resolve_workspace_path(path_str)
        if file_path is None:
            return True
        if not file_path.exists() or not file_path.is_file():
            self.console.print(f"[error]File not found: {file_path}[/error]")
            return True

        self._log_action("Reading file", str(file_path.relative_to(self.workspace_root)))
        original_content = file_path.read_text(encoding="utf-8", errors="replace")

        edit_prompt = (
            "You are applying a precise code edit.\n"
            "Given the user request and file content, return the complete updated file content only.\n"
            "Do not include explanations.\n"
            "Output format:\n"
            "```updated_file\n"
            "<full updated file content>\n"
            "```\n\n"
            f"User request:\n{request}\n\n"
            f"File path:\n{file_path.name}\n\n"
            "Current file content:\n"
            "```text\n"
            f"{original_content}\n"
            "```"
        )

        response = await self.provider.complete(
            messages=[
                LLMMessage(role="system", content="You are a precise code editor."),
                LLMMessage(role="user", content=edit_prompt),
            ],
            config=LLMConfig(
                model=self.config.llm.model,
                temperature=0.1,
                max_tokens=self.config.llm.max_tokens,
            ),
        )

        block_match = re.search(
            r"```updated_file\s*(.*?)```",
            response.content,
            re.DOTALL | re.IGNORECASE,
        )
        updated_content = block_match.group(1).strip("\n") if block_match else response.content.strip()

        if updated_content == original_content:
            self.console.print("[muted]No changes proposed.[/muted]")
            return True

        diff_lines = list(
            difflib.unified_diff(
                original_content.splitlines(),
                updated_content.splitlines(),
                fromfile=f"a/{file_path.name}",
                tofile=f"b/{file_path.name}",
                lineterm="",
            )
        )
        diff_preview = "\n".join(diff_lines) if diff_lines else "(No changes)"

        if not prompt_file_approval(self.console, "edit", str(file_path), diff_preview):
            self.console.print("[muted]Edit cancelled.[/muted]")
            return True

        self._log_action("Editing file", str(file_path.relative_to(self.workspace_root)))
        file_path.write_text(updated_content, encoding="utf-8")
        self.console.print(f"[success]Updated: {file_path}[/success]")
        return True

    async def _handle_natural_language_file_request(self, user_input: str) -> bool:
        """Handle plain-language file actions using internal tools."""
        lower = user_input.strip().lower()

        read_prefixes = ("show ", "read ", "open ", "view ")
        if lower.startswith(read_prefixes):
            path = self._extract_file_path_from_text(user_input) or user_input.split(maxsplit=1)[1]
            self._read_file(path)
            return True

        if lower.startswith(("list files", "show files", "list directory", "show directory")):
            if " in " in user_input:
                directory = user_input.split(" in ", maxsplit=1)[1].strip()
            else:
                directory = "."
            self._list_directory(directory)
            return True

        if lower.startswith(("create ", "make file ", "new file ")):
            path = self._extract_file_path_from_text(user_input)
            if path:
                self._create_file(path)
                return True

        edit_keywords = ("add ", "update ", "modify ", "change ", "refactor ", "fix ", "remove ")
        if lower.startswith(edit_keywords):
            path = self._extract_file_path_from_text(user_input)
            if path:
                return await self._ai_edit_file(path, user_input)

        return False

    def _show_scope(self) -> None:
        """Display current scope."""
        from kage.cli.ui.panels import create_scope_panel

        self.console.print(create_scope_panel(self.session.scope))

    def _check_and_prompt_scope(self, user_input: str) -> bool:
        """Check scope/authorization for security requests."""
        import ipaddress
        import re as _re

        from kage.cli.ui.prompts import (
            prompt_scope_authorization,
            prompt_scope_definition,
            prompt_scope_input,
        )

        # Try to extract a target from the input
        target = None
        # Match IPs
        ip_match = _re.search(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?:/\d{1,2})?)\b", user_input)
        if ip_match:
            target = ip_match.group(1)
        else:
            # Match domains (word.tld)
            domain_match = _re.search(r"\b([\w-]+\.[\w.-]+\.\w{2,}|[\w-]+\.\w{2,})\b", user_input)
            if domain_match:
                candidate = domain_match.group(1)
                # Exclude common non-targets
                if candidate not in ("example.com",) and "." in candidate:
                    target = candidate

        if not target:
            return True

        self._remember_security_target(target)

        choice = prompt_scope_definition(self.console, target)

        if choice == "add":
            # Determine target type
            target_type = "domain"
            try:
                ipaddress.ip_address(target)
                target_type = "ip"
            except ValueError:
                try:
                    ipaddress.ip_network(target, strict=False)
                    target_type = "cidr"
                except ValueError:
                    if target.startswith(("http://", "https://")):
                        target_type = "url"

            self.session.scope.targets.append(
                Target(value=target, target_type=target_type)
            )
            self.console.print(f"[success]Added {target} to scope.[/success]")
            return True

        elif choice == "define":
            scope_input = prompt_scope_input(self.console)
            if scope_input.strip():
                self._parse_and_add_scope(scope_input)
                self.console.print(
                    f"[success]Scope updated: "
                    f"{len(self.session.scope.targets)} target(s)[/success]"
                )
                return True

        else:
            approved = prompt_scope_authorization(self.console, target)
            if not approved:
                self.console.print("[muted]Security request cancelled: scope not authorized.[/muted]")
                return False
            self.console.print("[warning]Proceeding without explicit scope definition.[/warning]")
            return True

        return False

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

    def _save_session(self, name: str | None = None) -> None:
        """Save the current session with optional name."""
        from kage.persistence import SessionStorage

        if not self._session_storage:
            self._session_storage = SessionStorage()

        # If name provided, set it as session name/alias
        if name:
            self.session.name = name

        path = asyncio.run(self._session_storage.save(self.session))

        if name:
            self.console.print(f"[success]Session saved as: [bold]{name}[/bold][/success]")
        else:
            self.console.print(f"[success]Session saved: {self.session.id[:8]}[/success]")
        self.console.print(f"[muted]Path: {path}[/muted]")
        self.console.print()
        self.console.print(f"[muted]Resume with: kage session resume {self.session.id[:8]}[/muted]")
        if name:
            self.console.print(f"[muted]Or in chat: /load {name}[/muted]")

    def _load_session(self, name: str) -> None:
        """Load a session by name or ID."""
        from kage.persistence import SessionStorage

        if not self._session_storage:
            self._session_storage = SessionStorage()

        self.console.print(f"[info]Loading session: {name}...[/info]")

        # First try to find by name
        sessions = asyncio.run(self._session_storage.list_sessions(limit=100))

        found_session = None
        for s in sessions:
            # Check by name
            if s.get("name", "").lower() == name.lower():
                found_session = s
                break
            # Check by ID prefix
            if s["id"].startswith(name):
                found_session = s
                break

        if not found_session:
            self.console.print(f"[error]Session not found: {name}[/error]")
            self.console.print("[muted]Use /saves to list available sessions[/muted]")
            return

        # Load the session
        loaded = asyncio.run(self._session_storage.load(found_session["id"]))

        if loaded:
            self.session = loaded
            self.console.print(
                f"[success]✓ Loaded session: {loaded.name or loaded.id[:8]}[/success]"
            )
            self.console.print(
                f"[muted]Messages: {len(self.session.messages)}, Commands: {len(self.session.commands)}[/muted]"
            )

            # Reinitialize conversation with loaded session
            if self.conversation:
                self.conversation.session = self.session
        else:
            self.console.print("[error]Failed to load session[/error]")

    def _list_saves(self) -> None:
        """List all saved sessions."""
        from rich.table import Table

        from kage.persistence import SessionStorage

        if not self._session_storage:
            self._session_storage = SessionStorage()

        sessions = asyncio.run(self._session_storage.list_sessions(limit=20))

        if not sessions:
            self.console.print("[muted]No saved sessions found.[/muted]")
            self.console.print("[muted]Use /save <name> to save your current session.[/muted]")
            return

        self.console.print()
        table = Table(title="Saved Sessions", header_style="table.header")
        table.add_column("Name/ID", style="highlight")
        table.add_column("Updated", style="muted")
        table.add_column("Scope", style="info")
        table.add_column("Msgs", style="muted", justify="right")
        table.add_column("Cmds", style="muted", justify="right")

        for s in sessions:
            name_display = s.get("name") or s["id"][:8]
            table.add_row(
                name_display,
                s.get("updated_at", "")[:10],
                s.get("scope_summary", "-")[:25],
                str(s.get("message_count", 0)),
                str(s.get("command_count", 0)),
            )

        self.console.print(table)
        self.console.print()
        self.console.print("[muted]Load a session: /load <name or id>[/muted]")

    def _export_session(self, args: str) -> None:
        """Export the current session to a file."""
        from pathlib import Path

        from kage.persistence import SessionStorage

        if not self._session_storage:
            self._session_storage = SessionStorage()

        # Determine output path and format
        output_path = Path(args) if args else Path(f"session_{self.session.id[:8]}.md")

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

    def _import_session(self, path_str: str) -> None:
        """Import a session from a JSON file."""
        import json
        from pathlib import Path

        file_path = Path(path_str)
        if not file_path.exists():
            self.console.print(f"[error]File not found: {file_path}[/error]")
            return

        if file_path.suffix != ".json":
            self.console.print("[error]Only JSON session files can be imported.[/error]")
            return

        try:
            with open(file_path) as f:
                data = json.load(f)
            loaded = Session(**data)
            self.session = loaded
            if self.conversation:
                self.conversation.session = self.session
            self.console.print(
                f"[success]Imported session: {loaded.name or loaded.id[:8]}[/success]"
            )
            self.console.print(
                f"[muted]Messages: {len(self.session.messages)}, "
                f"Commands: {len(self.session.commands)}[/muted]"
            )
        except Exception as e:
            self.console.print(f"[error]Failed to import session: {e}[/error]")

    def _handle_at_command(self, command: str) -> None:
        """Handle @ file operation commands."""
        rest = command[1:].strip()
        if not rest:
            self.console.print("[header]@ File Operations:[/header]")
            self.console.print("  [command]@read <path>[/command]   - Read and display a file")
            self.console.print("  [command]@write <path> <text>[/command] - Write text to a file")
            self.console.print("  [command]@edit <path>[/command]   - Interactive file editor")
            self.console.print("  [command]@create <path>[/command] - Create a new file")
            self.console.print("  [command]@ls [path][/command]     - List directory contents")
            return

        parts = rest.split(maxsplit=1)
        action = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if action == "read":
            if args:
                self._read_file(args)
            else:
                self.console.print("[muted]Usage: @read <path>[/muted]")
        elif action == "write":
            if args:
                parts_w = args.split(maxsplit=1)
                if len(parts_w) == 2:
                    self._write_file(parts_w[0], parts_w[1])
                else:
                    self.console.print("[muted]Usage: @write <path> <content>[/muted]")
            else:
                self.console.print("[muted]Usage: @write <path> <content>[/muted]")
        elif action == "edit":
            if args:
                self._edit_file(args)
            else:
                self.console.print("[muted]Usage: @edit <path>[/muted]")
        elif action == "create":
            if args:
                self._create_file(args)
            else:
                self.console.print("[muted]Usage: @create <path>[/muted]")
        elif action == "ls":
            self._list_directory(args if args else ".")
        else:
            # If no known action, treat as a file path to read
            self._read_file(rest)

    def _read_file(self, path_str: str) -> None:
        """Read and display a file's contents."""
        file_path = self._resolve_workspace_path(path_str)
        if file_path is None:
            return
        if not file_path.exists():
            self.console.print(f"[error]File not found: {file_path}[/error]")
            return
        if not file_path.is_file():
            self.console.print(f"[error]Not a file: {file_path}[/error]")
            return

        try:
            self._log_action("Reading file", str(file_path.relative_to(self.workspace_root)))
            content = file_path.read_text(encoding="utf-8", errors="replace")
            from rich.syntax import Syntax

            ext_map = {
                ".py": "python",
                ".js": "javascript",
                ".ts": "typescript",
                ".sh": "bash",
                ".yaml": "yaml",
                ".yml": "yaml",
                ".json": "json",
                ".md": "markdown",
                ".html": "html",
                ".css": "css",
                ".xml": "xml",
                ".sql": "sql",
                ".rb": "ruby",
                ".go": "go",
                ".rs": "rust",
                ".c": "c",
                ".cpp": "cpp",
                ".h": "c",
                ".java": "java",
                ".toml": "toml",
                ".ini": "ini",
                ".cfg": "ini",
                ".txt": "text",
                ".log": "text",
                ".conf": "text",
            }
            lang = ext_map.get(file_path.suffix.lower(), "text")
            syntax = Syntax(
                content,
                lang,
                theme="monokai",
                line_numbers=True,
                word_wrap=True,
            )
            self.console.print(Panel(syntax, title=f"📄 {file_path.name}", border_style="cyan"))
            self.console.print(
                f"[muted]{len(content)} bytes, {content.count(chr(10)) + 1} lines[/muted]"
            )
        except Exception as e:
            self.console.print(f"[error]Failed to read file: {e}[/error]")

    def _write_file(self, path_str: str, content: str) -> None:
        """Write content to a file with approval."""
        from kage.cli.ui.prompts import (
            FileCreateApprovalChoice,
            prompt_file_approval,
            prompt_file_create_approval,
        )

        file_path = self._resolve_workspace_path(path_str)
        if file_path is None:
            return
        action = "overwrite" if file_path.exists() else "create"

        if action == "create":
            if not self._auto_approve_file_create:
                create_choice = prompt_file_create_approval(self.console, str(file_path), content)
                if create_choice == FileCreateApprovalChoice.CANCEL:
                    self.console.print("[muted]Write cancelled.[/muted]")
                    return
                if create_choice == FileCreateApprovalChoice.AUTO_APPROVE_CREATES:
                    self._auto_approve_file_create = True
                    self.console.print(
                        "[info]Auto-approving file creation for this session.[/info]"
                    )
        elif not prompt_file_approval(self.console, action, str(file_path), content):
            self.console.print("[muted]Write cancelled.[/muted]")
            return

        try:
            verb = "Creating file" if action == "create" else "Writing file"
            self._log_action(verb, str(file_path.relative_to(self.workspace_root)))
            file_path.parent.mkdir(parents=True, exist_ok=True)
            content = content.replace("\\n", "\n").replace("\\t", "\t")
            file_path.write_text(content, encoding="utf-8")
            self.console.print(f"[success]Written to: {file_path}[/success]")
            self.console.print(f"[muted]{len(content)} bytes written[/muted]")
        except Exception as e:
            self.console.print(f"[error]Failed to write file: {e}[/error]")

    def _edit_file(self, path_str: str) -> None:
        """Open a file for interactive editing (append/replace line)."""
        from kage.cli.ui.prompts import prompt_file_approval

        file_path = self._resolve_workspace_path(path_str)
        if file_path is None:
            return
        if not file_path.exists():
            self.console.print(f"[error]File not found: {file_path}[/error]")
            return

        try:
            original_content = file_path.read_text(encoding="utf-8", errors="replace")
            lines = original_content.splitlines()
            self._log_action("Editing file", str(file_path.relative_to(self.workspace_root)))

            from rich.syntax import Syntax

            syntax = Syntax(original_content, "text", line_numbers=True, theme="monokai")
            self.console.print(
                Panel(syntax, title=f"✏️ Editing: {file_path.name}", border_style="yellow")
            )

            self.console.print()
            self.console.print("[header]Edit Options:[/header]")
            self.console.print("  [command]a[/command]  - Append a line at the end")
            self.console.print("  [command]r <n>[/command] - Replace line number n")
            self.console.print("  [command]d <n>[/command] - Delete line number n")
            self.console.print("  [command]i <n>[/command] - Insert before line number n")
            self.console.print("  [command]q[/command]  - Save and quit")
            self.console.print("  [command]x[/command]  - Quit without saving")
            self.console.print()

            modified = False
            while True:
                action = self.console.input("[yellow]edit>[/yellow] ").strip()
                if not action:
                    continue

                if action.lower() == "q":
                    if modified:
                        import difflib

                        updated_content = "\n".join(lines) + "\n"
                        diff_lines = list(
                            difflib.unified_diff(
                                original_content.splitlines(),
                                updated_content.splitlines(),
                                fromfile=f"a/{file_path.name}",
                                tofile=f"b/{file_path.name}",
                                lineterm="",
                            )
                        )
                        diff_preview = "\n".join(diff_lines) if diff_lines else "(No changes)"

                        if not prompt_file_approval(
                            self.console,
                            "edit",
                            str(file_path),
                            diff_preview,
                        ):
                            self.console.print("[muted]Edit cancelled. Changes not saved.[/muted]")
                            break

                        file_path.write_text(updated_content, encoding="utf-8")
                        self.console.print(f"[success]Saved: {file_path}[/success]")
                    break
                elif action.lower() == "x":
                    self.console.print("[muted]Discarded changes.[/muted]")
                    break
                elif action.lower() == "a":
                    new_line = self.console.input("[cyan]new line>[/cyan] ")
                    lines.append(new_line)
                    modified = True
                    self.console.print(f"[muted]Added line {len(lines)}[/muted]")
                elif action.lower().startswith("r "):
                    try:
                        n = int(action.split()[1]) - 1
                        if 0 <= n < len(lines):
                            self.console.print(f"[muted]Current: {lines[n]}[/muted]")
                            new_text = self.console.input("[cyan]new text>[/cyan] ")
                            lines[n] = new_text
                            modified = True
                            self.console.print(f"[muted]Replaced line {n + 1}[/muted]")
                        else:
                            self.console.print(
                                f"[error]Line {n + 1} out of range (1-{len(lines)})[/error]"
                            )
                    except (ValueError, IndexError):
                        self.console.print("[error]Usage: r <line_number>[/error]")
                elif action.lower().startswith("d "):
                    try:
                        n = int(action.split()[1]) - 1
                        if 0 <= n < len(lines):
                            removed = lines.pop(n)
                            modified = True
                            self.console.print(f"[muted]Deleted: {removed}[/muted]")
                        else:
                            self.console.print(f"[error]Line {n + 1} out of range[/error]")
                    except (ValueError, IndexError):
                        self.console.print("[error]Usage: d <line_number>[/error]")
                elif action.lower().startswith("i "):
                    try:
                        n = int(action.split()[1]) - 1
                        if 0 <= n <= len(lines):
                            new_line = self.console.input("[cyan]new line>[/cyan] ")
                            lines.insert(n, new_line)
                            modified = True
                            self.console.print(f"[muted]Inserted at line {n + 1}[/muted]")
                        else:
                            self.console.print("[error]Position out of range[/error]")
                    except (ValueError, IndexError):
                        self.console.print("[error]Usage: i <line_number>[/error]")
                else:
                    self.console.print("[muted]Unknown action. Use a/r/d/i/q/x[/muted]")

        except Exception as e:
            self.console.print(f"[error]Failed to edit file: {e}[/error]")

    def _create_file(self, path_str: str) -> None:
        """Create a new file with interactive content input."""
        from kage.cli.ui.prompts import (
            FileCreateApprovalChoice,
            prompt_file_create_approval,
        )

        file_path = self._resolve_workspace_path(path_str)
        if file_path is None:
            return
        if file_path.exists():
            self.console.print(f"[error]File already exists: {file_path}[/error]")
            self.console.print("[muted]Use /edit to modify or /write to overwrite.[/muted]")
            return

        self._log_action("Creating file", str(file_path.relative_to(self.workspace_root)))
        self.console.print(f"[info]Creating: {file_path}[/info]")
        self.console.print(
            "[muted]Enter content (type ':done' on a new line to finish, ':cancel' to abort):[/muted]"
        )

        lines = []
        while True:
            line = self.console.input("[green]│[/green] ")
            if line.strip() == ":done":
                break
            if line.strip() == ":cancel":
                self.console.print("[muted]File creation cancelled.[/muted]")
                return
            lines.append(line)

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            content = "\n".join(lines) + "\n"

            if not self._auto_approve_file_create:
                create_choice = prompt_file_create_approval(self.console, str(file_path), content)
                if create_choice == FileCreateApprovalChoice.CANCEL:
                    self.console.print("[muted]File creation cancelled.[/muted]")
                    return
                if create_choice == FileCreateApprovalChoice.AUTO_APPROVE_CREATES:
                    self._auto_approve_file_create = True
                    self.console.print(
                        "[info]Auto-approving file creation for this session.[/info]"
                    )

            file_path.write_text(content, encoding="utf-8")
            self.console.print(f"[success]Created: {file_path}[/success]")
            self.console.print(f"[muted]{len(lines)} lines, {len(content)} bytes[/muted]")
        except Exception as e:
            self.console.print(f"[error]Failed to create file: {e}[/error]")

    def _list_directory(self, path_str: str) -> None:
        """List contents of a directory."""
        from rich.table import Table

        dir_path = self._resolve_workspace_path(path_str)
        if dir_path is None:
            return
        if not dir_path.exists():
            self.console.print(f"[error]Path not found: {dir_path}[/error]")
            return
        if not dir_path.is_dir():
            self.console.print(f"[error]Not a directory: {dir_path}[/error]")
            return

        try:
            self._log_action("Listing files in", str(dir_path.relative_to(self.workspace_root)))
            entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))

            table = Table(title=f"📁 {dir_path}", header_style="table.header")
            table.add_column("Type", style="muted", width=6)
            table.add_column("Name", style="info")
            table.add_column("Size", style="muted", justify="right")

            for entry in entries:
                if entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    table.add_row("📁 dir", f"[bold]{entry.name}/[/bold]", "-")
                else:
                    size = entry.stat().st_size
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    else:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                    table.add_row("📄 file", entry.name, size_str)

            self.console.print(table)
            self.console.print(f"[muted]{len(entries)} items[/muted]")
        except PermissionError:
            self.console.print(f"[error]Permission denied: {dir_path}[/error]")
        except Exception as e:
            self.console.print(f"[error]Failed to list directory: {e}[/error]")

    def _show_easter_egg(self) -> None:
        """Display the hidden easter egg with animated joker card."""
        joker_lines = [
            "",
            "  🃏",
            "",
            "[bold magenta]       ██╗ ██████╗ ██╗  ██╗███████╗██████╗ [/bold magenta]",
            "[bold magenta]       ██║██╔═══██╗██║ ██╔╝██╔════╝██╔══██╗[/bold magenta]",
            "[bold yellow]       ██║██║   ██║█████╔╝ █████╗  ██████╔╝[/bold yellow]",
            "[bold yellow]  ██   ██║██║   ██║██╔═██╗ ██╔══╝  ██╔══██╗[/bold yellow]",
            "[bold red]  ╚█████╔╝╚██████╔╝██║  ██╗███████╗██║  ██║[/bold red]",
            "[bold red]   ╚════╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝[/bold red]",
            "",
            "  🃏",
            "",
        ]

        self.console.print()
        for line in joker_lines:
            self.console.print(line, highlight=False)
            time.sleep(0.07)

        time.sleep(0.3)

        # Typewriter effect for the quote
        quote = (
            '"Jack of all trades. Master of none, '
            'But oftentimes better than a master of one."'
        )
        self.console.print("  ", end="")
        for char in quote:
            self.console.print(f"[italic cyan]{char}[/italic cyan]", end="")
            time.sleep(0.03)
        self.console.print()
        self.console.print()

    def _change_model(self) -> None:
        """Change LLM model/provider interactively with auto-detection."""
        import asyncio

        from rich.prompt import Confirm, Prompt

        from kage.ai.providers.ollama import OllamaProvider
        from kage.ai.providers.openai import LMStudioProvider

        self.console.print()
        self.console.print("[header]Change LLM Model[/header]")
        self.console.print()

        # Show current settings
        self.console.print(
            f"[info]Current: {self.config.llm.provider} / {self.config.llm.model}[/info]"
        )
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
            # Test connection and list models
            self.console.print()
            with self.console.status("[info]Connecting to Ollama...[/info]"):

                async def get_ollama_models():
                    p = OllamaProvider(base_url=base_url)
                    try:
                        connected = await p.check_connection()
                        models = await p.list_models() if connected else []
                        return connected, models
                    finally:
                        await p.close()

                connected, models = asyncio.run(get_ollama_models())

            if connected and models:
                self.console.print("[success]✓ Connected[/success]")
                self.console.print()
                self.console.print("[header]Available Models:[/header]")
                for i, m in enumerate(models[:15], 1):
                    self.console.print(f"  [cyan]{i}[/cyan] - {m}")
                self.console.print()
                model_choice = Prompt.ask(
                    "[bold]Select model (number or name)[/bold]",
                    default="1",
                )
                if model_choice.isdigit() and 1 <= int(model_choice) <= len(models):
                    model = models[int(model_choice) - 1]
                else:
                    model = model_choice
            elif connected:
                self.console.print("[warning]Connected but no models found[/warning]")
                self.console.print("[muted]Pull a model: ollama pull llama3.1[/muted]")
                model = Prompt.ask("[bold]Model name[/bold]", default="llama3.1")
            else:
                self.console.print("[error]Could not connect to Ollama[/error]")
                return

        elif choice == "2":
            provider = "lmstudio"
            base_url = Prompt.ask(
                "[bold]LM Studio URL[/bold]",
                default="http://localhost:1234/v1",
            )
            # Test connection
            self.console.print()
            with self.console.status("[info]Connecting to LM Studio...[/info]"):

                async def get_lmstudio_models():
                    p = LMStudioProvider(base_url=base_url)
                    try:
                        connected = await p.check_connection()
                        models = await p.list_models() if connected else []
                        return connected, models
                    finally:
                        await p.close()

                connected, models = asyncio.run(get_lmstudio_models())

            if connected:
                self.console.print("[success]✓ Connected[/success]")
                if models:
                    self.console.print()
                    self.console.print("[header]Available Models:[/header]")
                    for i, m in enumerate(models[:10], 1):
                        self.console.print(f"  [cyan]{i}[/cyan] - {m}")
                    self.console.print()
                    model_choice = Prompt.ask(
                        "[bold]Select model (number or name)[/bold]",
                        default="1",
                    )
                    if model_choice.isdigit() and 1 <= int(model_choice) <= len(models):
                        model = models[int(model_choice) - 1]
                    else:
                        model = model_choice
                else:
                    model = Prompt.ask("[bold]Model name[/bold]", default="local-model")
            else:
                self.console.print("[error]Could not connect to LM Studio[/error]")
                return

        elif choice == "3":
            provider = "openai"
            base_url = "https://api.openai.com/v1"
            api_key = Prompt.ask("[bold]OpenAI API Key[/bold]", password=True)
            self.console.print()
            self.console.print("[dim]Models: gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo[/dim]")
            model = Prompt.ask("[bold]Model name[/bold]", default="gpt-4o-mini")

        elif choice == "4":
            provider = Prompt.ask("[bold]Provider name[/bold]", default="openai")
            base_url = Prompt.ask("[bold]API Base URL[/bold]")
            if Confirm.ask("[bold]Requires API key?[/bold]", default=False):
                api_key = Prompt.ask("[bold]API Key[/bold]", password=True)
            model = Prompt.ask("[bold]Model name[/bold]", default=self.config.llm.model)

        # Update config
        self.config.llm.provider = provider
        self.config.llm.base_url = base_url
        self.config.llm.model = model
        if api_key:
            self.config.llm.api_key = api_key

        # Save config
        self.console.print()
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

    def _manage_mcp(self) -> None:
        """Manage MCP servers through Docker."""
        import subprocess

        from rich.prompt import Confirm, Prompt
        from rich.table import Table

        self.console.print()
        self.console.print("[header]MCP Server Management[/header]")
        self.console.print()

        # Check if Docker is available
        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                self.console.print("[error]Docker not found or not running[/error]")
                self.console.print(
                    "[muted]Install Docker: https://docs.docker.com/get-docker/[/muted]"
                )
                return
            self.console.print("[success]✓ Docker available[/success]")
        except Exception:
            self.console.print("[error]Docker not available[/error]")
            return

        self.console.print()
        self.console.print("[bold]Options:[/bold]")
        self.console.print("  [cyan]1[/cyan] - List running MCP containers")
        self.console.print("  [cyan]2[/cyan] - Start an MCP server")
        self.console.print("  [cyan]3[/cyan] - Stop an MCP server")
        self.console.print("  [cyan]4[/cyan] - Pull MCP server image")
        self.console.print("  [cyan]5[/cyan] - View configured servers")
        self.console.print()

        choice = Prompt.ask(
            "[bold]Select option[/bold]", choices=["1", "2", "3", "4", "5"], default="1"
        )

        if choice == "1":
            # List running containers
            self.console.print()
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--filter",
                    "label=mcp-server",
                    "--format",
                    "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}",
                ],
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                self.console.print("[header]Running MCP Containers:[/header]")
                self.console.print(result.stdout)
            else:
                # Show all containers that might be MCP
                result = subprocess.run(
                    ["docker", "ps", "--format", "table {{.Names}}\t{{.Image}}\t{{.Status}}"],
                    capture_output=True,
                    text=True,
                )
                self.console.print("[header]Running Docker Containers:[/header]")
                self.console.print(
                    result.stdout
                    if result.stdout.strip()
                    else "[muted]No containers running[/muted]"
                )

        elif choice == "2":
            # Start an MCP server
            self.console.print()
            self.console.print("[header]Popular MCP Servers:[/header]")
            self.console.print("  [cyan]1[/cyan] - mcp/filesystem - File system access")
            self.console.print("  [cyan]2[/cyan] - mcp/fetch - HTTP fetch capabilities")
            self.console.print("  [cyan]3[/cyan] - mcp/sqlite - SQLite database")
            self.console.print("  [cyan]4[/cyan] - mcp/puppeteer - Browser automation")
            self.console.print("  [cyan]5[/cyan] - Custom image")
            self.console.print()

            server_choice = Prompt.ask(
                "[bold]Select server[/bold]", choices=["1", "2", "3", "4", "5"], default="1"
            )

            images = {
                "1": "mcp/filesystem",
                "2": "mcp/fetch",
                "3": "mcp/sqlite",
                "4": "mcp/puppeteer",
            }

            if server_choice == "5":
                image = Prompt.ask("[bold]Docker image name[/bold]")
            else:
                image = images.get(server_choice, "mcp/filesystem")

            container_name = Prompt.ask(
                "[bold]Container name[/bold]", default=f"kage-{image.split('/')[-1]}"
            )

            self.console.print()
            self.console.print(f"[info]Starting {image}...[/info]")

            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    container_name,
                    "--label",
                    "mcp-server=true",
                    image,
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                self.console.print(f"[success]✓ Started: {container_name}[/success]")

                # Add to config
                if Confirm.ask("[bold]Add to Kage config?[/bold]", default=True):
                    from kage.persistence.config import MCPServerConfig

                    mcp_config = MCPServerConfig(
                        name=container_name,
                        transport="docker",
                        docker_image=image,
                    )
                    self.config.mcp.servers.append(mcp_config)
                    self.config.save()
                    self.console.print("[success]Added to config[/success]")
            else:
                self.console.print(f"[error]Failed to start: {result.stderr}[/error]")

        elif choice == "3":
            # Stop a container
            container = Prompt.ask("[bold]Container name to stop[/bold]")
            if container:
                result = subprocess.run(
                    ["docker", "stop", container],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    self.console.print(f"[success]✓ Stopped: {container}[/success]")
                    # Optionally remove
                    if Confirm.ask("[bold]Remove container?[/bold]", default=False):
                        subprocess.run(["docker", "rm", container], capture_output=True)
                        self.console.print("[success]Container removed[/success]")
                else:
                    self.console.print(f"[error]Failed: {result.stderr}[/error]")

        elif choice == "4":
            # Pull an image
            image = Prompt.ask("[bold]Image to pull[/bold]", default="mcp/filesystem")
            self.console.print(f"[info]Pulling {image}...[/info]")
            result = subprocess.run(
                ["docker", "pull", image],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                self.console.print(f"[success]✓ Pulled: {image}[/success]")
            else:
                self.console.print(f"[error]Failed: {result.stderr}[/error]")

        elif choice == "5":
            # View configured servers
            self.console.print()
            if self.config.mcp.servers:
                table = Table(title="Configured MCP Servers", header_style="table.header")
                table.add_column("Name", style="highlight")
                table.add_column("Transport", style="info")
                table.add_column("Image/Command", style="muted")
                table.add_column("Enabled", style="info")

                for server in self.config.mcp.servers:
                    table.add_row(
                        server.name,
                        server.transport,
                        server.docker_image or server.command or "-",
                        "✓" if server.enabled else "✗",
                    )
                self.console.print(table)
            else:
                self.console.print("[muted]No MCP servers configured[/muted]")
                self.console.print("[muted]Use option 2 to start a server[/muted]")

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
        asyncio.run(
            run_hack_mode(
                console=self.console,
                config=self.config,
                target=target,
                scope=scope,
                skip_warning=False,
            )
        )

    def _run_pending_commands(self) -> None:
        """Execute pending commands with planning, approval, and routing."""
        if not self._pending_commands:
            self.console.print("[muted]No pending commands.[/muted]")
            return

        from rich.prompt import Confirm

        from kage.cli.ui.prompts import (
            ApprovalChoice,
            prompt_command_approval,
            prompt_plan_approval,
            prompt_plan_edit,
        )
        from kage.security import ApprovalDecision, ApprovalWorkflow
        from kage.security.safemode import DangerLevel

        # Create approval workflow
        workflow = ApprovalWorkflow(
            scope=self.session.scope,
            safe_mode_enabled=self.session.safe_mode,
            require_approval=self.config.security.require_approval,
            scope_enforcement=self.config.security.scope_enforcement,
        )

        commands_to_run = self._pending_commands[:]

        # --- Multi-step plan display (2+ commands) ---
        if len(commands_to_run) >= 2:
            plan = ExecutionPlan.from_commands(commands_to_run)
            steps = [
                (s.index, s.command.command, s.command.description)
                for s in plan.steps
            ]

            choice = prompt_plan_approval(self.console, steps)

            if choice == "cancel":
                self._pending_commands.clear()
                self.console.print("[muted]Plan cancelled.[/muted]")
                return

            if choice == "edit":
                to_remove = prompt_plan_edit(self.console, plan.total_steps)
                for idx in sorted(to_remove, reverse=True):
                    plan.remove_step(idx)

                if not plan.steps:
                    self._pending_commands.clear()
                    self.console.print("[muted]All steps removed. Plan cancelled.[/muted]")
                    return

                commands_to_run = [s.command for s in plan.steps]
                self.console.print(
                    f"[info]Running {len(commands_to_run)} step(s).[/info]"
                )

        # --- Execute each command ---
        for i, cmd in enumerate(commands_to_run):
            step_label = f"[{i + 1}/{len(commands_to_run)}]" if len(commands_to_run) > 1 else ""
            preliminary_route = self._router.route(cmd.command)

            self.console.print()
            if step_label:
                self.console.print(f"[info]{step_label}[/info] ", end="")
            self.console.print(f"[command]$ {cmd.command}[/command]")
            if cmd.description:
                self.console.print(f"[muted]{cmd.description}[/muted]")

            if preliminary_route.tool_name and not self._ensure_tool_installed(
                preliminary_route.tool_name
            ):
                cmd.status = CommandStatus.REJECTED
                self.session.commands.append(cmd)
                if cmd in self._pending_commands:
                    self._pending_commands.remove(cmd)
                self.console.print("[muted]Skipped (missing tool).[/muted]")
                continue

            if (
                preliminary_route.tool_name
                and preliminary_route.tool_name in SECURITY_TOOLS
                and not self.session.scope.targets
                and not self._check_and_prompt_scope(cmd.command)
            ):
                cmd.status = CommandStatus.REJECTED
                self.session.commands.append(cmd)
                if cmd in self._pending_commands:
                    self._pending_commands.remove(cmd)
                self.console.print("[muted]Skipped[/muted]")
                continue

            # Run through security approval workflow
            result = asyncio.run(workflow.evaluate(cmd))

            # Handle blocked commands
            if result.decision == ApprovalDecision.BLOCKED:
                self.console.print(
                    Panel(
                        f"[danger]{result.reason}[/danger]",
                        title="[unsafe]🛡 BLOCKED BY SAFE MODE[/unsafe]",
                        border_style="danger",
                    )
                )
                cmd.status = CommandStatus.REJECTED
                self.session.commands.append(cmd)
                if cmd in self._pending_commands:
                    self._pending_commands.remove(cmd)
                continue

            # Show warnings
            if result.warnings:
                self.console.print()
                for warning in result.warnings:
                    self.console.print(f"[warning]{warning}[/warning]")

            if (
                result.safe_mode_result
                and result.safe_mode_result.danger_level == DangerLevel.DANGEROUS
            ):
                self.console.print(
                    Panel(
                        "[danger]WARNING: This command may impact system stability or targets.[/danger]\n"
                        f"[command]{cmd.command}[/command]",
                        title="[unsafe]⚠ Dangerous Command[/unsafe]",
                        border_style="danger",
                    )
                )
                if not Confirm.ask("[danger]Continue?[/danger]", default=False):
                    cmd.status = CommandStatus.REJECTED
                    self.session.commands.append(cmd)
                    if cmd in self._pending_commands:
                        self._pending_commands.remove(cmd)
                    self.console.print("[muted]Skipped[/muted]")
                    continue

            # --- Enhanced approval (4-option) ---
            if result.decision == ApprovalDecision.NEEDS_CONFIRMATION:
                approval = prompt_command_approval(
                    self.console, cmd,
                    session_approved_all=self._approved_all,
                    session_approved_tools=self._approved_tools,
                )

                if approval == ApprovalChoice.CANCEL:
                    cmd.status = CommandStatus.REJECTED
                    self.session.commands.append(cmd)
                    if cmd in self._pending_commands:
                        self._pending_commands.remove(cmd)
                    self.console.print("[muted]Skipped[/muted]")
                    continue

                if approval == ApprovalChoice.ALWAYS:
                    self._approved_all = True

                if approval == ApprovalChoice.APPROVE_TOOL:
                    tool = cmd.command.strip().split()[0].lower()
                    self._approved_tools.add(tool)
                    self.console.print(
                        f"[info]Auto-approving '{tool}' for this session.[/info]"
                    )

            # --- Route and execute ---
            cmd.status = CommandStatus.APPROVED
            route = self._router.route(cmd.command)
            self._log_action("Running command", cmd.command)

            if route.executor_type == ExecutorType.KALI_MCP:
                cmd.environment = ExecutionEnvironment.KALI_MCP
                self.console.print(
                    f"[info]→ Routing to Kali MCP ({route.reasoning})[/info]"
                )

            asyncio.run(self._execute_command(cmd, route))
            if cmd in self._pending_commands:
                self._pending_commands.remove(cmd)

    async def _execute_command(self, cmd: Command, route: RouteResult | None = None) -> None:
        """Execute a single command using the appropriate executor."""
        from kage.core.router import ExecutorType
        from kage.executor import LocalExecutor

        if route is None:
            route = self._router.route(cmd.command)

        cmd.status = CommandStatus.RUNNING
        cmd.started_at = utcnow()

        self.console.print("[status.running]Running...[/status.running]")

        executor = None

        # Select executor based on routing
        if route.executor_type == ExecutorType.KALI_MCP:
            try:
                from kage.executor.kali import KaliExecutor

                if self._kali_executor is None:
                    self._kali_executor = KaliExecutor(
                        servers=dict(self.config.kali.servers),
                    )
                executor = self._kali_executor
            except Exception as e:
                if route.fallback_to_local or self.config.kali.fallback_to_local:
                    self.console.print(
                        f"[warning]Kali MCP unavailable ({e}). Falling back to local.[/warning]"
                    )
                    executor = LocalExecutor()
                else:
                    cmd.status = CommandStatus.FAILED
                    cmd.stderr = f"Kali MCP unavailable: {e}"
                    cmd.completed_at = utcnow()
                    self.session.commands.append(cmd)
                    self.console.print(f"[error]Kali MCP unavailable: {e}[/error]")
                    return

        if executor is None:
            executor = LocalExecutor()

        try:
            result = await executor.execute(cmd.command, timeout=cmd.timeout)

            cmd.exit_code = result.exit_code
            cmd.stdout = result.stdout
            cmd.stderr = result.stderr
            cmd.status = CommandStatus.COMPLETED if not result.timed_out else CommandStatus.TIMEOUT
            cmd.completed_at = utcnow()

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
            # MCP fallback: if Kali execution failed, try local
            if (
                route
                and route.executor_type == ExecutorType.KALI_MCP
                and (route.fallback_to_local or self.config.kali.fallback_to_local)
            ):
                self.console.print(
                    f"[warning]Kali MCP failed ({e}). Falling back to local...[/warning]"
                )
                try:
                    fallback = LocalExecutor()
                    result = await fallback.execute(cmd.command, timeout=cmd.timeout)
                    cmd.exit_code = result.exit_code
                    cmd.stdout = result.stdout
                    cmd.stderr = result.stderr
                    cmd.status = (
                        CommandStatus.COMPLETED if not result.timed_out
                        else CommandStatus.TIMEOUT
                    )
                    cmd.completed_at = utcnow()
                    if result.stdout:
                        self.console.print(
                            Panel(
                                result.stdout[:2000],
                                title="[panel.title]Output (local fallback)[/panel.title]",
                                border_style="panel.border",
                            )
                        )
                    self.console.print(
                        f"[status.completed]Completed via local (exit: {result.exit_code})[/status.completed]"
                    )
                except Exception as e2:
                    cmd.status = CommandStatus.FAILED
                    cmd.stderr = f"MCP: {e} | Local fallback: {e2}"
                    cmd.completed_at = utcnow()
                    self.console.print(f"[error]All executors failed: {e2}[/error]")
            else:
                cmd.status = CommandStatus.FAILED
                cmd.stderr = str(e)
                cmd.completed_at = utcnow()
                self.console.print(f"[error]Failed: {e}[/error]")

        self.console.print(f"[subtitle]Summary:[/subtitle] {self._summarize_command_result(cmd)}")

        # Add to session history
        if route and route.tool_name and route.tool_name in SECURITY_TOOLS:
            self._remember_security_result(cmd, tool_name=route.tool_name)
        self.session.commands.append(cmd)

    async def _try_reconnect(self) -> bool:
        """Attempt to reconnect to the LLM provider."""
        self.console.print("[warning]Connection lost. Reconnecting...[/warning]")
        for attempt in range(3):
            try:
                if self.provider:
                    await self.provider.close()
                self.provider = create_provider(self.config.llm)
                connected = await self.provider.check_connection()
                if connected:
                    await self.provider.close()
                    self.conversation = ConversationManager(
                        provider=self.provider,
                        config=self.config,
                        session=self.session,
                    )
                    self.console.print("[success]Reconnected.[/success]")
                    return True
            except Exception:
                pass
            self.console.print(f"[warning]Retry {attempt + 1}/3...[/warning]")
            import time

            time.sleep(2**attempt)
        return False

    async def _process_message(self, user_input: str) -> None:
        """Process a user message with intent detection and generate response."""
        if not self.conversation:
            self.console.print("[error]AI not connected. Restart session.[/error]")
            return

        if await self._handle_natural_language_file_request(user_input):
            return

        # --- Intent detection ---
        intent_result = classify_intent(user_input)

        # Show intent badge for non-chat intents
        if intent_result.intent != Intent.CHAT:
            intent_label = {
                Intent.SECURITY: "[red]⚡ security[/red]",
                Intent.DEVELOPMENT: "[green]⚙ development[/green]",
                Intent.SYSTEM: "[blue]🖥 system[/blue]",
            }.get(intent_result.intent, "")
            self.console.print(f"\n[muted]Intent:[/muted] {intent_label}")

        # --- Scope auto-prompt for security intent ---
        security_context: str | None = None
        if (
            intent_result.intent == Intent.SECURITY
            and not self.session.scope.targets
            and not self._check_and_prompt_scope(user_input)
        ):
            return

        if intent_result.intent == Intent.SECURITY:
            security_context = await self._build_security_mcp_context(user_input)

        self.console.print()
        self.console.print("[assistant]KAGE:[/assistant] ", end="")

        try:
            response_text, commands = await self.conversation.send_message(
                user_input,
                on_chunk=lambda c: self.console.print(c, end="", highlight=False),
                additional_context=security_context,
            )

            # If nothing was streamed (error/empty), print the response text directly
            if response_text and response_text.startswith(("Error ", "No response")):
                self.console.print(response_text, highlight=False)

            self.console.print()  # Newline after streaming

            # --- Tag commands with routing info ---
            if commands:
                for cmd in commands:
                    route = self._router.route(cmd.command)
                    if route.executor_type == ExecutorType.KALI_MCP:
                        cmd.environment = ExecutionEnvironment.KALI_MCP

                self._pending_commands.extend(commands)
                self.console.print()
                self.console.print(
                    f"[info]{len(commands)} command(s) suggested. "
                    f"Use /commands to view, /run to execute.[/info]"
                )

        except Exception as e:
            self.console.print()
            self.console.print(f"[error]Error: {e}[/error]")
            if await self._try_reconnect():
                self.console.print("[info]Please resend your message.[/info]")
            else:
                self.console.print("[error]Could not reconnect. Use /exit to end session.[/error]")

    def run(self) -> None:
        """Run the interactive chat loop."""
        # Initialize provider
        if not asyncio.run(self._init_provider()):
            return
        asyncio.run(self._init_mcp())

        # Set up tab completion for slash commands
        self._setup_completer()

        # Show static startup banner
        from kage.cli.ui.banner import show_startup_banner

        show_startup_banner(
            self.console,
            provider=self.config.llm.provider,
            model=self.config.llm.model,
        )

        while self.running:
            try:
                # Get user input with styled prompt box
                self.console.print()
                self.console.print(
                    "[cyan]╭─[/cyan][bold cyan] kage [/bold cyan][cyan]─────────────────────────────────────────────────────────[/cyan]"
                )
                self.console.print("[cyan]│[/cyan]")
                user_input = self.console.input("[cyan]│[/cyan] [prompt.arrow]>[/prompt.arrow] ")
                self.console.print(
                    "[cyan]╰──────────────────────────────────────────────────────────────────[/cyan]"
                )

                if not user_input.strip():
                    continue

                # Handle slash commands
                if user_input.startswith("/"):
                    if not self._handle_slash_command(user_input):
                        break
                    continue

                # Intercept identity questions and answer locally
                if self._is_identity_question(user_input):
                    self._show_identity()
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
        if self._mcp_manager:
            asyncio.run(self._mcp_manager.stop())

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
