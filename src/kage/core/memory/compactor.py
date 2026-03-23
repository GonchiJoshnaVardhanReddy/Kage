"""Memory compaction engine for long-session transcript summarization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kage.core.observability import recorder_for_session
from kage.utils import utcnow

from .blocks import MemoryBlock, MemoryTimestampRange
from .store import MemoryStore
from .summarizer import MemorySummarizer, RuleBasedMemorySummarizer, TranscriptSegment


@dataclass(slots=True)
class CompactionConfig:
    """Configurable compaction thresholds."""

    token_threshold: int = 1200
    min_transcript_turns: int = 4
    max_segment_chars: int = 2400


@dataclass(slots=True)
class MemoryCompactor:
    """Compacts raw transcript history into semantic memory blocks."""

    store: MemoryStore
    summarizer: MemorySummarizer
    config: CompactionConfig = field(default_factory=CompactionConfig)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)

    def should_compact(
        self,
        *,
        transcript_excerpts: list[str],
        trigger: str,
    ) -> bool:
        """Check whether compaction should run for current trigger."""
        if trigger in {"agent_pipeline_completed", "workflow_terminated"}:
            return len(transcript_excerpts) > 0
        token_count = self._estimate_tokens("\n".join(transcript_excerpts))
        return token_count >= self.config.token_threshold

    def compact(
        self,
        *,
        session: Any,
        workflow_memory: Any,
        transcript_excerpts: list[str],
        turn_id: int,
        trigger: str,
    ) -> list[MemoryBlock]:
        """Perform compaction and return newly created blocks."""
        recorder = recorder_for_session(session, component="memory_compactor")
        recorder.record(
            event_type="memory_compaction_triggered",
            turn_id=turn_id,
            payload={"trigger": trigger, "excerpt_count": len(transcript_excerpts)},
        )
        if not self.should_compact(transcript_excerpts=transcript_excerpts, trigger=trigger):
            return []

        segments = self._segment_transcript(transcript_excerpts, max_chars=self.config.max_segment_chars)
        created: list[MemoryBlock] = []
        for segment_index, text in enumerate(segments):
            source_turn_ids = list(range(max(1, turn_id - len(segments) + 1), turn_id + 1))
            segment = TranscriptSegment(
                text=text,
                source_turn_ids=source_turn_ids,
                timestamp_range=MemoryTimestampRange(start=utcnow(), end=utcnow()),
            )
            block = self.summarizer.summarize(segment)
            block.metadata.setdefault("segment_index", segment_index)
            block.metadata.setdefault("trigger", trigger)
            self.store.add(block)
            created.append(block)
            recorder.record(
                event_type="memory_block_created",
                turn_id=turn_id,
                payload={
                    "block_id": block.block_id,
                    "confidence_score": block.confidence_score,
                    "source_turn_ids": block.source_turn_ids,
                },
            )

        removed = self.store.deduplicate()
        for removed_id in removed:
            recorder.record(
                event_type="memory_block_deduplicated",
                turn_id=turn_id,
                payload={"block_id": removed_id},
            )

        self._trim_transcript_excerpts(workflow_memory, transcript_excerpts)
        return created

    @staticmethod
    def _segment_transcript(transcript_excerpts: list[str], *, max_chars: int) -> list[str]:
        combined = "\n".join(excerpt for excerpt in transcript_excerpts if excerpt.strip())
        if not combined:
            return []
        if len(combined) <= max_chars:
            return [combined]
        segments: list[str] = []
        cursor = 0
        while cursor < len(combined):
            chunk = combined[cursor : cursor + max_chars]
            if not chunk:
                break
            segments.append(chunk)
            cursor += max_chars
        return segments

    @staticmethod
    def _trim_transcript_excerpts(workflow_memory: Any, transcript_excerpts: list[str]) -> None:
        if hasattr(workflow_memory, "intermediate_outputs") and isinstance(
            workflow_memory.intermediate_outputs, list
        ) and len(workflow_memory.intermediate_outputs) > 5:
            workflow_memory.intermediate_outputs = workflow_memory.intermediate_outputs[-5:]
        if len(transcript_excerpts) > 5:
            del transcript_excerpts[:-5]


def default_compactor(store: MemoryStore | None = None) -> MemoryCompactor:
    """Factory for default rule-based memory compactor."""
    memory_store = store or MemoryStore()
    return MemoryCompactor(store=memory_store, summarizer=RuleBasedMemorySummarizer())

