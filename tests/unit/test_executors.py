"""Unit tests for executor classes."""

import pytest

from kage.executor.docker import DockerExecutor
from kage.executor.local import _DANGEROUS_ENV_VARS, LocalExecutor, WindowsExecutor, sanitize_env
from kage.executor.ssh import SSHExecutor
from kage.executor.wsl import WSLExecutor


class TestSanitizeEnv:
    """sanitize_env strips dangerous environment variables."""

    def test_removes_dangerous_vars(self):
        env = dict.fromkeys(_DANGEROUS_ENV_VARS, "bad")
        env["PATH"] = "/usr/bin"
        env["HOME"] = "/home/user"
        result = sanitize_env(env)
        assert "PATH" in result
        assert "HOME" in result
        for var in _DANGEROUS_ENV_VARS:
            assert var not in result

    def test_preserves_safe_vars(self):
        env = {"PATH": "/usr/bin", "TERM": "xterm", "USER": "test"}
        result = sanitize_env(env)
        assert result == env


class TestLocalExecutor:
    def test_instantiation(self):
        executor = LocalExecutor()
        assert executor.environment_name == "local"

    async def test_check_available(self):
        executor = LocalExecutor()
        assert await executor.check_available() is True


class TestWindowsExecutor:
    def test_instantiation(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(WindowsExecutor, "_detect_shell", lambda _self: "powershell.exe")
            executor = WindowsExecutor(use_powershell=True)
        assert executor.environment_name == "windows"


class TestSSHExecutor:
    def test_instantiation(self):
        executor = SSHExecutor(host="192.168.1.1")
        assert executor.environment_name == "ssh:192.168.1.1"


class TestDockerExecutor:
    def test_instantiation_with_container(self):
        executor = DockerExecutor(container="my-container")
        assert executor.environment_name == "docker:my-container"


class TestWSLExecutor:
    def test_instantiation(self):
        executor = WSLExecutor()
        assert executor.environment_name == "wsl:default"
