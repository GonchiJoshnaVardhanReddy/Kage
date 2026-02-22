"""Rich UI themes for Kage."""

from rich.style import Style
from rich.theme import Theme

# Dark hacker theme - inspired by Kali Linux terminal
KAGE_THEME = Theme({
    # Base colors
    "info": Style(color="cyan"),
    "warning": Style(color="yellow"),
    "error": Style(color="red", bold=True),
    "success": Style(color="green"),
    "danger": Style(color="red"),

    # UI elements
    "title": Style(color="bright_cyan", bold=True),
    "subtitle": Style(color="cyan"),
    "header": Style(color="bright_white", bold=True),
    "muted": Style(color="bright_black"),
    "highlight": Style(color="bright_magenta"),

    # Prompt elements
    "prompt": Style(color="bright_green", bold=True),
    "prompt.arrow": Style(color="green"),
    "input": Style(color="white"),

    # AI/Assistant
    "assistant": Style(color="bright_cyan"),
    "assistant.thinking": Style(color="cyan", italic=True),
    "user": Style(color="bright_green"),
    "system": Style(color="yellow"),

    # Commands
    "command": Style(color="bright_yellow"),
    "command.approved": Style(color="green"),
    "command.rejected": Style(color="red"),
    "command.pending": Style(color="yellow"),
    "command.output": Style(color="white"),

    # Security
    "safe": Style(color="green"),
    "unsafe": Style(color="red", bold=True),
    "scope.in": Style(color="green"),
    "scope.out": Style(color="red"),

    # Severity levels
    "severity.critical": Style(color="bright_red", bold=True),
    "severity.high": Style(color="red"),
    "severity.medium": Style(color="yellow"),
    "severity.low": Style(color="cyan"),
    "severity.info": Style(color="blue"),

    # Status
    "status.running": Style(color="yellow"),
    "status.completed": Style(color="green"),
    "status.failed": Style(color="red"),
    "status.pending": Style(color="cyan"),

    # Code/Technical
    "code": Style(color="bright_white", bgcolor="grey19"),
    "path": Style(color="bright_blue", underline=True),
    "url": Style(color="bright_blue", underline=True),
    "ip": Style(color="bright_magenta"),
    "port": Style(color="bright_yellow"),

    # Panels
    "panel.border": Style(color="cyan"),
    "panel.title": Style(color="bright_cyan", bold=True),

    # Tables
    "table.header": Style(color="bright_cyan", bold=True),
    "table.row.odd": Style(color="white"),
    "table.row.even": Style(color="bright_white"),

    # Logo/Brand
    "brand": Style(color="bright_red", bold=True),
    "brand.accent": Style(color="bright_cyan"),
})


# ASCII art logo
KAGE_LOGO = """[brand]
██╗  ██╗ █████╗  ██████╗ ███████╗
██║ ██╔╝██╔══██╗██╔════╝ ██╔════╝
█████╔╝ ███████║██║  ███╗█████╗  
██╔═██╗ ██╔══██║██║   ██║██╔══╝  
██║  ██╗██║  ██║╚██████╔╝███████╗
╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝[/brand]
[brand.accent]AI-Powered Penetration Testing Assistant[/brand.accent]
"""

KAGE_LOGO_SMALL = "[brand]KAGE[/brand] [brand.accent]// Shadow Security[/brand.accent]"
