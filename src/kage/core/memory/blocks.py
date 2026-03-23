"""Structured semantic memory block models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from kage.utils import utcnow


@dataclass(slots=True)
class MemoryTimestampRange:
    """Start/end timestamps represented in one semantic block."""

    start: datetime
    end: datetime


@dataclass(slots=True)
class MemoryBlock:
    """Compacted semantic memory block derived from transcript history."""

    summary: str
    entities: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    confidence_score: float = 0.5
    source_turn_ids: list[int] = field(default_factory=list)
    timestamp_range: MemoryTimestampRange | None = None
    block_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized_key(self) -> str:
        """Deterministic key for deduplication heuristics."""
        entity_key = ",".join(sorted({entity.strip().lower() for entity in self.entities if entity.strip()}))
        artifact_key = ",".join(
            sorted({artifact.strip().lower() for artifact in self.artifacts if artifact.strip()})
        )
        summary_key = " ".join(self.summary.strip().lower().split())
        return f"{summary_key}|{entity_key}|{artifact_key}"

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> MemoryBlock:
        """Construct one memory block from persistence payload."""
        timestamp_range = None
        timestamp_raw = payload.get("timestamp_range")
        if isinstance(timestamp_raw, dict):
            start = timestamp_raw.get("start")
            end = timestamp_raw.get("end")
            if isinstance(start, str) and isinstance(end, str):
                timestamp_range = MemoryTimestampRange(
                    start=datetime.fromisoformat(start),
                    end=datetime.fromisoformat(end),
                )
        entities_raw = payload.get("entities")
        entities = [str(entity) for entity in entities_raw] if isinstance(entities_raw, list) else []
        artifacts_raw = payload.get("artifacts")
        artifacts = [str(artifact) for artifact in artifacts_raw] if isinstance(artifacts_raw, list) else []
        confidence_raw = payload.get("confidence_score", 0.5)
        confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float, str)) else 0.5
        turn_ids_raw = payload.get("source_turn_ids")
        source_turn_ids = [int(turn_id) for turn_id in turn_ids_raw if isinstance(turn_id, int)] if isinstance(
            turn_ids_raw, list
        ) else []
        metadata_raw = payload.get("metadata", {})
        metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
        return cls(
            block_id=str(payload.get("block_id", "")) or str(uuid.uuid4()),
            summary=str(payload.get("summary", "")),
            entities=entities,
            artifacts=artifacts,
            confidence_score=confidence,
            source_turn_ids=source_turn_ids,
            timestamp_range=timestamp_range,
            metadata=metadata,
        )

    def to_payload(self) -> dict[str, object]:
        """Serialize one block for session persistence."""
        return {
            "block_id": self.block_id,
            "summary": self.summary,
            "entities": list(self.entities),
            "artifacts": list(self.artifacts),
            "confidence_score": self.confidence_score,
            "source_turn_ids": list(self.source_turn_ids),
            "timestamp_range": (
                {
                    "start": self.timestamp_range.start.isoformat(),
                    "end": self.timestamp_range.end.isoformat(),
                }
                if self.timestamp_range is not None
                else None
            ),
            "metadata": dict(self.metadata),
        }


def timestamp_range_now() -> MemoryTimestampRange:
    """Create a timestamp range anchored to the current instant."""
    now = utcnow()
    return MemoryTimestampRange(start=now, end=now)

