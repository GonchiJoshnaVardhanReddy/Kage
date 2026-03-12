"""Executor module for Kage."""

from kage.executor.base import BaseExecutor, ExecutionResult, StreamingOutput
from kage.executor.docker import DockerExecutor
from kage.executor.kali import KaliExecutor, KaliMCPError
from kage.executor.local import LocalExecutor, WindowsExecutor
from kage.executor.ssh import SSHExecutor
from kage.executor.wsl import WSLExecutor

__all__ = [
    "BaseExecutor",
    "DockerExecutor",
    "ExecutionResult",
    "KaliExecutor",
    "KaliMCPError",
    "LocalExecutor",
    "SSHExecutor",
    "StreamingOutput",
    "WindowsExecutor",
    "WSLExecutor",
]
