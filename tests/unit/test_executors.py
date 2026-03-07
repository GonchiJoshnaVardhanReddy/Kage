"""Unit tests for executor classes."""

import pytest

from kage.executor.docker import DockerExecutor
from kage.executor.local import _DANGEROUS_ENV_VARS, LocalExecutor, WindowsExecutor, sanitize_env
from kage.executor.ssh import SSHExecutor
from kage.executor.wsl import WSLExecutor


class TestSanitizeEnv:
    """sanitize_env strips dangerous environment variables."""

    def test_removes_dangerous_vars(self):
        """All known dangerous vars are stripped."""
        env = dict.fromkeys(_DANGEROUS_ENV_VARS, "bad")
        env["PATH"] = "/usr/bin"
        env["HOME"] = "/home/user"
        result = sanitize_env(env)
        assert "PATH" in result
        assert "HOME" in result
        for var in _DANGEROUS_ENV_VARS:
            assert var not in result

    def test_preserves_safe_vars(self):
        """Non-dangerous vars are preserved."""
        env = {"PATH": "/usr/bin", "TERM": "xterm", "USER": "test"}
        result = sanitize_env(env)
        assert result == env

    def test_empty_env(self):
        """Empty dict returns empty dict."""
        assert sanitize_env({}) == {}

    def test_specific_dangerous_vars(self):
        """Spot-check specific dangerous variable names."""
        for var in ("LD_PRELOAD", "PYTHONPATH", "NODE_OPTIONS"):
            result = sanitize_env({var: "x", "SAFE": "y"})
            assert var not in result
            assert "SAFE" in result


class TestLocalExecutor:
    """LocalExecutor instantiation and properties."""

    def test_instantiation(self):
        """LocalExecutor can be created."""
        executor = LocalExecutor()
        assert executor.environment_name == "local"

    def test_working_dir(self):
        """Working dir is stored."""
        executor = LocalExecutor(working_dir="/tmp")
        assert executor.working_dir == "/tmp"

    async def test_check_available(self):
        """Local executor is always available."""
        executor = LocalExecutor()
        assert await executor.check_available() is True


class TestWindowsExecutor:
    """WindowsExecutor instantiation.

    Note: WindowsExecutor has a known init-order issue where
    _detect_shell() is called before use_powershell is set.
    We patch _detect_shell to isolate the rest of the class.
    """

    def test_instantiation(self):
        """WindowsExecutor can be created."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(WindowsExecutor, "_detect_shell", lambda self: "powershell.exe")
            executor = WindowsExecutor(use_powershell=True)
        assert executor.environment_name == "windows"

    def test_powershell_flag(self):
        """use_powershell flag is stored."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(WindowsExecutor, "_detect_shell", lambda self: "cmd.exe")
            executor = WindowsExecutor(use_powershell=False)
        assert executor.use_powershell is False


class TestSSHExecutor:
    """SSHExecutor instantiation and command building."""

    def test_instantiation(self):
        """SSHExecutor can be created with host."""
        executor = SSHExecutor(host="192.168.1.1")
        assert executor.environment_name == "ssh:192.168.1.1"

    def test_ssh_args_basic(self):
        """SSH args contain host."""
        executor = SSHExecutor(host="target.local", username="root", port=2222)
        args = executor._build_ssh_args()
        assert "ssh" in args
        assert "-p" in args
        assert "2222" in args
        assert "root@target.local" in args

    def test_ssh_args_with_key(self):
        """SSH args include key file when specified."""
        executor = SSHExecutor(host="target.local", key_file="/home/user/.ssh/id_rsa")
        args = executor._build_ssh_args()
        assert "-i" in args
        assert "/home/user/.ssh/id_rsa" in args

    def test_ssh_args_no_username(self):
        """SSH args use bare host when no username."""
        executor = SSHExecutor(host="target.local")
        args = executor._build_ssh_args()
        assert "target.local" in args
        assert not any("@" in a for a in args)


class TestDockerExecutor:
    """DockerExecutor instantiation and command building."""

    def test_instantiation_with_container(self):
        """DockerExecutor works with a container name."""
        executor = DockerExecutor(container="my-container")
        assert executor.environment_name == "docker:my-container"

    def test_instantiation_with_image(self):
        """DockerExecutor works with an image name."""
        executor = DockerExecutor(image="kalilinux/kali-rolling")
        assert executor.environment_name == "docker:kalilinux/kali-rolling"

    def test_instantiation_requires_container_or_image(self):
        """Must specify at least container or image."""
        with pytest.raises(ValueError, match="Either container or image"):
            DockerExecutor()

    def test_build_exec_args_container(self):
        """Exec args use 'docker exec' for running container."""
        executor = DockerExecutor(container="ctr1")
        args = executor._build_exec_args("whoami")
        assert args[0] == "docker"
        assert "exec" in args
        assert "ctr1" in args
        assert "whoami" in args

    def test_build_exec_args_image(self):
        """Exec args use 'docker run' for image."""
        executor = DockerExecutor(image="ubuntu:latest")
        args = executor._build_exec_args("id")
        assert "run" in args
        assert "--rm" in args
        assert "ubuntu:latest" in args

    def test_build_exec_args_with_env(self):
        """Env vars are passed with -e flag."""
        executor = DockerExecutor(container="ctr1")
        args = executor._build_exec_args("echo $FOO", env={"FOO": "bar"})
        assert "-e" in args
        assert "FOO=bar" in args

    def test_build_exec_args_with_working_dir(self):
        """Working dir is passed with -w flag."""
        executor = DockerExecutor(container="ctr1")
        args = executor._build_exec_args("ls", working_dir="/app")
        assert "-w" in args
        assert "/app" in args


class TestWSLExecutor:
    """WSLExecutor instantiation and command building."""

    def test_instantiation(self):
        """WSLExecutor can be created."""
        executor = WSLExecutor()
        assert executor.environment_name == "wsl:default"

    def test_instantiation_with_distribution(self):
        """WSLExecutor stores distribution name."""
        executor = WSLExecutor(distribution="kali-linux")
        assert executor.environment_name == "wsl:kali-linux"

    def test_build_wsl_args_default(self):
        """WSL args for default distribution."""
        executor = WSLExecutor()
        args = executor._build_wsl_args("uname -a")
        assert args[0] == "wsl.exe"
        assert "--" in args
        assert "/bin/bash" in args
        assert "-c" in args

    def test_build_wsl_args_with_distribution(self):
        """WSL args include -d for named distribution."""
        executor = WSLExecutor(distribution="Ubuntu")
        args = executor._build_wsl_args("id")
        assert "-d" in args
        assert "Ubuntu" in args

    def test_build_wsl_args_with_env(self):
        """Env vars are prefixed in the inner command."""
        executor = WSLExecutor()
        args = executor._build_wsl_args("echo $X", env={"X": "1"})
        inner = args[-1]  # last arg is the inner command string
        assert "X=1" in inner
