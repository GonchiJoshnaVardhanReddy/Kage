"""Local shell executor for Kage."""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import AsyncIterator
from datetime import datetime

from kage.executor.base import BaseExecutor, ExecutionResult, StreamingOutput


class LocalExecutor(BaseExecutor):
    """Execute commands on the local shell."""

    def __init__(self, working_dir: str | None = None, shell: str | None = None) -> None:
        super().__init__(working_dir)
        self.shell = shell or self._detect_shell()

    @property
    def environment_name(self) -> str:
        return "local"

    def _detect_shell(self) -> str:
        """Detect the appropriate shell for the current OS."""
        if os.name == "nt":  # Windows
            return os.environ.get("COMSPEC", "cmd.exe")
        else:  # Unix-like
            return os.environ.get("SHELL", "/bin/bash")

    async def check_available(self) -> bool:
        """Local shell is always available."""
        return True

    async def execute(
        self,
        command: str,
        timeout: int = 300,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """Execute a command locally."""
        started_at = datetime.utcnow()
        cwd = working_dir or self.working_dir

        # Merge environment variables
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        timed_out = False
        exit_code = -1
        stdout = ""
        stderr = ""

        try:
            # Run in executor to not block
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=cwd,
                    env=run_env,
                ),
            )
            exit_code = result.returncode
            stdout = result.stdout
            stderr = result.stderr

        except subprocess.TimeoutExpired as e:
            timed_out = True
            stdout = e.stdout.decode() if e.stdout else ""
            stderr = e.stderr.decode() if e.stderr else ""

        except Exception as e:
            stderr = str(e)

        return ExecutionResult(
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            timed_out=timed_out,
            environment=self.environment_name,
            working_dir=cwd,
        )

    async def execute_streaming(
        self,
        command: str,
        timeout: int = 300,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> AsyncIterator[StreamingOutput]:
        """Execute a command and stream output."""
        cwd = working_dir or self.working_dir

        # Merge environment variables
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        # Use asyncio subprocess for streaming
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=run_env,
        )

        async def read_stream(stream, stream_name: str):
            """Read from a stream and yield chunks."""
            while True:
                line = await stream.readline()
                if not line:
                    break
                yield StreamingOutput(
                    text=line.decode("utf-8", errors="replace"),
                    stream=stream_name,
                )

        # Read both streams concurrently
        try:
            async with asyncio.timeout(timeout):
                # Yield from both streams as they come in
                for stream in [process.stdout, process.stderr]:
                    if stream:
                        stream_name = "stdout" if stream == process.stdout else "stderr"
                        async for line in self._read_lines(stream):
                            yield StreamingOutput(text=line, stream=stream_name)

                await process.wait()

        except asyncio.TimeoutError:
            process.kill()
            yield StreamingOutput(
                text=f"\n[Command timed out after {timeout}s]\n",
                stream="stderr",
            )

    async def _read_lines(self, stream) -> AsyncIterator[str]:
        """Read lines from an async stream."""
        while True:
            line = await stream.readline()
            if not line:
                break
            yield line.decode("utf-8", errors="replace")

    async def _collect_stream(self, stream, name: str) -> list[StreamingOutput]:
        """Collect all output from a stream."""
        outputs = []
        async for line in self._read_lines(stream):
            outputs.append(StreamingOutput(text=line, stream=name))
        return outputs


class WindowsExecutor(LocalExecutor):
    """Windows-specific executor with PowerShell support."""

    def __init__(
        self,
        working_dir: str | None = None,
        use_powershell: bool = True,
    ) -> None:
        super().__init__(working_dir)
        self.use_powershell = use_powershell

    @property
    def environment_name(self) -> str:
        return "windows"

    def _detect_shell(self) -> str:
        if self.use_powershell:
            return "powershell.exe"
        return "cmd.exe"

    async def execute(
        self,
        command: str,
        timeout: int = 300,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """Execute using PowerShell if configured."""
        if self.use_powershell:
            # Wrap command for PowerShell
            command = f'powershell.exe -NoProfile -Command "{command}"'

        return await super().execute(command, timeout, working_dir, env)
