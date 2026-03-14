"""Docker executor for Kage — command execution inside Docker containers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from kage.executor.base import BaseExecutor, ExecutionResult, StreamingOutput
from kage.utils import utcnow

logger = logging.getLogger(__name__)


class DockerExecutor(BaseExecutor):
    """Execute commands inside a Docker container."""

    def __init__(
        self,
        container: str | None = None,
        image: str | None = None,
        working_dir: str | None = None,
        docker_cmd: str = "docker",
    ) -> None:
        """Initialize Docker executor.

        Args:
            container: Name or ID of a running container to exec into.
            image: Image name to run a new container from (one-shot).
            working_dir: Working directory inside the container.
            docker_cmd: Path to docker binary.
        """
        super().__init__(working_dir)
        self.container = container
        self.image = image
        self.docker_cmd = docker_cmd

        if not container and not image:
            raise ValueError("Either container or image must be specified")

    @property
    def environment_name(self) -> str:
        return f"docker:{self.container or self.image}"

    async def check_available(self) -> bool:
        """Check if Docker is available and the container/image is accessible."""
        try:
            process = await asyncio.create_subprocess_exec(
                self.docker_cmd,
                "info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(process.communicate(), timeout=10.0)
            if process.returncode != 0:
                return False

            # If using an existing container, check it's running
            if self.container:
                process = await asyncio.create_subprocess_exec(
                    self.docker_cmd,
                    "inspect",
                    "-f",
                    "{{.State.Running}}",
                    self.container,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10.0)
                return b"true" in stdout

            return True

        except Exception as e:
            logger.debug("Docker availability check failed: %s", e)
            return False

    def _build_exec_args(
        self,
        command: str,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> list[str]:
        """Build docker exec/run command arguments."""
        cwd = working_dir or self.working_dir

        if self.container:
            # Exec into running container
            args = [self.docker_cmd, "exec"]
            if cwd:
                args.extend(["-w", cwd])
            if env:
                for k, v in env.items():
                    args.extend(["-e", f"{k}={v}"])
            args.extend([self.container, "/bin/sh", "-c", command])
        else:
            # Run a new container from image
            args = [self.docker_cmd, "run", "--rm"]
            if cwd:
                args.extend(["-w", cwd])
            if env:
                for k, v in env.items():
                    args.extend(["-e", f"{k}={v}"])
            args.extend([self.image or "", "/bin/sh", "-c", command])

        return args

    async def execute(
        self,
        command: str,
        timeout: int = 300,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """Execute a command inside the Docker container."""
        started_at = utcnow()
        args = self._build_exec_args(command, working_dir, env)

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
            logger.error("Docker execute failed: %s", e)
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
        """Execute a command in Docker and stream output."""
        async def _stream() -> AsyncIterator[StreamingOutput]:
            args = self._build_exec_args(command, working_dir, env)

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
                    text=f"\n[Docker command timed out after {timeout}s]\n",
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
