"""Executor module for Kage."""

from kage.executor.base import BaseExecutor, ExecutionResult, StreamingOutput
from kage.executor.local import LocalExecutor, WindowsExecutor

__all__ = [
    "BaseExecutor",
    "ExecutionResult",
    "LocalExecutor",
    "StreamingOutput",
    "WindowsExecutor",
]
