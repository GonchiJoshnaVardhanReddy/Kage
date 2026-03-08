"""Rich UI panels for Kage."""

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from kage.core.models import Command, CommandStatus, Finding, Scope, Severity


def create_status_panel(
    safe_mode: bool,
    scope: Scope | None,
    session_id: str | None,
    provider: str,
    model: str,
) -> Panel:
    """Create the status panel shown at the top of the chat."""
    table = Table.grid(padding=(0, 2))
    table.add_column(justify="left")
    table.add_column(justify="left")
    table.add_column(justify="left")
    table.add_column(justify="left")

    # Safe mode indicator
    safe_text = Text()
    if safe_mode:
        safe_text.append("● ", style="safe")
        safe_text.append("SAFE MODE", style="safe")
    else:
        safe_text.append("● ", style="unsafe")
        safe_text.append("UNSAFE", style="unsafe")

    # Scope indicator
    scope_text = Text()
    if scope and scope.targets:
        scope_text.append(f"{len(scope.targets)} targets", style="scope.in")
    else:
        scope_text.append("No scope", style="muted")

    # Session indicator
    session_text = Text()
    if session_id:
        session_text.append(session_id[:8], style="highlight")
    else:
        session_text.append("New session", style="muted")

    # Model indicator
    model_text = Text()
    model_text.append(f"{provider}/{model}", style="info")

    table.add_row(safe_text, scope_text, session_text, model_text)

    return Panel(
        table,
        title="[panel.title]Status[/panel.title]",
        border_style="panel.border",
        padding=(0, 1),
        expand=True,
    )


def create_command_panel(command: Command, show_output: bool = True) -> Panel:
    """Create a panel displaying a command and its status."""
    content = []

    # Command line
    cmd_text = Text()
    cmd_text.append("$ ", style="prompt.arrow")
    cmd_text.append(command.command, style="command")
    content.append(cmd_text)

    # Status
    status_style = {
        CommandStatus.PENDING: "status.pending",
        CommandStatus.APPROVED: "command.approved",
        CommandStatus.REJECTED: "command.rejected",
        CommandStatus.RUNNING: "status.running",
        CommandStatus.COMPLETED: "status.completed",
        CommandStatus.FAILED: "status.failed",
        CommandStatus.TIMEOUT: "status.failed",
    }.get(command.status, "muted")

    status_text = Text()
    status_text.append(f"Status: {command.status.value}", style=status_style)
    if command.exit_code is not None:
        status_text.append(f" (exit: {command.exit_code})", style="muted")
    content.append(status_text)

    # Output
    if show_output and command.stdout:
        content.append(Text())
        content.append(Text(command.stdout[:2000], style="command.output"))
        if len(command.stdout) > 2000:
            content.append(Text("... (truncated)", style="muted"))

    if show_output and command.stderr:
        content.append(Text())
        content.append(Text(command.stderr[:1000], style="error"))

    title = f"[panel.title]Command: {command.id[:8]}[/panel.title]"
    if command.description:
        title = f"[panel.title]{command.description}[/panel.title]"

    return Panel(
        Group(*content),
        title=title,
        border_style="panel.border",
        padding=(0, 1),
    )


def create_finding_panel(finding: Finding) -> Panel:
    """Create a panel displaying a finding."""
    content = []

    # Severity badge
    severity_style = {
        Severity.CRITICAL: "severity.critical",
        Severity.HIGH: "severity.high",
        Severity.MEDIUM: "severity.medium",
        Severity.LOW: "severity.low",
        Severity.INFO: "severity.info",
    }.get(finding.severity, "muted")

    header = Text()
    header.append(f"[{finding.severity.value.upper()}]", style=severity_style)
    if finding.cvss_score:
        header.append(f" CVSS: {finding.cvss_score}", style="muted")
    content.append(header)
    content.append(Text())

    # Description
    content.append(Text(finding.description, style="white"))

    # Impact
    if finding.impact:
        content.append(Text())
        content.append(Text("Impact:", style="subtitle"))
        content.append(Text(finding.impact, style="white"))

    # Remediation
    if finding.remediation:
        content.append(Text())
        content.append(Text("Remediation:", style="subtitle"))
        content.append(Text(finding.remediation, style="white"))

    return Panel(
        Group(*content),
        title=f"[panel.title]{finding.title}[/panel.title]",
        border_style="panel.border",
        padding=(0, 1),
    )


def create_scope_panel(scope: Scope) -> Panel:
    """Create a panel displaying the current scope."""
    if not scope.targets:
        return Panel(
            Text("No targets defined", style="muted"),
            title="[panel.title]Scope[/panel.title]",
            border_style="panel.border",
        )

    table = Table(show_header=True, header_style="table.header", border_style="muted")
    table.add_column("Type", style="info")
    table.add_column("Target", style="ip")
    table.add_column("Notes", style="muted")

    for target in scope.targets:
        table.add_row(target.target_type, target.value, target.notes or "-")

    content = [table]

    if scope.excluded:
        content.append(Text())
        content.append(Text("Excluded:", style="subtitle"))
        for ex in scope.excluded:
            content.append(Text(f"  • {ex}", style="muted"))

    return Panel(
        Group(*content),
        title="[panel.title]Scope[/panel.title]",
        border_style="panel.border",
        padding=(0, 1),
    )
