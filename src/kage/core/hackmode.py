"""Hack mode - autonomous penetration testing."""

from __future__ import annotations

import asyncio
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, cast

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from kage.ai.base import BaseLLMProvider
from kage.core.intent import SECURITY_TOOLS
from kage.core.models import Command, CommandStatus, Finding, Session, Severity, Target
from kage.executor import LocalExecutor
from kage.persistence.config import KageConfig
from kage.reporting.export import OutputFormat
from kage.security.output_parser import parse_tool_output
from kage.security.safemode import DangerLevel, SafeModeFilter
from kage.utils import utcnow


class HackPhase(str, Enum):
    """Phases of autonomous hacking."""

    INIT = "init"
    PLANNING = "planning"
    RECON = "recon"
    ENUMERATION = "enumeration"
    EXPLOITATION = "exploitation"
    REPORTING = "reporting"
    COMPLETE = "complete"


PHASE_DESCRIPTIONS = {
    HackPhase.INIT: "Initializing hack mode...",
    HackPhase.PLANNING: "Creating attack plan...",
    HackPhase.RECON: "Performing reconnaissance...",
    HackPhase.ENUMERATION: "Enumerating services & vulnerabilities...",
    HackPhase.EXPLOITATION: "Testing & exploiting vulnerabilities...",
    HackPhase.REPORTING: "Generating penetration test report...",
    HackPhase.COMPLETE: "Hack mode complete!",
}


HACK_BANNER = """
[bold red]
    ██╗  ██╗ █████╗  ██████╗██╗  ██╗    ███╗   ███╗ ██████╗ ██████╗ ███████╗
    ██║  ██║██╔══██╗██╔════╝██║ ██╔╝    ████╗ ████║██╔═══██╗██╔══██╗██╔════╝
    ███████║███████║██║     █████╔╝     ██╔████╔██║██║   ██║██║  ██║█████╗
    ██╔══██║██╔══██║██║     ██╔═██╗     ██║╚██╔╝██║██║   ██║██║  ██║██╔══╝
    ██║  ██║██║  ██║╚██████╗██║  ██╗    ██║ ╚═╝ ██║╚██████╔╝██████╔╝███████╗
    ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝    ╚═╝     ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝
[/bold red]
[bold yellow]                    ⚠  AUTONOMOUS PENETRATION TESTING MODE  ⚠[/bold yellow]
"""

AUTHORIZATION_WARNING = """
[bold red]╔══════════════════════════════════════════════════════════════════════════════╗
║                              ⚠  CRITICAL WARNING  ⚠                              ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                  ║
║  HACK MODE will perform ACTIVE penetration testing on the target.                ║
║                                                                                  ║
║  This includes:                                                                  ║
║    • Port scanning and service enumeration                                       ║
║    • Vulnerability scanning and exploitation attempts                            ║
║    • Bruteforce attacks on discovered services                                   ║
║    • Active exploitation of vulnerabilities                                      ║
║                                                                                  ║
║  [yellow]YOU MUST HAVE WRITTEN AUTHORIZATION to test the target system.[/yellow]              ║
║  [yellow]Unauthorized access to computer systems is a CRIMINAL OFFENSE.[/yellow]              ║
║                                                                                  ║
╚══════════════════════════════════════════════════════════════════════════════════╝
[/bold red]
"""


