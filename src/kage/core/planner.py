"""Execution planning engine for Kage.

Manages multi-step command plans with user approval,
editing, and step-by-step execution tracking.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from kage.core.models import Command, CommandStatus
from kage.utils import utcnow


class PlanStatus(str, Enum):
    """Overall plan status."""

    DRAFT = "draft"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"


class PlanStep(BaseModel):
    """A single step in an execution plan."""

    index: int
    command: Command
    status: CommandStatus = CommandStatus.PENDING
    skipped: bool = False

    @property
    def display_label(self) -> str:
        desc = self.command.description or self.command.command
        return f"Step {self.index}: {desc}"


class ExecutionPlan(BaseModel):
    """A multi-step execution plan."""

    steps: list[PlanStep] = Field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT
    description: str | None = None

    @classmethod
    def from_commands(cls, commands: list[Command], description: str | None = None) -> ExecutionPlan:
        """Create a plan from a list of pending commands."""
        steps = [
            PlanStep(index=i + 1, command=cmd)
            for i, cmd in enumerate(commands)
        ]
        return cls(steps=steps, description=description)

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(
            1 for s in self.steps
            if s.status in (CommandStatus.COMPLETED, CommandStatus.FAILED)
        )

    @property
    def pending_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == CommandStatus.PENDING and not s.skipped]

    @property
    def current_step(self) -> PlanStep | None:
        for step in self.steps:
            if step.status == CommandStatus.PENDING and not step.skipped:
                return step
        return None

    def remove_step(self, index: int) -> bool:
        """Remove a step by its 1-based index."""
        for step in self.steps:
            if step.index == index:
                self.steps.remove(step)
                self._reindex()
                return True
        return False

    def _reindex(self) -> None:
        """Re-number steps after removal."""
        for i, step in enumerate(self.steps):
            step.index = i + 1

    def mark_step_running(self, index: int) -> None:
        """Mark a step as running."""
        for step in self.steps:
            if step.index == index:
                step.status = CommandStatus.RUNNING
                step.command.status = CommandStatus.RUNNING
                step.command.started_at = utcnow()
                return

    def mark_step_completed(self, index: int, exit_code: int = 0) -> None:
        """Mark a step as completed."""
        for step in self.steps:
            if step.index == index:
                step.status = CommandStatus.COMPLETED
                step.command.status = CommandStatus.COMPLETED
                step.command.exit_code = exit_code
                step.command.completed_at = utcnow()
                return

    def mark_step_failed(self, index: int, error: str = "") -> None:
        """Mark a step as failed."""
        for step in self.steps:
            if step.index == index:
                step.status = CommandStatus.FAILED
                step.command.status = CommandStatus.FAILED
                step.command.stderr = error
                step.command.completed_at = utcnow()
                return

    def mark_step_skipped(self, index: int) -> None:
        """Skip a step."""
        for step in self.steps:
            if step.index == index:
                step.skipped = True
                step.status = CommandStatus.REJECTED
                return

    def finalize(self) -> None:
        """Finalize plan status based on step outcomes."""
        if all(s.skipped or s.status == CommandStatus.REJECTED for s in self.steps):
            self.status = PlanStatus.CANCELLED
        elif all(
            s.status in (CommandStatus.COMPLETED, CommandStatus.REJECTED) or s.skipped
            for s in self.steps
        ):
            if any(s.status == CommandStatus.FAILED for s in self.steps):
                self.status = PlanStatus.PARTIAL
            else:
                self.status = PlanStatus.COMPLETED
        elif any(
            s.status in (CommandStatus.COMPLETED, CommandStatus.FAILED)
            for s in self.steps
        ):
            self.status = PlanStatus.PARTIAL
