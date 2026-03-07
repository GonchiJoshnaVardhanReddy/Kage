"""Integration tests for reporting workflow."""

import tempfile
from pathlib import Path

import pytest

from kage.core.models import (
    Command,
    CommandStatus,
    Finding,
    Scope,
    Session,
    Severity,
    Target,
)
from kage.reporting import FindingStats, ReportEngine, ReportExporter


class TestReportingWorkflow:
    """Integration tests for complete reporting workflow."""

    @pytest.fixture
    def complete_session(self):
        """Create a complete session with all data types."""
        return Session(
            name="Integration Test Session",
            scope=Scope(
                targets=[
                    Target(value="192.168.1.0/24", target_type="cidr"),
                    Target(value="example.com", target_type="domain"),
                ],
                excluded=["192.168.1.1"],
            ),
            findings=[
                Finding(
                    title="SQL Injection in Login Form",
                    severity=Severity.CRITICAL,
                    description="The login form is vulnerable to SQL injection.",
                    impact="Complete database compromise.",
                    remediation="Use parameterized queries.",
                    cvss_score=9.8,
                    cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                    cwe_id="CWE-89",
                    target="https://example.com/login",
                    evidence=["' OR '1'='1' -- worked"],
                    verified=True,
                ),
                Finding(
                    title="Missing Security Headers",
                    severity=Severity.LOW,
                    description="Several security headers are missing.",
                    remediation="Add X-Frame-Options, CSP headers.",
                    target="https://example.com",
                ),
            ],
            commands=[
                Command(
                    command="nmap -sV 192.168.1.0/24",
                    status=CommandStatus.COMPLETED,
                    exit_code=0,
                    stdout="Nmap scan report...",
                ),
                Command(
                    command="sqlmap -u 'https://example.com/login'",
                    status=CommandStatus.COMPLETED,
                    exit_code=0,
                ),
            ],
        )

    @pytest.mark.asyncio
    async def test_full_markdown_export(self, complete_session):
        """Test complete markdown export workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.md"

            exporter = ReportExporter()
            result = await exporter.export(complete_session, output_path, "markdown")

            assert result.exists()
            content = result.read_text()

            # Check key sections
            assert "# Penetration Testing Report" in content
            assert "Integration Test Session" in content
            assert "SQL Injection" in content
            assert "CRITICAL" in content
            assert "192.168.1.0/24" in content
            assert "nmap" in content

    @pytest.mark.asyncio
    async def test_full_html_export(self, complete_session):
        """Test complete HTML export workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"

            exporter = ReportExporter()
            result = await exporter.export(complete_session, output_path, "html")

            assert result.exists()
            content = result.read_text(encoding="utf-8")

            # Check HTML structure
            assert "<!DOCTYPE html>" in content
            assert "<title>" in content
            assert "SQL Injection" in content
            assert "severity-critical" in content

    def test_stats_calculation(self, complete_session):
        """Test statistics calculation from session."""
        stats = FindingStats(complete_session.findings)

        assert stats.total == 2
        assert stats.critical == 1
        assert stats.low == 1
        assert stats.verified == 1
        assert stats.risk_rating == "CRITICAL"

    def test_engine_template_rendering(self, complete_session):
        """Test template rendering engine."""
        engine = ReportEngine()

        # Test both formats
        md = engine.render_markdown(complete_session)
        html = engine.render_html(complete_session)

        assert len(md) > 100
        assert len(html) > 100
        assert "SQL Injection" in md
        assert "SQL Injection" in html


class TestEmptySessionReport:
    """Tests for generating reports from empty sessions."""

    @pytest.fixture
    def empty_session(self):
        """Create an empty session."""
        return Session(name="Empty Test")

    @pytest.mark.asyncio
    async def test_empty_markdown_report(self, empty_session):
        """Test markdown report with no findings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "empty.md"

            exporter = ReportExporter()
            result = await exporter.export(empty_session, output_path, "markdown")

            assert result.exists()
            content = result.read_text()
            assert "No findings recorded" in content

    @pytest.mark.asyncio
    async def test_empty_html_report(self, empty_session):
        """Test HTML report with no findings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "empty.html"

            exporter = ReportExporter()
            result = await exporter.export(empty_session, output_path, "html")

            assert result.exists()
            content = result.read_text(encoding="utf-8")
            assert "No findings recorded" in content