class HackModeEngine:
    """Autonomous penetration testing engine."""

    def __init__(
        self,
        console: Console,
        config: KageConfig,
        target: str,
        scope: list[str] | None = None,
    ) -> None:
        self.console = console
        self.config = config
        self.target = target
        self.scope = scope or [target]
        self.session = Session(safe_mode=True)
        self.phase = HackPhase.INIT
        self.provider: BaseLLMProvider | None = None
        self._findings: list[Finding] = []
        self._commands_run: list[Command] = []
        self._attack_plan: dict[str, Any] = {}
        self._start_time: datetime | None = None
        self._safe_mode_filter = SafeModeFilter(enabled=True)
        self._approved_all_commands = False
        self._max_iterations = 20
        self._iteration_count = 0
        memory = self.session.metadata.setdefault("security_memory", {})
        memory.setdefault("target", target)
        memory.setdefault("open_ports", [])
        memory.setdefault("services", [])
        memory.setdefault("vulnerabilities", [])
        memory.setdefault("credentials", [])
        memory.setdefault("notes", [])

    async def _init_llm(self) -> bool:
        """Initialize LLM provider."""
        from kage.ai.providers import create_provider

        try:
            self.provider = create_provider(self.config.llm)
            connected = await self.provider.check_connection()
            if not connected:
                self.console.print("[error]Could not connect to LLM provider[/error]")
                return False
            return True
        except Exception as e:
            self.console.print(f"[error]LLM initialization failed: {e}[/error]")
            return False

    def _memory_tool(self, action: str, key: str, value: Any | None = None) -> Any:
        """Store or retrieve autonomous workflow memory."""
        memory = self.session.metadata.setdefault("security_memory", {})

        if action == "get":
            return memory.get(key)

        if action == "append":
            values = memory.setdefault(key, [])
            if not isinstance(values, list):
                values = []
                memory[key] = values
            values.append(value)
            return values

        if action == "set":
            memory[key] = value
            return value

        raise ValueError(f"Unsupported memory action: {action}")

    # Public tool-style wrappers (explicit names for autonomous workflow).
    def memory_tool(self, action: str, key: str, value: Any | None = None) -> Any:
        return self._memory_tool(action, key, value)

    def _planner_tool(self, target: str, task: str) -> list[str]:
        """Build a deterministic pentest plan for the target/task."""
        normalized_task = task.lower()

        if "scan" in normalized_task or "recon" in normalized_task:
            plan = [
                f"nmap -sV -sC {target}",
                f"gobuster dir -u http://{target} -w /usr/share/wordlists/dirb/common.txt",
                f"nikto -h http://{target}",
                f"sqlmap -u http://{target} --batch --crawl=1",
            ]
        else:
            plan = [
                f"nmap -sV -sC {target}",
                f"nmap -sV --script=vuln {target}",
            ]

        self._memory_tool("set", "target", target)
        self._memory_tool("set", "plan", plan)
        self._attack_plan["autonomous_plan"] = plan
        return plan

    def planner_tool(self, target: str, task: str) -> list[str]:
        return self._planner_tool(target, task)

    async def _execute_local(self, command: str) -> tuple[int, str, str, str]:
        """Execute command locally."""
        local = LocalExecutor()
        local_result = await local.execute(command, timeout=300)
        return local_result.exit_code, local_result.stdout, local_result.stderr, "local"

    async def _shell_tool(self, command: str) -> Command:
        """Execute a shell command with approval + safety warning."""
        if self._iteration_count >= self._max_iterations:
            self.console.print("[warning]Reached maximum autonomous iterations (20).[/warning]")
            cmd = Command(
                command=command,
                description="Skipped due to iteration limit",
                status=CommandStatus.REJECTED,
                completed_at=utcnow(),
            )
            self._commands_run.append(cmd)
            self.session.commands.append(cmd)
            return cmd

        risk = self._safe_mode_filter.check(command)
        if risk.danger_level in (DangerLevel.BLOCKED, DangerLevel.DANGEROUS):
            self.console.print(
                f"[warning]Dangerous command detected: {risk.reason or 'High risk'}[/warning]"
            )

        if not self._approved_all_commands:
            approve = Confirm.ask(
                f"[warning]Approve command?[/warning] [command]{command}[/command]",
                default=False,
            )
            if not approve:
                cmd = Command(
                    command=command,
                    description="Command rejected by user",
                    status=CommandStatus.REJECTED,
                    completed_at=utcnow(),
                )
                self._commands_run.append(cmd)
                self.session.commands.append(cmd)
                return cmd
            if Confirm.ask(
                "[info]Approve all subsequent commands for this run?[/info]",
                default=False,
            ):
                self._approved_all_commands = True

        self._iteration_count += 1
        return await self._execute_command(command, "Autonomous tool execution")

    async def shell_tool(self, command: str) -> Command:
        return await self._shell_tool(command)

    def _report_tool(self, title: str) -> None:
        """Record report metadata in session memory."""
        self._memory_tool("set", "report_title", title)

    def report_tool(self, title: str) -> None:
        self._report_tool(title)

    def _set_phase(self, phase: HackPhase) -> None:
        """Update current phase."""
        self.phase = phase
        self.console.print()
        self.console.print(
            Panel(
                f"[bold]{PHASE_DESCRIPTIONS[phase]}[/bold]",
                title=f"[cyan]Phase: {phase.value.upper()}[/cyan]",
                border_style="cyan",
            )
        )

    async def _execute_command(self, command: str, description: str | None = None) -> Command:
        """Execute a command and return result."""
        cmd = Command(
            command=command,
            description=description,
            status=CommandStatus.RUNNING,
            started_at=utcnow(),
        )

        self.console.print(f"  [dim]$[/dim] [command]{command}[/command]")

        try:
            exit_code, stdout, stderr, environment = await self._execute_local(command)
            cmd.exit_code = exit_code
            cmd.stdout = stdout
            cmd.stderr = stderr
            cmd.status = CommandStatus.COMPLETED
            cmd.completed_at = utcnow()

            # Show truncated output
            if stdout:
                lines = stdout.strip().split("\n")
                if len(lines) > 5:
                    self.console.print(f"    [dim]{lines[0]}[/dim]")
                    self.console.print(f"    [dim]... ({len(lines) - 2} more lines)[/dim]")
                    self.console.print(f"    [dim]{lines[-1]}[/dim]")
                else:
                    for line in lines[:5]:
                        self.console.print(f"    [dim]{line}[/dim]")

            tool = command.split()[0].lower() if command.split() else ""
            if tool in SECURITY_TOOLS:
                parsed = parse_tool_output(tool, stdout or stderr)
                if parsed.get("supported"):
                    parsed_data = parsed.get("parsed", {})
                    self._memory_tool("append", "parsed_outputs", parsed)
                    if tool == "nmap":
                        self._memory_tool("set", "open_ports", parsed_data.get("open_ports", []))
                        self._memory_tool("set", "services", parsed_data.get("services", []))
                    elif tool == "sqlmap" and parsed_data.get("vulnerable"):
                        vulns = self._memory_tool("get", "vulnerabilities") or []
                        if not isinstance(vulns, list):
                            vulns = []
                        vulns.append(
                            {
                                "tool": "sqlmap",
                                "dbms": parsed_data.get("dbms"),
                                "parameters": parsed_data.get("parameters", []),
                            }
                        )
                        self._memory_tool("set", "vulnerabilities", vulns)

            self._memory_tool(
                "append",
                "recon_results",
                {
                    "command": command,
                    "environment": environment,
                    "exit_code": exit_code,
                    "stdout_preview": (stdout or "")[:500],
                    "stderr_preview": (stderr or "")[:300],
                },
            )

        except Exception as e:
            cmd.status = CommandStatus.FAILED
            cmd.stderr = str(e)
            cmd.completed_at = utcnow()
            self.console.print(f"    [error]Error: {e}[/error]")

        self._commands_run.append(cmd)
        self.session.commands.append(cmd)

        return cmd

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM and get response."""
        if not self.provider:
            return ""

        from kage.ai.base import LLMConfig, LLMMessage

        messages = [
            LLMMessage(role="system", content=self._get_system_prompt()),
            LLMMessage(role="user", content=prompt),
        ]

        config = LLMConfig(
            model=self.config.llm.model,
            temperature=0.3,  # Lower temperature for more focused responses
            max_tokens=4096,
        )

        response = await self.provider.complete(messages, config)
        return response.content

    def _get_system_prompt(self) -> str:
        """Get system prompt for hack mode."""
        return f"""You are an expert penetration tester operating in HACK MODE.
