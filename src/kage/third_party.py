"""Typed runtime adapters for optional or unstubbed third-party libraries."""

from __future__ import annotations

from collections.abc import AsyncIterator
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast


class AsyncTextFile(Protocol):
    """Protocol for async text file handles used by aiofiles."""

    async def __aenter__(self) -> AsyncTextFile: ...
    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool | None: ...
    def __aiter__(self) -> AsyncIterator[str]: ...
    async def read(self) -> str: ...
    async def write(self, data: str) -> int: ...


class AiofilesModule(Protocol):
    """Protocol for the aiofiles module subset used by Kage."""

    def open(
        self,
        file: str | Path,
        mode: str = "r",
        encoding: str | None = None,
    ) -> AsyncTextFile: ...


aiofiles = cast(AiofilesModule, import_module("aiofiles"))


class WeasyHTML(Protocol):
    """Protocol for weasyprint.HTML used for PDF export."""

    def __init__(self, string: str) -> None: ...

    def write_pdf(self, target: str | Path) -> None: ...


def load_weasyprint_html() -> type[WeasyHTML]:
    """Load weasyprint.HTML dynamically."""
    module = import_module("weasyprint")
    return cast(type[WeasyHTML], module.HTML)
