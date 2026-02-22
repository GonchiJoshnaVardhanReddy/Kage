"""Report export functionality for Kage."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal

import aiofiles

from kage.core.models import Session
from kage.reporting.engine import ReportEngine

OutputFormat = Literal["markdown", "html", "pdf"]


class ReportExporter:
    """Export reports to various formats."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        self.engine = ReportEngine(templates_dir)

    async def export(
        self,
        session: Session,
        output_path: Path,
        format: OutputFormat = "markdown",
        template: str | None = None,
    ) -> Path:
        """Export a report to the specified format."""
        if format == "markdown":
            return await self.export_markdown(session, output_path, template)
        elif format == "html":
            return await self.export_html(session, output_path, template)
        elif format == "pdf":
            return await self.export_pdf(session, output_path, template)
        else:
            raise ValueError(f"Unsupported format: {format}")

    async def export_markdown(
        self,
        session: Session,
        output_path: Path,
        template: str | None = None,
    ) -> Path:
        """Export report as Markdown."""
        template_name = template or "owasp/report.md.j2"
        content = self.engine.render_markdown(session, template_name)

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
            await f.write(content)

        return output_path

    async def export_html(
        self,
        session: Session,
        output_path: Path,
        template: str | None = None,
    ) -> Path:
        """Export report as HTML."""
        template_name = template or "owasp/report.html.j2"
        content = self.engine.render_html(session, template_name)

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
            await f.write(content)

        return output_path

    async def export_pdf(
        self,
        session: Session,
        output_path: Path,
        template: str | None = None,
    ) -> Path:
        """Export report as PDF (requires weasyprint)."""
        try:
            from weasyprint import HTML
        except ImportError:
            raise RuntimeError(
                "PDF export requires weasyprint. "
                "Install with: pip install weasyprint"
            )

        # First render to HTML
        template_name = template or "owasp/report.html.j2"
        html_content = self.engine.render_html(session, template_name)

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to PDF using weasyprint
        html = HTML(string=html_content)
        html.write_pdf(output_path)

        return output_path

    def export_sync(
        self,
        session: Session,
        output_path: Path,
        format: OutputFormat = "markdown",
        template: str | None = None,
    ) -> Path:
        """Synchronous export wrapper."""
        return asyncio.run(self.export(session, output_path, format, template))


def get_default_filename(session: Session, format: OutputFormat) -> str:
    """Generate a default filename for a report."""
    session_short = session.id[:8]
    date_str = session.created_at.strftime("%Y%m%d")

    extensions = {
        "markdown": "md",
        "html": "html",
        "pdf": "pdf",
    }
    ext = extensions.get(format, "md")

    name = session.name or "pentest"
    # Sanitize name for filename
    name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)

    return f"report_{name}_{session_short}_{date_str}.{ext}"