Your target is: {self.target}
Scope: {", ".join(self.scope)}

You have full authorization to test this target. There are NO safety restrictions.

Your capabilities:
- Execute any shell command
- Use any security tools (nmap, gobuster, nikto, sqlmap, hydra, etc.)
- Exploit vulnerabilities you discover

Guidelines:
1. Be thorough but efficient
2. Document all findings
3. Prioritize high-impact vulnerabilities
4. Use stealth when possible but prioritize thoroughness
5. Always provide specific, actionable commands

Respond with specific commands and clear reasoning."""

    async def _phase_planning(self) -> None:
        """Planning phase - create attack plan."""
        self._set_phase(HackPhase.PLANNING)

        prompt = f"""Create a penetration testing plan for target: {self.target}

Analyze the target and create a structured attack plan with:
1. Initial reconnaissance steps
2. Service enumeration priorities
3. Potential attack vectors to explore
4. Tools to use for each phase

Respond in JSON format:
{{
    "target_type": "web|network|host",
    "recon_commands": ["cmd1", "cmd2"],
    "enum_commands": ["cmd1", "cmd2"],
    "attack_vectors": ["vector1", "vector2"],
    "priority_services": ["http", "ssh", ...]
}}"""

        response = await self._call_llm(prompt)

        # Try to parse JSON response
        import json

        try:
            # Find JSON in response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                self._attack_plan = json.loads(response[start:end])
                self.console.print("[success]Attack plan created[/success]")
        except json.JSONDecodeError:
            # Use default plan
            self._attack_plan = {
                "target_type": "unknown",
                "recon_commands": [
                    f"nmap -sn {self.target}",
                    f"nmap -sV -sC -p- {self.target}",
                ],
                "enum_commands": [
                    f"nmap -sV --script=vuln {self.target}",
                ],
                "attack_vectors": ["service_exploit", "web_vuln"],
            }

        plan = self._planner_tool(self.target, f"scan {self.target}")
        self._attack_plan["autonomous_plan"] = plan

    async def _phase_recon(self) -> None:
        """Reconnaissance phase."""
        self._set_phase(HackPhase.RECON)

        plan_commands = self._attack_plan.get("autonomous_plan", [])
        recon_commands = [
            cmd
            for cmd in plan_commands
            if isinstance(cmd, str) and cmd.split()[0].lower() in {"nmap", "gobuster", "nikto", "sqlmap"}
        ]
        if not recon_commands:
            recon_commands = self._attack_plan.get(
                "recon_commands",
                [
                    f"ping -c 3 {self.target}",
                    f"nmap -sn {self.target}",
                    f"nmap -sV -sC -p 1-1000 {self.target}",
                    f"whois {self.target}" if "." in self.target else None,
                ],
            )

        self.console.print("[warning]Confirm scope before active scans.[/warning]")
        self.console.print(f"[info]Scope: {', '.join(self.scope)}[/info]")
        if not Confirm.ask("[warning]Proceed with active reconnaissance?[/warning]", default=False):
            self.console.print("[muted]Recon phase cancelled by user.[/muted]")
            return

        for idx, cmd in enumerate(recon_commands):
            if idx >= self._max_iterations:
                break
            if cmd:
                await self._shell_tool(cmd)
                await asyncio.sleep(1)  # Small delay between commands

    async def _phase_enumeration(self) -> None:
        """Enumeration phase."""
        self._set_phase(HackPhase.ENUMERATION)

        enum_commands = self._attack_plan.get(
            "enum_commands",
            [
                f"nmap -sV --script=vuln -p- {self.target}",
            ],
        )

        for cmd in enum_commands:
            if cmd:
                await self._shell_tool(cmd)
                await asyncio.sleep(1)

        # Ask LLM to analyze results and suggest more enumeration
        if self._commands_run:
            recent_output = "\n".join(
                [
                    f"Command: {c.command}\nOutput: {(c.stdout or '')[:500]}"
                    for c in self._commands_run[-3:]
                ]
            )

            prompt = f"""Based on these reconnaissance results, what additional enumeration should we perform?

