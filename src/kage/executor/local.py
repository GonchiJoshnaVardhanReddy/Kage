"""Local shell executor for Kage."""

from __future__ import annotations

import asyncio
import base64
import os
import subprocess
from collections.abc import AsyncIterator
from functools import partial

from kage.executor.base import BaseExecutor, ExecutionResult, StreamingOutput
from kage.utils import utcnow

# Environment variables that could be abused for injection/hijacking
_DANGEROUS_ENV_VARS = frozenset(
    {
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "NODE_OPTIONS",
        "PERL5LIB",
        "RUBYLIB",
    }
)


def sanitize_env(env: dict[str, str]) -> dict[str, str]:
    """Filter out environment variables that could be used for injection."""
    return {k: v for k, v in env.items() if k not in _DANGEROUS_ENV_VARS}


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
        started_at = utcnow()
        cwd = working_dir or self.working_dir

        # Merge environment variables
        run_env = os.environ.copy()
        if env:
            run_env.update(sanitize_env(env))

        timed_out = False
        exit_code = -1
        stdout = ""
        stderr = ""

        try:
            # Run in executor to not block
            # Use explicit shell invocation to avoid shell=True injection
            if os.name == "nt":
                cmd: str | list[str] = command
                use_shell = True
            else:
                cmd = [self.shell, "-c", command]
                use_shell = False

            loop = asyncio.get_running_loop()
            run_cmd = partial(
                subprocess.run,
                cmd,
                shell=use_shell,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=run_env,
            )
            result = await loop.run_in_executor(
                None,
                run_cmd,
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
        """Execute a command and stream output."""
        async def _stream() -> AsyncIterator[StreamingOutput]:
            cwd = working_dir or self.working_dir

            # Merge environment variables
            run_env = os.environ.copy()
            if env:
                run_env.update(sanitize_env(env))

            # Use explicit shell invocation to avoid shell=True injection
            if os.name == "nt":
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=run_env,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    self.shell,
                    "-c",
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=run_env,
                )

            # Read both streams concurrently
            try:
                # Yield from both streams as they come in
                for stream in [process.stdout, process.stderr]:
                    if stream:
                        stream_name = "stdout" if stream == process.stdout else "stderr"
                        async for line in self._read_lines(stream, timeout=float(timeout)):
                            yield StreamingOutput(text=line, stream=stream_name)

                await asyncio.wait_for(process.wait(), timeout=float(timeout))

            except asyncio.TimeoutError:
                process.kill()
                yield StreamingOutput(
                    text=f"\n[Command timed out after {timeout}s]\n",
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

    async def _collect_stream(
        self, stream: asyncio.StreamReader, name: str
    ) -> list[StreamingOutput]:
        """Collect all output from a stream."""
        outputs: list[StreamingOutput] = []
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
            # Use -EncodedCommand with base64 to prevent quote injection
            encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
            command = f"powershell.exe -NoProfile -EncodedCommand {encoded}"

        return await super().execute(command, timeout, working_dir, env)
