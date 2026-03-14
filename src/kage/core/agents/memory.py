"""Shared workflow memory for agent pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class WorkflowMemory:
    """Shared memory propagated across all agents in a pipeline."""

    findings: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    confidence_scores: dict[str, float] = field(default_factory=dict)
    intermediate_outputs: list[dict[str, Any]] = field(default_factory=list)

    def add_note(self, note: str) -> None:
        """Append a note entry to workflow memory."""
        cleaned = note.strip()
        if cleaned:
            self.notes.append(cleaned)

    def add_finding(self, finding: dict[str, Any]) -> None:
        """Append one structured finding."""
        self.findings.append(finding)

    def add_target(self, target: str) -> None:
        """Append one target entry."""
        cleaned = target.strip()
        if cleaned:
            self.targets.append(cleaned)

    def add_artifact(self, key: str, value: Any) -> None:
        """Store one artifact by key."""
        if key:
            self.artifacts[key] = value

    def set_confidence(self, key: str, score: float) -> None:
        """Set confidence score in the range [0.0, 1.0]."""
        if score < 0.0 or score > 1.0:
            raise ValueError("confidence score must be between 0.0 and 1.0")
        if key:
            self.confidence_scores[key] = score

    def add_intermediate_output(self, output: dict[str, Any]) -> None:
        """Append one intermediate output payload."""
        self.intermediate_outputs.append(output)