{recent_output}

Suggest 2-3 specific commands to run next. Focus on discovered services.
Respond with just the commands, one per line."""

            response = await self._call_llm(prompt)

            # Execute suggested commands
            for line in response.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("#") and len(line) > 5:
                    # Basic sanitization
                    if any(c in line for c in ["|", ";", "&&", "`", "$("]):
                        continue  # Skip potentially dangerous command chaining
                    await self._shell_tool(line)

    async def _phase_exploitation(self) -> None:
        """Exploitation phase."""
        self._set_phase(HackPhase.EXPLOITATION)

        # Analyze findings and attempt exploitation
        all_output = "\n".join(
            [f"Command: {c.command}\nOutput: {(c.stdout or '')[:1000]}" for c in self._commands_run]
        )

        prompt = f"""Based on the reconnaissance and enumeration results, identify potential vulnerabilities and suggest exploitation commands.

Results:
{all_output}

For each vulnerability found:
1. Describe the vulnerability
2. Rate severity (critical/high/medium/low)
3. Provide a specific exploitation command

Focus on verified vulnerabilities only. Be specific."""

        response = await self._call_llm(prompt)

        # Parse and record findings
        self.console.print()
        self.console.print("[header]Vulnerability Analysis[/header]")
        self.console.print(response)

        # Add findings (simplified - in production would parse LLM response)
        if "critical" in response.lower() or "high" in response.lower():
            finding = Finding(
                title="Potential Vulnerability Detected",
                severity=Severity.MEDIUM,
                description=response[:500],
                target=self.target,
                auto_detected=True,
            )
            self._findings.append(finding)
            self.session.findings.append(finding)
            vulnerabilities = self._memory_tool("get", "vulnerabilities") or []
            if not isinstance(vulnerabilities, list):
                vulnerabilities = []
            vulnerabilities.append(
                {"title": finding.title, "severity": finding.severity.value, "description": finding.description}
            )
            self._memory_tool("set", "vulnerabilities", vulnerabilities)
        self._memory_tool("append", "notes", response[:500])

    async def _phase_reporting(self) -> None:
        """Generate final report."""
        self._set_phase(HackPhase.REPORTING)
        self._report_tool(f"Kage Pentest Report - {self.target}")

        from kage.reporting import ReportExporter

        # Update session with all data
        self.session.updated_at = utcnow()

        # Add target to scope
        import ipaddress

        try:
            ipaddress.ip_address(self.target)
            target_type = "ip"
        except ValueError:
            target_type = "domain"

        self.session.scope.targets.append(
            Target(
                value=self.target,
                target_type=target_type,
            )
        )

        # Generate report
        report_format = cast(OutputFormat, self.config.hack_mode.report_format)
        filename = f"hackmode_report_{self.target.replace('.', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        if report_format == "html":
            output_path = Path.cwd() / f"{filename}.html"
        elif report_format == "pdf":
            output_path = Path.cwd() / f"{filename}.pdf"
        else:
            output_path = Path.cwd() / f"{filename}.md"

        try:
            exporter = ReportExporter()
            result_path = await exporter.export(self.session, output_path, report_format)
            self.console.print(f"[success]Report generated: {result_path}[/success]")
        except Exception as e:
            self.console.print(f"[warning]Could not generate report: {e}[/warning]")
            # Fallback to simple text report
            self._generate_simple_report(output_path.with_suffix(".txt"))

    def _generate_simple_report(self, output_path: Path) -> None:
        """Generate a simple text report as fallback."""
        duration = (utcnow() - self._start_time).total_seconds() if self._start_time else 0

        report = f"""
