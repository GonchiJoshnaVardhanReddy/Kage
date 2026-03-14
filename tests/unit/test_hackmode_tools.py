"""Tests for hack mode tool wrappers and memory updates."""

from __future__ import annotations

from rich.console import Console

from kage.core.hackmode import HackModeEngine
from kage.persistence.config import KageConfig


def _engine() -> HackModeEngine:
    return HackModeEngine(console=Console(), config=KageConfig(), target="example.com")


def test_planner_tool_builds_recon_chain() -> None:
    engine = _engine()
    plan = engine.planner_tool("example.com", "scan example.com")
    assert any(cmd.startswith("nmap") for cmd in plan)
    assert any(cmd.startswith("gobuster") for cmd in plan)
    assert any(cmd.startswith("nikto") for cmd in plan)
    assert any(cmd.startswith("sqlmap") for cmd in plan)


def test_memory_tool_set_get_roundtrip() -> None:
    engine = _engine()
    engine.memory_tool("set", "open_ports", [80, 443])
    assert engine.memory_tool("get", "open_ports") == [80, 443]
