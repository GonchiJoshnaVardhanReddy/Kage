"""Unit tests for the reporting module."""

from datetime import datetime

from kage.core.models import (
    Command,
    CommandStatus,
    Finding,
    Scope,
    Session,
    Severity,
    Target,
)
from kage.reporting.engine import (
    ReportEngine,
    format_datetime,
    severity_color,
    severity_emoji,
    truncate_output,
)
from kage.reporting.findings import (
    FindingStats,
    ReportData,
    group_findings_by_severity,
    group_findings_by_target,
    sort_findings_by_severity,
)


class TestFindingStats:
    """Tests for FindingStats class."""

    def test_empty_findings(self):
        """Test stats with no findings."""
        stats = FindingStats([])
        assert stats.total == 0
        assert stats.critical == 0
        assert stats.high == 0
        assert stats.medium == 0
        assert stats.low == 0
        assert stats.info == 0
        assert stats.risk_rating == "INFORMATIONAL"
        assert stats.risk_score == 0

    def test_single_critical_finding(self):
        """Test stats with one critical finding."""
        finding = Finding(
            title="SQL Injection",
            severity=Severity.CRITICAL,
            description="A critical SQL injection vulnerability.",
        )
        stats = FindingStats([finding])
        assert stats.total == 1
        assert stats.critical == 1
        assert stats.risk_rating == "CRITICAL"
        assert stats.risk_score == 10  # Critical weight

    def test_mixed_severity_findings(self):
        """Test stats with multiple severity levels."""
        findings = [
            Finding(title="F1", severity=Severity.CRITICAL, description="..."),
            Finding(title="F2", severity=Severity.HIGH, description="..."),
            Finding(title="F3", severity=Severity.HIGH, description="..."),
            Finding(title="F4", severity=Severity.MEDIUM, description="..."),
            Finding(title="F5", severity=Severity.LOW, description="..."),
            Finding(title="F6", severity=Severity.INFO, description="..."),
        ]
        stats = FindingStats(findings)
        assert stats.total == 6
        assert stats.critical == 1
        assert stats.high == 2
        assert stats.medium == 1
        assert stats.low == 1
        assert stats.info == 1
        assert stats.risk_rating == "CRITICAL"
        # Score: 10 + 7*2 + 4 + 1 + 0 = 29
        assert stats.risk_score == 29

    def test_verified_findings(self):
        """Test verified vs unverified counts."""
        findings = [
            Finding(title="F1", severity=Severity.HIGH, description="...", verified=True),
            Finding(title="F2", severity=Severity.HIGH, description="...", verified=True),
            Finding(title="F3", severity=Severity.MEDIUM, description="...", verified=False),
        ]
        stats = FindingStats(findings)
        assert stats.verified == 2
        assert stats.unverified == 1

    def test_to_dict(self):
        """Test conversion to dictionary."""
        finding = Finding(
            title="XSS",
            severity=Severity.MEDIUM,
            description="Cross-site scripting",
        )
        stats = FindingStats([finding])
        data = stats.to_dict()

        assert data["total"] == 1
        assert data["by_severity"]["medium"] == 1
        assert data["risk_rating"] == "MEDIUM"


class TestSortAndGroupFunctions:
    """Tests for sorting and grouping functions."""

    def test_sort_findings_by_severity(self):
        """Test that findings are sorted critical-first."""
        findings = [
            Finding(title="Low", severity=Severity.LOW, description="..."),
            Finding(title="Critical", severity=Severity.CRITICAL, description="..."),
            Finding(title="Medium", severity=Severity.MEDIUM, description="..."),
        ]
        sorted_findings = sort_findings_by_severity(findings)

        assert sorted_findings[0].severity == Severity.CRITICAL
        assert sorted_findings[1].severity == Severity.MEDIUM
        assert sorted_findings[2].severity == Severity.LOW

    def test_group_findings_by_severity(self):
        """Test grouping findings by severity level."""
        findings = [
            Finding(title="H1", severity=Severity.HIGH, description="..."),
            Finding(title="H2", severity=Severity.HIGH, description="..."),
            Finding(title="L1", severity=Severity.LOW, description="..."),
        ]
        grouped = group_findings_by_severity(findings)

        assert len(grouped["high"]) == 2
        assert len(grouped["low"]) == 1
        assert len(grouped["critical"]) == 0

    def test_group_findings_by_target(self):
        """Test grouping findings by target."""
        findings = [
            Finding(title="F1", severity=Severity.HIGH, description="...", target="10.0.0.1"),
            Finding(title="F2", severity=Severity.HIGH, description="...", target="10.0.0.1"),
            Finding(title="F3", severity=Severity.MEDIUM, description="...", target="10.0.0.2"),
        ]
        grouped = group_findings_by_target(findings)

        assert len(grouped["10.0.0.1"]) == 2
        assert len(grouped["10.0.0.2"]) == 1


