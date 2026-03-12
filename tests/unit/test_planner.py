"""Tests for execution planning engine."""

from kage.core.models import Command, CommandStatus
from kage.core.planner import ExecutionPlan, PlanStatus


def _make_cmd(command: str, desc: str | None = None) -> Command:
    return Command(command=command, description=desc)


class TestExecutionPlan:
    """Test the ExecutionPlan model."""

    def test_from_commands(self):
        cmds = [_make_cmd("nmap 10.0.0.1"), _make_cmd("gobuster dir -u http://10.0.0.1")]
        plan = ExecutionPlan.from_commands(cmds)
        assert plan.total_steps == 2
        assert plan.steps[0].index == 1
        assert plan.steps[1].index == 2

    def test_current_step(self):
        plan = ExecutionPlan.from_commands([_make_cmd("cmd1"), _make_cmd("cmd2")])
        assert plan.current_step is not None
        assert plan.current_step.index == 1

    def test_pending_steps(self):
        plan = ExecutionPlan.from_commands([_make_cmd("a"), _make_cmd("b"), _make_cmd("c")])
        assert len(plan.pending_steps) == 3

    def test_mark_step_running(self):
        plan = ExecutionPlan.from_commands([_make_cmd("cmd")])
        plan.mark_step_running(1)
        assert plan.steps[0].status == CommandStatus.RUNNING

    def test_mark_step_completed(self):
        plan = ExecutionPlan.from_commands([_make_cmd("cmd")])
        plan.mark_step_running(1)
        plan.mark_step_completed(1, exit_code=0)
        assert plan.steps[0].status == CommandStatus.COMPLETED
        assert plan.completed_steps == 1

    def test_mark_step_failed(self):
        plan = ExecutionPlan.from_commands([_make_cmd("cmd")])
        plan.mark_step_failed(1, error="timeout")
        assert plan.steps[0].status == CommandStatus.FAILED

    def test_mark_step_skipped(self):
        plan = ExecutionPlan.from_commands([_make_cmd("a"), _make_cmd("b")])
        plan.mark_step_skipped(1)
        assert plan.steps[0].skipped is True
        assert len(plan.pending_steps) == 1

    def test_remove_step(self):
        plan = ExecutionPlan.from_commands([_make_cmd("a"), _make_cmd("b"), _make_cmd("c")])
        removed = plan.remove_step(2)
        assert removed is True
        assert plan.total_steps == 2
        assert plan.steps[0].index == 1
        assert plan.steps[1].index == 2  # Re-indexed

    def test_remove_nonexistent_step(self):
        plan = ExecutionPlan.from_commands([_make_cmd("a")])
        assert plan.remove_step(99) is False

    def test_finalize_completed(self):
        plan = ExecutionPlan.from_commands([_make_cmd("a"), _make_cmd("b")])
        plan.mark_step_completed(1)
        plan.mark_step_completed(2)
        plan.finalize()
        assert plan.status == PlanStatus.COMPLETED

    def test_finalize_cancelled(self):
        plan = ExecutionPlan.from_commands([_make_cmd("a"), _make_cmd("b")])
        plan.mark_step_skipped(1)
        plan.mark_step_skipped(2)
        plan.finalize()
        assert plan.status == PlanStatus.CANCELLED

    def test_finalize_partial(self):
        plan = ExecutionPlan.from_commands([_make_cmd("a"), _make_cmd("b")])
        plan.mark_step_completed(1)
        plan.mark_step_failed(2, error="fail")
        plan.finalize()
        assert plan.status == PlanStatus.PARTIAL

    def test_description(self):
        plan = ExecutionPlan.from_commands(
            [_make_cmd("nmap 10.0.0.1")],
            description="Recon plan",
        )
        assert plan.description == "Recon plan"

    def test_step_display_label(self):
        plan = ExecutionPlan.from_commands([_make_cmd("nmap 10.0.0.1", desc="Port scan")])
        assert "Port scan" in plan.steps[0].display_label
