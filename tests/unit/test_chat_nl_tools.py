"""Tests for natural-language file tool dispatch in chat session."""

from __future__ import annotations

from rich.console import Console

from kage.cli.commands.chat import ChatSession
from kage.persistence.config import KageConfig


def _make_session() -> ChatSession:
    return ChatSession(console=Console(), config=KageConfig())


def test_extract_file_path_from_text() -> None:
    session = _make_session()
    assert session._extract_file_path_from_text("show server.py") == "server.py"
    assert session._extract_file_path_from_text('edit "src/app/main.py"') == "src/app/main.py"


async def test_nl_read_dispatch(monkeypatch) -> None:
    session = _make_session()
    called: list[str] = []

    def fake_read(path: str) -> None:
        called.append(path)

    monkeypatch.setattr(session, "_read_file", fake_read)
    handled = await session._handle_natural_language_file_request("show server.py")

    assert handled is True
    assert called == ["server.py"]


async def test_nl_list_dispatch(monkeypatch) -> None:
    session = _make_session()
    called: list[str] = []

    def fake_list(path: str) -> None:
        called.append(path)

    monkeypatch.setattr(session, "_list_directory", fake_list)
    handled = await session._handle_natural_language_file_request("list files in src")

    assert handled is True
    assert called == ["src"]


async def test_nl_create_dispatch(monkeypatch) -> None:
    session = _make_session()
    called: list[str] = []

    def fake_create(path: str) -> None:
        called.append(path)

    monkeypatch.setattr(session, "_create_file", fake_create)
    handled = await session._handle_natural_language_file_request("create app.py")

    assert handled is True
    assert called == ["app.py"]


async def test_nl_edit_dispatch(monkeypatch) -> None:
    session = _make_session()
    called: list[tuple[str, str]] = []

    async def fake_ai_edit(path: str, req: str) -> bool:
        called.append((path, req))
        return True

    monkeypatch.setattr(session, "_ai_edit_file", fake_ai_edit)
    handled = await session._handle_natural_language_file_request("add logging to server.py")

    assert handled is True
    assert called == [("server.py", "add logging to server.py")]
