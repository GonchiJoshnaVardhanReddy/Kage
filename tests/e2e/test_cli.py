"""End-to-end tests for Kage CLI."""

import pytest
import subprocess
import sys


class TestCLIBasics:
    """Basic CLI functionality tests."""

    def test_help_command(self):
        """Test --help works."""
        result = subprocess.run(
            [sys.executable, "-m", "kage", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "AI-powered penetration testing" in result.stdout

    def test_version_command(self):
        """Test --version works."""
        result = subprocess.run(
            [sys.executable, "-m", "kage", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Version" in result.stdout or "0." in result.stdout

    def test_report_help(self):
        """Test report command help."""
        result = subprocess.run(
            [sys.executable, "-m", "kage", "report", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "generate" in result.stdout.lower()
        assert "markdown" in result.stdout.lower()

    def test_session_help(self):
        """Test session command help."""
        result = subprocess.run(
            [sys.executable, "-m", "kage", "session", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "list" in result.stdout.lower()

    def test_plugin_help(self):
        """Test plugin command help."""
        result = subprocess.run(
            [sys.executable, "-m", "kage", "plugin", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "list" in result.stdout.lower()

    def test_config_help(self):
        """Test config command help."""
        result = subprocess.run(
            [sys.executable, "-m", "kage", "config", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0


class TestReportCommand:
    """Tests for report command."""

    def test_report_list_templates(self):
        """Test listing report templates."""
        result = subprocess.run(
            [sys.executable, "-m", "kage", "report", "list"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "owasp" in result.stdout.lower()

    def test_report_no_session(self):
        """Test report generation with no sessions gracefully handles error."""
        # This may fail if no sessions exist, but should handle gracefully
        result = subprocess.run(
            [sys.executable, "-m", "kage", "report", "generate", "-S", "nonexistent"],
            capture_output=True,
            text=True,
        )
        # Should exit with error code and show error message
        assert result.returncode != 0 or "not found" in result.stdout.lower()


class TestSessionCommand:
    """Tests for session command."""

    def test_session_list(self):
        """Test listing sessions."""
        result = subprocess.run(
            [sys.executable, "-m", "kage", "session", "list"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Should either show sessions table or "No sessions found"


class TestPluginCommand:
    """Tests for plugin command."""

    def test_plugin_list(self):
        """Test listing plugins."""
        result = subprocess.run(
            [sys.executable, "-m", "kage", "plugin", "list"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
