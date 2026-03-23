"""Semantic memory retrieval and ranking for prompt/agent consumers."""

from __future__ import annotations

from dataclasses import dataclass

from .blocks import MemoryBlock
from .store import MemoryStore


@dataclass(slots=True)
class MemoryRetriever:
    """Retrieves relevant memory blocks from a store."""

    store: MemoryStore

    def retrieve(self, query: str, *, limit: int = 5) -> list[MemoryBlock]:
        """Retrieve semantically relevant blocks with confidence-biased ranking."""
        return self.store.search(query, limit=limit)

    def retrieve_recent(self, *, limit: int = 5) -> list[MemoryBlock]:
        """Retrieve most recently added blocks."""
        return self.store.recent(limit=limit)

