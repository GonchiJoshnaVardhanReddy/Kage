"""In-memory semantic memory block store with relevance indexing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .blocks import MemoryBlock

_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_.:-]+")
_MEMORY_PAYLOAD_KEY = "memory_blocks"
_RUNTIME_STORES: dict[str, MemoryStore] = {}


def _tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in _TOKEN_PATTERN.finditer(text)}


@dataclass(slots=True)
class MemoryStore:
    """Stores and indexes compacted memory blocks."""

    blocks: list[MemoryBlock] = field(default_factory=list)
    _entity_index: dict[str, list[str]] = field(default_factory=dict, init=False, repr=False)
    _block_index: dict[str, MemoryBlock] = field(default_factory=dict, init=False, repr=False)

    def add(self, block: MemoryBlock) -> None:
        """Add a block and update indexes."""
        if block.block_id in self._block_index:
            return
        self.blocks.append(block)
        self._block_index[block.block_id] = block
        for entity in block.entities:
            normalized = entity.strip().lower()
            if not normalized:
                continue
            bucket = self._entity_index.setdefault(normalized, [])
            if block.block_id not in bucket:
                bucket.append(block.block_id)

    def deduplicate(self) -> list[str]:
        """Remove redundant blocks using normalized block keys."""
        seen: dict[str, str] = {}
        deduped: list[MemoryBlock] = []
        removed_ids: list[str] = []
        for block in self.blocks:
            key = block.normalized_key()
            existing = seen.get(key)
            if existing is None:
                seen[key] = block.block_id
                deduped.append(block)
                continue
            kept = self._block_index[existing]
            if block.confidence_score > kept.confidence_score:
                removed_ids.append(existing)
                seen[key] = block.block_id
                deduped = [candidate for candidate in deduped if candidate.block_id != existing]
                deduped.append(block)
            else:
                removed_ids.append(block.block_id)
        self.blocks = deduped
        self._reindex()
        return removed_ids

    def search(self, query: str, *, limit: int = 5) -> list[MemoryBlock]:
        """Retrieve blocks ranked by lexical overlap and confidence."""
        query_tokens = _tokens(query)
        scored: list[tuple[float, MemoryBlock]] = []
        for block in self.blocks:
            text = " ".join([block.summary, *block.entities, *block.artifacts])
            overlap = len(query_tokens.intersection(_tokens(text)))
            if overlap == 0 and query_tokens:
                continue
            score = overlap + block.confidence_score
            scored.append((score, block))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [block for _, block in scored[:limit]]

    def recent(self, *, limit: int = 5) -> list[MemoryBlock]:
        """Return latest blocks by insertion order."""
        if limit <= 0:
            return []
        return list(self.blocks[-limit:])

    def by_entity(self, entity: str) -> list[MemoryBlock]:
        """Return blocks matching one entity key."""
        ids = self._entity_index.get(entity.strip().lower(), [])
        return [self._block_index[block_id] for block_id in ids if block_id in self._block_index]

    def to_payload(self) -> list[dict[str, object]]:
        """Serialize for session persistence."""
        return [block.to_payload() for block in self.blocks]

    @classmethod
    def from_payload(cls, payload: list[dict[str, object]]) -> MemoryStore:
        """Restore store from persistence payload."""
        from .blocks import MemoryBlock

        store = cls()
        for item in payload:
            if not isinstance(item, dict):
                continue
            store.add(MemoryBlock.from_payload(item))
        return store

    def _reindex(self) -> None:
        self._entity_index.clear()
        self._block_index.clear()
        for block in self.blocks:
            self._block_index[block.block_id] = block
            for entity in block.entities:
                normalized = entity.strip().lower()
                if not normalized:
                    continue
                bucket = self._entity_index.setdefault(normalized, [])
                if block.block_id not in bucket:
                    bucket.append(block.block_id)


def get_or_create_memory_store(session: Any) -> MemoryStore:
    """Resolve memory store from session metadata payload."""
    session_id = getattr(session, "id", None)
    if isinstance(session_id, str):
        existing = _RUNTIME_STORES.get(session_id)
        if existing is not None:
            return existing

    metadata = getattr(session, "metadata", None)
    if not isinstance(metadata, dict):
        return MemoryStore()
    payload = metadata.get(_MEMORY_PAYLOAD_KEY, [])
    store = MemoryStore.from_payload(payload) if isinstance(payload, list) else MemoryStore()
    if isinstance(session_id, str):
        _RUNTIME_STORES[session_id] = store
    return store


def persist_memory_store(session: Any, store: MemoryStore) -> None:
    """Persist memory blocks into session metadata."""
    session_id = getattr(session, "id", None)
    metadata = getattr(session, "metadata", None)
    if not isinstance(metadata, dict):
        return
    metadata[_MEMORY_PAYLOAD_KEY] = store.to_payload()
    if isinstance(session_id, str):
        _RUNTIME_STORES[session_id] = store

