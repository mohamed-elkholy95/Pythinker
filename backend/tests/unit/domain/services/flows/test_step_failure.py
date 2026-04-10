"""Tests for StepFailureHandler."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.domain.services.flows.step_failure import StepFailureHandler


def _make_step(
    step_id: str = "s1",
    status: str = "pending",
    error: str | None = None,
    result: str | None = None,
    dependencies: list[str] | None = None,
    description: str = "Do something",
) -> MagicMock:
    step = MagicMock()
    step.id = step_id
    step.status = MagicMock()
    step.status.value = status
    # Make direct comparison work
    step.status.__eq__ = lambda self, other: self.value == (other.value if hasattr(other, "value") else other)
    step.error = error
    step.result = result
    step.dependencies = dependencies or []
    step.description = description
    step.artifacts = None
    return step


def _make_plan(steps: list[MagicMock]) -> MagicMock:
    plan = MagicMock()
    plan.steps = steps
    return plan


class TestHandleFailure:
    """Tests for StepFailureHandler.handle_failure."""

    def setup_method(self) -> None:
        self.handler = StepFailureHandler()

    def test_marks_blocked_cascade(self) -> None:
        step = _make_step(step_id="s1", error="LLM timeout")
        plan = _make_plan([step])
        plan.mark_blocked_cascade.return_value = ["s2", "s3"]
        plan.unblock_independent_steps.return_value = []

        blocked = self.handler.handle_failure(plan, step)

        plan.mark_blocked_cascade.assert_called_once()
        assert "s2" in blocked or "s3" in blocked

    def test_injects_placeholder_when_no_result(self) -> None:
        step = _make_step(step_id="s1", error="timeout", result=None)
        step.attachments = ["report.md"]
        plan = _make_plan([step])
        plan.mark_blocked_cascade.return_value = ["s2"]
        plan.unblock_independent_steps.return_value = []

        self.handler.handle_failure(plan, step)

        assert step.result is not None
        assert "[Step failed" in step.result

    def test_does_not_inject_when_result_exists(self) -> None:
        step = _make_step(step_id="s1", error="partial", result="Some partial data")
        plan = _make_plan([step])
        plan.mark_blocked_cascade.return_value = ["s2"]
        plan.unblock_independent_steps.return_value = []

        self.handler.handle_failure(plan, step)

        assert step.result == "Some partial data"

    def test_unblocked_removed_from_blocked_list(self) -> None:
        step = _make_step(step_id="s1", error="err", result=None)
        step.attachments = ["partial.md"]
        plan = _make_plan([step])
        plan.mark_blocked_cascade.return_value = ["s2", "s3"]
        plan.unblock_independent_steps.return_value = ["s2"]

        blocked = self.handler.handle_failure(plan, step)

        assert "s2" not in blocked
        assert "s3" in blocked

    def test_no_blocked_ids_skips_unblock(self) -> None:
        step = _make_step(step_id="s1", error="err")
        plan = _make_plan([step])
        plan.mark_blocked_cascade.return_value = []

        blocked = self.handler.handle_failure(plan, step)

        assert blocked == []
        plan.unblock_independent_steps.assert_not_called()

    def test_failed_step_without_actionable_output_stays_blocking(self) -> None:
        step = _make_step(step_id="s1", error="invalid json", result=None)
        plan = _make_plan([step])
        plan.mark_blocked_cascade.return_value = ["s2"]

        blocked = self.handler.handle_failure(plan, step)

        assert blocked == ["s2"]
        assert step.result is None
        plan.unblock_independent_steps.assert_not_called()

    def test_reason_truncated_to_200(self) -> None:
        long_error = "E" * 500
        step = _make_step(step_id="s1", error=long_error)
        plan = _make_plan([step])
        plan.mark_blocked_cascade.return_value = []

        self.handler.handle_failure(plan, step)

        call_args = plan.mark_blocked_cascade.call_args
        reason = call_args.kwargs.get("reason") or call_args[1].get("reason", "")
        assert len(reason) <= 200

    def test_includes_artifacts_in_placeholder(self) -> None:
        step = _make_step(step_id="s1", error="err", result=None)
        step.artifacts = ["report.md", "data.csv"]
        plan = _make_plan([step])
        plan.mark_blocked_cascade.return_value = ["s2"]
        plan.unblock_independent_steps.return_value = []

        self.handler.handle_failure(plan, step)

        assert "report.md" in step.result
        assert "data.csv" in step.result


class TestShouldSkipStep:
    """Tests for StepFailureHandler.should_skip_step."""

    def setup_method(self) -> None:
        self.handler = StepFailureHandler()

    def test_blocked_dependency_causes_skip(self) -> None:
        from app.domain.models.plan import ExecutionStatus

        dep = _make_step(step_id="dep1")
        dep.status = ExecutionStatus.BLOCKED
        step = _make_step(step_id="s1", dependencies=["dep1"])
        plan = _make_plan([dep, step])

        should_skip, reason = self.handler.should_skip_step(plan, step)

        assert should_skip is True
        assert "blocked" in reason.lower()

    def test_no_dependencies_no_skip(self) -> None:
        step = _make_step(step_id="s1", dependencies=[])
        plan = _make_plan([step])

        should_skip, reason = self.handler.should_skip_step(plan, step)

        assert should_skip is False
        assert reason == ""

    def test_optional_step_with_failed_dep_skipped(self) -> None:
        from app.domain.models.plan import ExecutionStatus

        dep = _make_step(step_id="dep1")
        dep.status = ExecutionStatus.FAILED
        step = _make_step(step_id="s1", dependencies=["dep1"], description="Optional: polish formatting")
        plan = _make_plan([dep, step])

        should_skip, reason = self.handler.should_skip_step(plan, step)

        assert should_skip is True
        assert "optional" in reason.lower()

    def test_non_optional_step_with_failed_dep_not_skipped(self) -> None:
        from app.domain.models.plan import ExecutionStatus

        dep = _make_step(step_id="dep1")
        dep.status = ExecutionStatus.FAILED
        step = _make_step(step_id="s1", dependencies=["dep1"], description="Compile results")
        plan = _make_plan([dep, step])

        should_skip, _reason = self.handler.should_skip_step(plan, step)

        assert should_skip is False

    def test_optional_patterns_detected(self) -> None:
        from app.domain.models.plan import ExecutionStatus

        dep = _make_step(step_id="dep1")
        dep.status = ExecutionStatus.FAILED
        plan = _make_plan([dep])

        for pattern in ["optional", "if needed", "if required", "alternatively"]:
            step = _make_step(step_id="s1", dependencies=["dep1"], description=f"Step: {pattern} do extra work")
            plan.steps = [dep, step]

            should_skip, _ = self.handler.should_skip_step(plan, step)
            assert should_skip is True, f"Pattern '{pattern}' not detected"


class TestCheckAndSkipSteps:
    """Tests for StepFailureHandler.check_and_skip_steps."""

    def setup_method(self) -> None:
        self.handler = StepFailureHandler()

    def test_skips_pending_steps_with_blocked_deps(self) -> None:
        from app.domain.models.plan import ExecutionStatus

        dep = _make_step(step_id="dep1")
        dep.status = ExecutionStatus.BLOCKED
        step1 = _make_step(step_id="s1", dependencies=["dep1"])
        step1.status = ExecutionStatus.PENDING
        step2 = _make_step(step_id="s2", dependencies=[])
        step2.status = ExecutionStatus.PENDING
        plan = _make_plan([dep, step1, step2])

        skipped = self.handler.check_and_skip_steps(plan)

        assert "s1" in skipped
        assert "s2" not in skipped

    def test_completed_steps_not_checked(self) -> None:
        from app.domain.models.plan import ExecutionStatus

        step = _make_step(step_id="s1")
        step.status = ExecutionStatus.COMPLETED
        plan = _make_plan([step])

        skipped = self.handler.check_and_skip_steps(plan)

        assert skipped == []
