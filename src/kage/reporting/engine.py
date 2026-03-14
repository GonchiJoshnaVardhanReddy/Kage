"""Template rendering engine for Kage reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from jinja2 import Environment, FileSystemLoader, select_autoescape
from jinja2.loaders import BaseLoader

from kage.core.models import Session, Severity
from kage.reporting.findings import ReportData
from kage.third_party import load_weasyprint_html


def get_templates_dir() -> Path:
    """Get the templates directory path."""
    # Check user templates first
    user_templates = Path.home() / ".config" / "kage" / "templates"
    if user_templates.exists():
        return user_templates

    # Fall back to package templates
    package_root = Path(__file__).parent.parent.parent.parent
    return package_root / "templates"


def get_builtin_templates_dir() -> Path:
    """Get the built-in templates directory."""
    return Path(__file__).parent / "templates"


def create_jinja_env(templates_dir: Path | None = None) -> Environment:
    """Create a Jinja2 environment with custom filters."""
    dirs = []

    # Add custom templates dir if provided
    if templates_dir:
        dirs.append(str(templates_dir))

    # Add user templates
    user_templates = Path.home() / ".config" / "kage" / "templates"
    if user_templates.exists():
        dirs.append(str(user_templates))

    # Add package templates (root level)
    package_templates = get_templates_dir()
    if package_templates.exists():
        dirs.append(str(package_templates))

    # Add built-in templates
    builtin = get_builtin_templates_dir()
    if builtin.exists():
        dirs.append(str(builtin))

    env = Environment(
        loader=FileSystemLoader(dirs),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Add custom filters
    env.filters["severity_color"] = severity_color
    env.filters["severity_emoji"] = severity_emoji
    env.filters["severity_badge"] = severity_badge
    env.filters["truncate_output"] = truncate_output
    env.filters["format_datetime"] = format_datetime
    env.filters["escape_markdown"] = escape_markdown

    return env


def severity_color(severity: Severity | str) -> str:
    """Get CSS color for severity level."""
    if isinstance(severity, Severity):
        severity = severity.value

    colors = {
        "critical": "#dc3545",
        "high": "#fd7e14",
        "medium": "#ffc107",
        "low": "#17a2b8",
        "info": "#6c757d",
    }
    return colors.get(severity, "#6c757d")


def severity_emoji(severity: Severity | str) -> str:
    """Get emoji for severity level."""
    if isinstance(severity, Severity):
        severity = severity.value

    emojis = {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🔵",
        "info": "⚪",
    }
    return emojis.get(severity, "⚪")


def severity_badge(severity: Severity | str) -> str:
    """Get HTML badge for severity level."""
    if isinstance(severity, Severity):
        severity = severity.value

    color = severity_color(severity)
    return f'<span class="severity-badge severity-{severity}" style="background-color: {color};">{severity.upper()}</span>'


def truncate_output(text: str | None, max_length: int = 500) -> str:
    """Truncate long output text."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "\n... (truncated)"


def format_datetime(dt: Any, fmt: str = "%Y-%m-%d %H:%M:%S UTC") -> str:
    """Format datetime object."""
    if dt is None:
        return ""
    if hasattr(dt, "strftime"):
        return cast(str, dt.strftime(fmt))
    return str(dt)


def escape_markdown(text: str) -> str:
    """Escape special Markdown characters."""
    if not text:
        return ""
    chars = ["\\", "`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", ".", "!"]
    for char in chars:
        text = text.replace(char, "\\" + char)
    return text


class ReportEngine:
    """Report rendering engine."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        self.env = create_jinja_env(templates_dir)

    def render_markdown(
        self,
        session: Session,
        template_name: str = "owasp/report.md.j2",
    ) -> str:
        """Render a Markdown report."""
        data = ReportData(session)
        template = self.env.get_template(template_name)
        return template.render(**data.to_context())

    def render_html(
        self,
        session: Session,
        template_name: str = "owasp/report.html.j2",
    ) -> str:
        """Render an HTML report."""
        data = ReportData(session)
        template = self.env.get_template(template_name)
        return template.render(**data.to_context())

    def list_templates(self) -> list[str]:
        """List available report templates."""
        templates = []
        loader: BaseLoader | None = self.env.loader
        if not isinstance(loader, FileSystemLoader):
            return []
        for loader_path in loader.searchpath:
            path = Path(loader_path)
            for template_file in path.rglob("*.j2"):
                rel_path = template_file.relative_to(path)
                templates.append(str(rel_path).replace("\\", "/"))
        return sorted(set(templates))

    def get_available_formats(self) -> list[str]:
        """Get available output formats."""
        return ["markdown", "html", "pdf"]

    def render_pdf(
        self,
        session: Session,
        output_path: str,
        template_name: str = "owasp/report.html.j2",
    ) -> str:
        """Render report as PDF. Requires weasyprint: pip install kage[pdf]"""
        html_content = self.render_html(session, template_name)
        try:
            HTML = load_weasyprint_html()

            HTML(string=html_content).write_pdf(output_path)
            return output_path
        except ImportError as e:
            raise RuntimeError(
                "PDF export requires WeasyPrint. Install with: pip install kage[pdf]"
            ) from e
