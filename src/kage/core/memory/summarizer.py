"""Transcript summarization interfaces and implementations."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .blocks import MemoryBlock, MemoryTimestampRange, timestamp_range_now

_ENTITY_PATTERN = re.compile(r"\b(?:\d{1,3}(?:\.\d{1,3}){3}|[a-zA-Z0-9._-]+\.[a-zA-Z]{2,})\b")
_ARTIFACT_PATTERN = re.compile(r"\b(?:artifact|result|report|scan|finding|port[_-]?scan)\b", re.IGNORECASE)


@dataclass(slots=True)
class TranscriptSegment:
    """Raw transcript segment for summarization."""

    text: str
    source_turn_ids: list[int]
    timestamp_range: MemoryTimestampRange | None = None


class MemorySummarizer:
    """Summarizer interface for transcript compaction."""

    def summarize(self, segment: TranscriptSegment) -> MemoryBlock:
        raise NotImplementedError


class RuleBasedMemorySummarizer(MemorySummarizer):
    """Deterministic fallback summarizer using lexical heuristics."""

    def summarize(self, segment: TranscriptSegment) -> MemoryBlock:
        lines = [line.strip() for line in segment.text.splitlines() if line.strip()]
        summary_body = " ".join(lines[:3])[:280]
        entities = sorted({match.group(0) for match in _ENTITY_PATTERN.finditer(segment.text)})[:12]
        artifacts = sorted({match.group(0).lower() for match in _ARTIFACT_PATTERN.finditer(segment.text)})[:8]
        if not summary_body:
            summary_body = "Compacted transcript segment"
        return MemoryBlock(
            summary=summary_body,
            entities=entities,
            artifacts=artifacts,
            confidence_score=0.62 if entities or artifacts else 0.45,
            source_turn_ids=list(segment.source_turn_ids),
            timestamp_range=segment.timestamp_range or timestamp_range_now(),
        )


class LLMMemorySummarizer(MemorySummarizer):
    """LLM-capable summarizer interface with rule-based fallback execution."""

    def __init__(self, fallback: MemorySummarizer | None = None) -> None:
        self._fallback = fallback or RuleBasedMemorySummarizer()

    def summarize(self, segment: TranscriptSegment) -> MemoryBlock:
        # Runtime currently defaults to deterministic behavior.
        # This class exists as the extension seam for provider-based summarization.
        return self._fallback.summarize(segment)

