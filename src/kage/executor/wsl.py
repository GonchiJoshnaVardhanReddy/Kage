"""WSL executor for Kage — command execution via Windows Subsystem for Linux."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator

from kage.executor.base import BaseExecutor, ExecutionResult, StreamingOutput
from kage.utils import utcnow

logger = logging.getLogger(__name__)


class WSLExecutor(BaseExecutor):
    """Execute commands via WSL (Windows Subsystem for Linux)."""

    def __init__(
        self,
        distribution: str | None = None,
        working_dir: str | None = None,
        wsl_cmd: str = "wsl.exe",
    ) -> None:
        """Initialize WSL executor.

        Args:
            distribution: WSL distribution name (e.g., "Ubuntu", "kali-linux").
                          If None, uses the default distribution.
            working_dir: Working directory inside WSL.
            wsl_cmd: Path to wsl.exe binary.
        """
        super().__init__(working_dir)
        self.distribution = distribution
        self.wsl_cmd = wsl_cmd

    @property
    def environment_name(self) -> str:
        return f"wsl:{self.distribution or 'default'}"

    def _build_wsl_args(
        self,
        command: str,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> list[str]:
        """Build WSL command arguments."""
        args = [self.wsl_cmd]

        if self.distribution:
            args.extend(["-d", self.distribution])

        # Build the inner command with optional cd and env
        cwd = working_dir or self.working_dir
        inner_cmd = command
        if cwd:
            inner_cmd = f"cd {cwd} && {command}"
        if env:
            env_prefix = " ".join(f"{k}={v}" for k, v in env.items())
            inner_cmd = f"{env_prefix} {inner_cmd}"

        args.extend(["--", "/bin/bash", "-c", inner_cmd])

        return args

    async def check_available(self) -> bool:
        """Check if WSL is available."""
        if os.name != "nt":
            return False

        try:
            args = [self.wsl_cmd, "--status"]
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(process.communicate(), timeout=10.0)
            return process.returncode == 0
        except Exception as e:
            logger.debug("WSL availability check failed: %s", e)
            return False

    async def execute(
        self,
        command: str,
        timeout: int = 300,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """Execute a command via WSL."""
        started_at = utcnow()
        args = self._build_wsl_args(command, working_dir, env)

        timed_out = False
        exit_code = -1
        stdout = ""
        stderr = ""

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
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
            logger.error("WSL execute failed: %s", e)
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
            working_dir=working_dir or self.working_dir,
        )

    def execute_streaming(
        self,
        command: str,
        timeout: int = 300,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> AsyncIterator[StreamingOutput]:
        """Execute a command via WSL and stream output."""
        async def _stream() -> AsyncIterator[StreamingOutput]:
            args = self._build_wsl_args(command, working_dir, env)

            process = await asyncio.create_subprocess_exec(
                *args,
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
                    text=f"\n[WSL command timed out after {timeout}s]\n",
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
