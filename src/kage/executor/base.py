"""Base executor interface for Kage."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from kage.utils import utcnow


@dataclass
class ExecutionResult:
    """Result of a command execution."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    started_at: datetime
    completed_at: datetime
    timed_out: bool = False
    environment: str = "local"
    working_dir: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Check if command executed successfully."""
        return self.exit_code == 0 and not self.timed_out

    @property
    def duration(self) -> float:
        """Get execution duration in seconds."""
        return (self.completed_at - self.started_at).total_seconds()


@dataclass
class StreamingOutput:
    """A chunk of streaming output from command execution."""

    text: str
    stream: str  # "stdout" or "stderr"
    timestamp: datetime = field(default_factory=utcnow)


class BaseExecutor(ABC):
    """Abstract base class for command executors."""

    def __init__(self, working_dir: str | None = None) -> None:
        self.working_dir = working_dir

    @property
    @abstractmethod
    def environment_name(self) -> str:
        """Return the name of the execution environment."""
        ...

    @abstractmethod
    async def execute(
        self,
        command: str,
        timeout: int = 300,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """Execute a command and return the result."""
        ...

    @abstractmethod
    async def execute_streaming(
        self,
        command: str,
        timeout: int = 300,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> AsyncIterator[StreamingOutput]:
        """Execute a command and stream output."""
        ...

    @abstractmethod
    async def check_available(self) -> bool:
        """Check if this executor is available and properly configured."""
        ...

    async def execute_with_callback(
        self,
        command: str,
        on_stdout: callable | None = None,
        on_stderr: callable | None = None,
        timeout: int = 300,
        working_dir: str | None = None,
    ) -> ExecutionResult:
        """Execute with callbacks for streaming output."""
        stdout_parts = []
        stderr_parts = []
        started_at = utcnow()
        async for chunk in self.execute_streaming(command, timeout, working_dir):
            if chunk.stream == "stdout":
                stdout_parts.append(chunk.text)
                if on_stdout:
                    on_stdout(chunk.text)
            else:
                stderr_parts.append(chunk.text)
                if on_stderr:
                    on_stderr(chunk.text)

        # Note: This is a simplified version - actual exit code needs
        # to come from the streaming implementation
        return ExecutionResult(
            command=command,
            exit_code=0,  # Will be set properly by implementation
            stdout="".join(stdout_parts),
            stderr="".join(stderr_parts),
            started_at=started_at,
            completed_at=utcnow(),
            environment=self.environment_name,
            working_dir=working_dir or self.working_dir,
        )
