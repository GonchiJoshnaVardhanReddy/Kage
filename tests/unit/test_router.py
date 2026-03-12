"""Tests for command routing engine."""

from kage.core.router import CommandRouter, ExecutorType


class TestCommandRouter:
    """Test command routing decisions."""

    def test_local_tool_routes_locally(self):
        router = CommandRouter(kali_available=True)
        result = router.route("git status")
        assert result.executor_type == ExecutorType.LOCAL
        assert result.tool_name == "git"

    def test_python_routes_locally(self):
        router = CommandRouter(kali_available=True)
        result = router.route("python app.py")
        assert result.executor_type == ExecutorType.LOCAL

    def test_pip_routes_locally(self):
        router = CommandRouter(kali_available=True)
        result = router.route("pip install flask")
        assert result.executor_type == ExecutorType.LOCAL

    def test_security_tool_routes_to_kali(self):
        router = CommandRouter(kali_available=True)
        result = router.route("nmap -sV 192.168.1.1")
        assert result.executor_type == ExecutorType.KALI_MCP
        assert result.tool_name == "nmap"
        assert result.fallback_to_local is True

    def test_sqlmap_routes_to_kali(self):
        router = CommandRouter(kali_available=True)
        result = router.route("sqlmap -u http://target.com --dbs")
        assert result.executor_type == ExecutorType.KALI_MCP

    def test_nikto_routes_to_kali(self):
        router = CommandRouter(kali_available=True)
        result = router.route("nikto -h http://target.com")
        assert result.executor_type == ExecutorType.KALI_MCP

    def test_security_tool_falls_back_when_kali_unavailable(self):
        router = CommandRouter(kali_available=False)
        result = router.route("nmap -sV 192.168.1.1")
        assert result.executor_type == ExecutorType.LOCAL
        assert "unavailable" in result.reasoning.lower()

    def test_sudo_prefix_handled(self):
        router = CommandRouter(kali_available=True)
        result = router.route("sudo nmap -sV 10.0.0.1")
        assert result.executor_type == ExecutorType.KALI_MCP
        assert result.tool_name == "nmap"

    def test_pipe_routes_by_first_command(self):
        router = CommandRouter(kali_available=True)
        result = router.route("nmap 10.0.0.1 | grep open")
        assert result.executor_type == ExecutorType.KALI_MCP
        assert result.tool_name == "nmap"

    def test_path_qualified_command(self):
        router = CommandRouter(kali_available=True)
        result = router.route("/usr/bin/nmap 10.0.0.1")
        assert result.executor_type == ExecutorType.KALI_MCP
        assert result.tool_name == "nmap"

    def test_unknown_tool_defaults_local(self):
        router = CommandRouter(kali_available=True)
        result = router.route("sometool --flag")
        assert result.executor_type == ExecutorType.LOCAL

    def test_empty_command(self):
        router = CommandRouter()
        result = router.route("")
        assert result.executor_type == ExecutorType.LOCAL

    def test_kali_available_property(self):
        router = CommandRouter(kali_available=False)
        assert router.kali_available is False
        router.kali_available = True
        assert router.kali_available is True

    def test_custom_security_tools(self):
        router = CommandRouter(
            kali_available=True,
            custom_security_tools={"mytool"},
        )
        result = router.route("mytool --scan target.com")
        assert result.executor_type == ExecutorType.KALI_MCP

    def test_env_var_prefix_stripped(self):
        router = CommandRouter(kali_available=True)
        result = router.route("PYTHONPATH=/tmp nmap 10.0.0.1")
        assert result.executor_type == ExecutorType.KALI_MCP

    def test_ls_routes_locally(self):
        router = CommandRouter(kali_available=True)
        result = router.route("ls -la /etc")
        assert result.executor_type == ExecutorType.LOCAL

    def test_docker_routes_locally(self):
        router = CommandRouter(kali_available=True)
        result = router.route("docker ps")
        assert result.executor_type == ExecutorType.LOCAL