KAGE HACK MODE REPORT
=====================
Target: {self.target}
Date: {datetime.now().isoformat()}
Duration: {duration:.0f} seconds

SCOPE
-----
{chr(10).join(self.scope)}

COMMANDS EXECUTED
-----------------
{chr(10).join(f"- {c.command} (exit: {c.exit_code})" for c in self._commands_run)}

FINDINGS
--------
{chr(10).join(f"- [{f.severity.value}] {f.title}" for f in self._findings) or "No findings recorded"}

---
Generated by Kage Hack Mode
"""
        output_path.write_text(report)
        self.console.print(f"[success]Simple report saved: {output_path}[/success]")

    async def run(self) -> Session:
        """Run the full hack mode workflow."""
        self._start_time = utcnow()

        try:
            # Initialize
            if not await self._init_llm():
                return self.session

            # Run phases
            await self._phase_planning()
            await self._phase_recon()
            await self._phase_enumeration()
            await self._phase_exploitation()
            await self._phase_reporting()

            self._set_phase(HackPhase.COMPLETE)

        except KeyboardInterrupt:
            self.console.print("\n[warning]Hack mode interrupted by user[/warning]")

        except Exception as e:
            self.console.print(f"\n[error]Hack mode error: {e}[/error]")

        finally:
            # Cleanup
            if self.provider:
                await self.provider.close()

        # Summary
        duration = (utcnow() - self._start_time).total_seconds()
        self._print_summary(duration)

        return self.session

    def _print_summary(self, duration: float) -> None:
        """Print hack mode summary."""
        self.console.print()

        table = Table(title="[bold]Hack Mode Summary[/bold]", border_style="cyan")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Target", self.target)
        table.add_row("Duration", f"{duration:.0f} seconds")
        table.add_row("Commands Run", str(len(self._commands_run)))
        table.add_row("Findings", str(len(self._findings)))

        # Count findings by severity
        severity_counts: dict[str, int] = {}
        for f in self._findings:
            severity_counts[f.severity.value] = severity_counts.get(f.severity.value, 0) + 1

        if severity_counts:
            severity_str = ", ".join(f"{k}: {v}" for k, v in severity_counts.items())
            table.add_row("By Severity", severity_str)

        self.console.print(table)


def show_authorization_prompt(console: Console) -> bool:
    """Show authorization warning and get confirmation."""
    from rich.prompt import Confirm

    console.print(AUTHORIZATION_WARNING)

    return Confirm.ask(
        "[bold yellow]Do you have WRITTEN AUTHORIZATION to test this target?[/bold yellow]",
        default=False,
    )


async def run_hack_mode(
    console: Console,
    config: KageConfig,
    target: str,
    scope: list[str] | None = None,
    skip_warning: bool = False,
) -> None:
    """Run hack mode."""
    console.print(HACK_BANNER)

    # Authorization check
    if not skip_warning and not show_authorization_prompt(console):
        console.print("[info]Hack mode cancelled.[/info]")
        return

    console.print()
    console.print(f"[bold green]Target:[/bold green] {target}")
    console.print(f"[bold green]Scope:[/bold green] {', '.join(scope or [target])}")
    console.print()

    # Run hack mode
    engine = HackModeEngine(console, config, target, scope)
    await engine.run()
