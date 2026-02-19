"""Unit tests for core models."""

import pytest
from datetime import datetime

from kage.core.models import (
    Session,
    Finding,
    Severity,
    Command,
    CommandStatus,
    Message,
    MessageRole,
    Target,
    Scope,
    AuditEntry,
    PluginMetadata,
    PluginCapability,
)


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_values(self):
        """Test severity enum values."""
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"
        assert Severity.INFO.value == "info"


class TestFinding:
    """Tests for Finding model."""

    def test_finding_creation(self):
        """Test creating a finding."""
        finding = Finding(
            title="SQL Injection",
            severity=Severity.CRITICAL,
            description="A SQL injection vulnerability was found.",
            impact="Full database compromise possible.",
            remediation="Use parameterized queries.",
            cvss_score=9.8,
            cwe_id="CWE-89",
            target="https://example.com/api",
        )
        
        assert finding.title == "SQL Injection"
        assert finding.severity == Severity.CRITICAL
        assert finding.cvss_score == 9.8
        assert finding.id is not None
        assert finding.discovered_at is not None

    def test_finding_defaults(self):
        """Test finding default values."""
        finding = Finding(
            title="Test",
            severity=Severity.INFO,
            description="Test finding",
        )
        
        assert finding.verified is False
        assert finding.auto_detected is False
        assert finding.evidence == []
        assert finding.references == []

    def test_finding_with_evidence(self):
        """Test finding with evidence."""
        finding = Finding(
            title="XSS",
            severity=Severity.MEDIUM,
            description="Reflected XSS",
            evidence=[
                "Request: GET /search?q=<script>alert(1)</script>",
                "Response: <script>alert(1)</script>",
            ],
        )
        
        assert len(finding.evidence) == 2


class TestCommand:
    """Tests for Command model."""

    def test_command_creation(self):
        """Test creating a command."""
        cmd = Command(
            command="nmap -sV 192.168.1.1",
            description="Port scan target",
        )
        
        assert cmd.command == "nmap -sV 192.168.1.1"
        assert cmd.status == CommandStatus.PENDING
        assert cmd.timeout == 300
        assert cmd.id is not None

    def test_command_status_transitions(self):
        """Test command status values."""
        cmd = Command(command="test")
        
        cmd.status = CommandStatus.APPROVED
        assert cmd.status == CommandStatus.APPROVED
        
        cmd.status = CommandStatus.RUNNING
        cmd.started_at = datetime.utcnow()
        assert cmd.status == CommandStatus.RUNNING
        
        cmd.status = CommandStatus.COMPLETED
        cmd.completed_at = datetime.utcnow()
        cmd.exit_code = 0
        assert cmd.status == CommandStatus.COMPLETED


class TestSession:
    """Tests for Session model."""

    def test_session_creation(self):
        """Test creating a session."""
        session = Session(name="Test Pentest")
        
        assert session.name == "Test Pentest"
        assert session.id is not None
        assert session.safe_mode is True
        assert session.messages == []
        assert session.commands == []
        assert session.findings == []

    def test_session_with_scope(self):
        """Test session with scope."""
        scope = Scope(
            targets=[
                Target(value="10.0.0.0/24", target_type="cidr"),
                Target(value="example.com", target_type="domain"),
            ]
        )
        session = Session(name="Scoped Test", scope=scope)
        
        assert len(session.scope.targets) == 2

    def test_session_with_findings(self):
        """Test session with findings."""
        session = Session()
        session.findings.append(
            Finding(title="Test", severity=Severity.HIGH, description="...")
        )
        session.findings.append(
            Finding(title="Test2", severity=Severity.LOW, description="...")
        )
        
        assert len(session.findings) == 2


class TestAuditEntry:
    """Tests for AuditEntry model."""

    def test_audit_entry_hash(self):
        """Test audit entry hash computation."""
        entry = AuditEntry(
            session_id="test-session",
            action="command_executed",
            details={"command": "nmap"},
        )
        entry.finalize()
        
        assert entry.entry_hash is not None
        assert entry.verify() is True

    def test_audit_hash_chain(self):
        """Test audit entry hash chain."""
        entry1 = AuditEntry(
            session_id="test-session",
            action="session_started",
            details={},
        )
        entry1.finalize()
        
        entry2 = AuditEntry(
            session_id="test-session",
            action="command_executed",
            details={"command": "nmap"},
        )
        entry2.finalize(previous_hash=entry1.entry_hash)
        
        assert entry2.previous_hash == entry1.entry_hash
        assert entry2.verify() is True

    def test_audit_tamper_detection(self):
        """Test that tampering is detected."""
        entry = AuditEntry(
            session_id="test-session",
            action="command_executed",
            details={"command": "nmap"},
        )
        entry.finalize()
        
        # Tamper with the entry
        entry.details["command"] = "malicious"
        
        # Hash should no longer verify
        assert entry.verify() is False


class TestMessage:
    """Tests for Message model."""

    def test_message_creation(self):
        """Test creating a message."""
        msg = Message(
            role=MessageRole.USER,
            content="Scan the target for open ports",
        )
        
        assert msg.role == MessageRole.USER
        assert msg.content == "Scan the target for open ports"
        assert msg.id is not None
        assert msg.timestamp is not None

    def test_message_roles(self):
        """Test different message roles."""
        roles = [MessageRole.SYSTEM, MessageRole.USER, MessageRole.ASSISTANT, MessageRole.TOOL]
        
        for role in roles:
            msg = Message(role=role, content="test")
            assert msg.role == role


class TestPluginMetadata:
    """Tests for PluginMetadata model."""

    def test_plugin_metadata(self):
        """Test plugin metadata creation."""
        capability = PluginCapability(
            name="scan_ports",
            description="Scan ports on a target",
            parameters={"target": "string"},
            dangerous=False,
        )
        
        metadata = PluginMetadata(
            name="recon",
            version="1.0.0",
            description="Reconnaissance plugin",
            author="Test Author",
            capabilities=[capability],
            required_tools=["nmap"],
        )
        
        assert metadata.name == "recon"
        assert len(metadata.capabilities) == 1
        assert metadata.capabilities[0].name == "scan_ports"
