"""Tests for command routing engine."""

from kage.core.router import CommandRouter, ExecutorType


class TestCommandRouter:
    """Test command routing decisions."""

    def test_local_tool_routes_locally(self):
        router = CommandRouter()
        result = router.route("git status")
        assert result.executor_type == ExecutorType.LOCAL
        assert result.tool_name == "git"

    def test_python_routes_locally(self):
        router = CommandRouter()
        result = router.route("python app.py")
        assert result.executor_type == ExecutorType.LOCAL

    def test_security_tool_routes_locally(self):
        router = CommandRouter()
        result = router.route("nmap -sV 192.168.1.1")
        assert result.executor_type == ExecutorType.LOCAL
        assert result.tool_name == "nmap"
        assert "local" in result.reasoning.lower()

    def test_sudo_prefix_handled(self):
        router = CommandRouter()
        result = router.route("sudo nmap -sV 10.0.0.1")
        assert result.executor_type == ExecutorType.LOCAL
        assert result.tool_name == "nmap"

    def test_pipe_routes_by_first_command(self):
        router = CommandRouter()
        result = router.route("nmap 10.0.0.1 | grep open")
        assert result.executor_type == ExecutorType.LOCAL
        assert result.tool_name == "nmap"

    def test_unknown_tool_defaults_local(self):
        router = CommandRouter()
        result = router.route("sometool --flag")
        assert result.executor_type == ExecutorType.LOCAL

    def test_empty_command(self):
        router = CommandRouter()
        result = router.route("")
        assert result.executor_type == ExecutorType.LOCAL
