"""Tests for security tool installation checks."""

from __future__ import annotations

from kage.security.tool_checker import (
    check_tool_installed,
    detect_installed_security_tools,
    get_install_suggestion,
)


def test_check_tool_installed_found(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr("kage.security.tool_checker.shutil.which", lambda _name: "/usr/bin/nmap")
    result = check_tool_installed("nmap")
    assert result["installed"] is True
    assert result["path"] == "/usr/bin/nmap"


def test_check_tool_installed_missing(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr("kage.security.tool_checker.shutil.which", lambda _name: None)
    result = check_tool_installed("sqlmap")
    assert result["installed"] is False
    assert result["path"] is None


def test_get_install_suggestion() -> None:
    assert get_install_suggestion("sqlmap") == "sudo apt install sqlmap"


def test_detect_installed_security_tools(monkeypatch) -> None:  # noqa: ANN001
    installed = {"nmap", "sqlmap"}

    def _fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in installed else None

    monkeypatch.setattr("kage.security.tool_checker.shutil.which", _fake_which)
    tools = detect_installed_security_tools(["nmap", "sqlmap", "hydra"])
    assert tools == ["nmap", "sqlmap"]