class TestReportData:
    """Tests for ReportData class."""

    def test_report_data_context(self):
        """Test that report data produces valid template context."""
        session = Session(
            name="Test Session",
            scope=Scope(
                targets=[
                    Target(value="192.168.1.0/24", target_type="cidr"),
                ]
            ),
            findings=[
                Finding(title="Test", severity=Severity.HIGH, description="A finding"),
            ],
            commands=[
                Command(command="nmap -sV target", status=CommandStatus.COMPLETED),
            ],
        )

        data = ReportData(session)
        context = data.to_context()

        assert context["session_name"] == "Test Session"
        assert len(context["findings"]) == 1
        assert len(context["commands"]) == 1
        assert context["stats"]["total"] == 1
        assert context["stats"]["risk_rating"] == "HIGH"


class TestTemplateFilters:
    """Tests for Jinja2 template filters."""

    def test_severity_color(self):
        """Test severity color mapping."""
        assert severity_color(Severity.CRITICAL) == "#dc3545"
        assert severity_color("high") == "#fd7e14"
        assert severity_color("unknown") == "#6c757d"

    def test_severity_emoji(self):
        """Test severity emoji mapping."""
        assert severity_emoji(Severity.CRITICAL) == "🔴"
        assert severity_emoji("high") == "🟠"
        assert severity_emoji("medium") == "🟡"
        assert severity_emoji("low") == "🔵"
        assert severity_emoji("info") == "⚪"

    def test_truncate_output(self):
        """Test output truncation."""
        short_text = "Short"
        assert truncate_output(short_text) == "Short"

        long_text = "A" * 1000
        truncated = truncate_output(long_text, max_length=100)
        assert len(truncated) < 150
        assert "truncated" in truncated

        assert truncate_output(None) == ""

    def test_format_datetime(self):
        """Test datetime formatting."""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        formatted = format_datetime(dt)
        assert "2024-01-15" in formatted
        assert "10:30:00" in formatted

        assert format_datetime(None) == ""


class TestReportEngine:
    """Tests for ReportEngine class."""

    def test_engine_initialization(self):
        """Test engine can be initialized."""
        engine = ReportEngine()
        assert engine.env is not None

    def test_list_templates(self):
        """Test listing available templates."""
        engine = ReportEngine()
        templates = engine.list_templates()

        # Should have at least the OWASP templates
        assert any("owasp" in t for t in templates)

    def test_render_markdown(self):
        """Test markdown rendering."""
        session = Session(
            name="Markdown Test",
            findings=[
                Finding(title="Test Finding", severity=Severity.MEDIUM, description="Test"),
            ],
        )

        engine = ReportEngine()
        markdown = engine.render_markdown(session)

        assert "# Penetration Testing Report" in markdown
        assert "Markdown Test" in markdown
        assert "Test Finding" in markdown

    def test_render_html(self):
        """Test HTML rendering."""
        session = Session(
            name="HTML Test",
            findings=[
                Finding(title="XSS Vulnerability", severity=Severity.HIGH, description="Test"),
            ],
        )

        engine = ReportEngine()
        html = engine.render_html(session)

        assert "<!DOCTYPE html>" in html
        assert "HTML Test" in html
        assert "XSS Vulnerability" in html

    def test_get_available_formats(self):
        """Test available formats list."""
        engine = ReportEngine()
        formats = engine.get_available_formats()

        assert "markdown" in formats
        assert "html" in formats
        assert "pdf" in formats
