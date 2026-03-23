"""Streaming response utilities for token-by-token rendering."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class StreamState:
    """Holds incremental stream chunks and metadata."""

    chunks: list[str] = field(default_factory=list)
    token_count: int = 0

    def append(self, token: str) -> None:
        """Append one streamed token chunk."""
        self.chunks.append(token)
        self.token_count += 1

    @property
    def text(self) -> str:
        """Return full streamed text."""
        return "".join(self.chunks)


def stream_lines(tokens: list[str], *, width: int = 100) -> list[str]:
    """Convert streamed token chunks into wrapped output lines."""
    if width <= 0:
        return ["".join(tokens)]

    lines: list[str] = []
    current = ""
    for token in tokens:
        if "\n" in token:
            parts = token.split("\n")
            current += parts[0]
            lines.append(current)
            for part in parts[1:-1]:
                lines.append(part)
            current = parts[-1]
            continue
        if len(current) + len(token) > width and current:
            lines.append(current)
            current = token
        else:
            current += token
    if current:
        lines.append(current)
    return lines

