"""Slash-command palette and fuzzy command matching."""

from __future__ import annotations

import builtins
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SlashCommand:
    """One slash-command entry for palette rendering and lookup."""

    command: str
    description: str


DEFAULT_SLASH_COMMANDS: tuple[SlashCommand, ...] = (
    SlashCommand(command="/run workflow", description="Run a named workflow template"),
    SlashCommand(command="/tools list", description="List registered tools"),
    SlashCommand(command="/workflows list", description="List available workflows"),
    SlashCommand(command="/memory inspect", description="Inspect compacted memory blocks"),
    SlashCommand(command="/trace last", description="Show latest trace diagnostics"),
    SlashCommand(command="/prompt inspect", description="Inspect prompt layer diagnostics"),
    SlashCommand(command="/plugins list", description="List loaded plugins"),
    SlashCommand(command="/status", description="Show session and model status"),
)


def _subsequence_score(query: str, candidate: str) -> int:
    """Score candidate where lower is better; -1 means no fuzzy match."""
    if not query:
        return 0
    q = query.lower()
    c = candidate.lower()
    idx = 0
    score = 0
    for char in q:
        found = c.find(char, idx)
        if found == -1:
            return -1
        score += found - idx
        idx = found + 1
    score += max(0, len(c) - len(q))
    return score


class SlashCommandPalette:
    """In-memory slash-command palette with deterministic fuzzy filtering."""

    def __init__(self, commands: builtins.list[SlashCommand] | None = None) -> None:
        self._commands = list(commands or DEFAULT_SLASH_COMMANDS)

    def register(self, command: SlashCommand) -> None:
        """Register a command if not already present."""
        if all(item.command != command.command for item in self._commands):
            self._commands.append(command)

    def list(self) -> builtins.list[SlashCommand]:
        """List commands in deterministic order."""
        return list(self._commands)

    def search(self, query: str, *, limit: int = 8) -> builtins.list[SlashCommand]:
        """Fuzzy-search slash commands by subsequence and prefix signals."""
        normalized = query.strip().lower()
        if not normalized:
            return self.list()[:limit]

        scored: builtins.list[tuple[int, int, SlashCommand]] = []
        for order, command in enumerate(self._commands):
            text = f"{command.command} {command.description}"
            if normalized in text.lower():
                scored.append((0, order, command))
                continue
            fuzzy = _subsequence_score(normalized, text)
            if fuzzy >= 0:
                scored.append((fuzzy + 10, order, command))

        scored.sort(key=lambda item: (item[0], item[1], item[2].command))
        return [item[2] for item in scored[:limit]]

