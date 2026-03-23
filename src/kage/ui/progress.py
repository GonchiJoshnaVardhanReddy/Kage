"""Workflow and parallel-agent progress rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

StepState = Literal["waiting", "running", "completed", "failed"]


@dataclass(slots=True)
class WorkflowStep:
    """One workflow/agent step in progress UI."""

    name: str
    state: StepState = "waiting"


@dataclass(slots=True)
class WorkflowProgress:
    """In-memory workflow progress tracker."""

    steps: list[WorkflowStep] = field(default_factory=list)

    def set_state(self, name: str, state: StepState) -> None:
        """Update one step state (or create it if absent)."""
        for step in self.steps:
            if step.name == name:
                step.state = state
                return
        self.steps.append(WorkflowStep(name=name, state=state))

    def render_lines(self) -> list[str]:
        """Render one line per step with visual state markers."""
        glyph = {
            "waiting": "…",
            "running": "▶",
            "completed": "✓",
            "failed": "✗",
        }
        return [f"{step.name:<16} {glyph[step.state]} {step.state}" for step in self.steps]


def pipeline_arrow_view(agent_names: list[str]) -> str:
    """Render compact arrow-based workflow topology."""
    return "\n→ ".join(agent_names)

