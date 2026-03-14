"""SSH executor for Kage — remote command execution over SSH."""

from __future__ import annotations

import asyncio
import logging
import shlex
from collections.abc import AsyncIterator

from kage.executor.base import BaseExecutor, ExecutionResult, StreamingOutput
from kage.utils import utcnow

logger = logging.getLogger(__name__)


class SSHExecutor(BaseExecutor):
    """Execute commands on a remote host via SSH."""

    def __init__(
        self,
        host: str,
        username: str | None = None,
        port: int = 22,
        key_file: str | None = None,
        password: str | None = None,
        working_dir: str | None = None,
    ) -> None:
        super().__init__(working_dir)
        self.host = host
        self.username = username
        self.port = port
        self.key_file = key_file
        self.password = password

    @property
    def environment_name(self) -> str:
        return f"ssh:{self.host}"

    def _build_ssh_args(self) -> list[str]:
        """Build the SSH command arguments."""
        args = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "BatchMode=yes",
            "-p",
            str(self.port),
        ]

        if self.key_file:
            args.extend(["-i", self.key_file])

        target = f"{self.username}@{self.host}" if self.username else self.host
        args.append(target)

        return args

    async def check_available(self) -> bool:
        """Check if SSH connection is possible."""
        try:
            args = self._build_ssh_args() + ["echo", "kage_ping"]
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10.0)
            return b"kage_ping" in stdout
        except Exception as e:
            logger.debug("SSH connection check failed: %s", e)
            return False

    async def execute(
        self,
        command: str,
        timeout: int = 300,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """Execute a command on the remote host via SSH."""
        started_at = utcnow()
        cwd = working_dir or self.working_dir

        # Build the remote command
        remote_cmd = command
        if cwd:
            remote_cmd = f"cd {shlex.quote(cwd)} && {command}"
        if env:
            env_prefix = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items())
            remote_cmd = f"{env_prefix} {remote_cmd}"

        ssh_args = self._build_ssh_args() + ["--", remote_cmd]

        timed_out = False
        exit_code = -1
        stdout = ""
        stderr = ""

        try:
            process = await asyncio.create_subprocess_exec(
                *ssh_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            exit_code = process.returncode or 0
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

        except asyncio.TimeoutError:
            timed_out = True
            if process:
                process.kill()

        except Exception as e:
            logger.error("SSH execute failed: %s", e)
            stderr = str(e)

        return ExecutionResult(
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            started_at=started_at,
            completed_at=utcnow(),
            timed_out=timed_out,
            environment=self.environment_name,
            working_dir=cwd,
        )

    def execute_streaming(
        self,
        command: str,
        timeout: int = 300,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> AsyncIterator[StreamingOutput]:
        """Execute a command via SSH and stream output."""
        async def _stream() -> AsyncIterator[StreamingOutput]:
            cwd = working_dir or self.working_dir

            remote_cmd = command
            if cwd:
                remote_cmd = f"cd {shlex.quote(cwd)} && {command}"
            if env:
                env_prefix = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items())
                remote_cmd = f"{env_prefix} {remote_cmd}"

            ssh_args = self._build_ssh_args() + ["--", remote_cmd]

            process = await asyncio.create_subprocess_exec(
                *ssh_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                if process.stdout:
                    async for line in self._read_lines(process.stdout, timeout=float(timeout)):
                        yield StreamingOutput(text=line, stream="stdout")

                await asyncio.wait_for(process.wait(), timeout=float(timeout))

            except asyncio.TimeoutError:
                process.kill()
                yield StreamingOutput(
                    text=f"\n[SSH command timed out after {timeout}s]\n",
                    stream="stderr",
                )

        return _stream()

    async def _read_lines(
        self, stream: asyncio.StreamReader, timeout: float | None = None
    ) -> AsyncIterator[str]:
        """Read lines from an async stream."""
        while True:
            if timeout is None:
                line = await stream.readline()
            else:
                line = await asyncio.wait_for(stream.readline(), timeout=timeout)
            if not line:
                break
            yield line.decode("utf-8", errors="replace")
