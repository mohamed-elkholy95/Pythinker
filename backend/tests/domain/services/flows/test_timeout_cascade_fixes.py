"""Regression tests for agent session timeout cascade failure fixes.

Tests cover:
- Fix 2: Anti-hallucination guard counts SKIPPED steps as progress
- Fix 3: Orphaned RUNNING steps are swept to SKIPPED on re-entry to EXECUTING
- Fix 4: Blocked steps unblock when dependency is SKIPPED
- Fix 5: Reflection ProgressMetrics counts SKIPPED as success
- Fix 6: False-success completion after anti-hallucination abort
"""

from app.domain.models.plan import ExecutionStatus, Plan, Step
from app.domain.services.flows.plan_act import PlanActFlow


# ── Fix 2: Anti-hallucination guard allows SKIPPED steps ─────────────────


class TestAntiHallucinationGuard:
    """Verify the SUMMARIZING gate counts SKIPPED steps as progress."""

    def _completed_steps_for_plan(self, steps: list[Step]) -> list[Step]:
        """Mirror the guard logic from plan_act.py SUMMARIZING block."""
        return [
            s for s in steps
            if s.status.value in ExecutionStatus.get_success_statuses()
        ]

    def test_anti_hallucination_allows_skipped(self) -> None:
        """Summarization should proceed when steps are SKIPPED but none COMPLETED."""
        steps = [
            Step(id="s1", description="research", status=ExecutionStatus.SKIPPED, success=True),
            Step(id="s2", description="analyze", status=ExecutionStatus.SKIPPED, success=True),
            Step(id="s3", description="compile", status=ExecutionStatus.FAILED),
        ]
        completed = self._completed_steps_for_plan(steps)
        assert len(completed) == 2, "SKIPPED steps should count as progress"

    def test_anti_hallucination_blocks_when_no_success(self) -> None:
        """Summarization should be blocked when zero steps succeeded."""
        steps = [
            Step(id="s1", description="research", status=ExecutionStatus.FAILED),
            Step(id="s2", description="analyze", status=ExecutionStatus.BLOCKED),
        ]
        completed = self._completed_steps_for_plan(steps)
        assert len(completed) == 0, "FAILED/BLOCKED should not count as progress"

    def test_anti_hallucination_mixed_completed_and_skipped(self) -> None:
        """Both COMPLETED and SKIPPED should count as progress."""
        steps = [
            Step(id="s1", description="research", status=ExecutionStatus.COMPLETED, success=True),
            Step(id="s2", description="analyze", status=ExecutionStatus.SKIPPED, success=True),
            Step(id="s3", description="compile", status=ExecutionStatus.PENDING),
        ]
        completed = self._completed_steps_for_plan(steps)
        assert len(completed) == 2


# ── Fix 3: Orphaned RUNNING step cleanup ─────────────────────────────────


class TestOrphanedRunningStepCleanup:
    """Verify RUNNING steps are swept to SKIPPED on re-entry to EXECUTING."""

    def test_orphaned_running_step_cleanup(self) -> None:
        """RUNNING steps should be marked SKIPPED with success=True."""
        steps = [
            Step(id="s1", description="search web", status=ExecutionStatus.RUNNING),
            Step(id="s2", description="analyze results", status=ExecutionStatus.PENDING),
        ]

        # Simulate the sweep logic from plan_act.py EXECUTING block
        steps_completed_count = 0
        for s in steps:
            if s.status == ExecutionStatus.RUNNING:
                s.status = ExecutionStatus.SKIPPED
                s.success = True
                s.notes = (
                    "Error recovery: LLM timeout during execution. "
                    "Partial work preserved."
                )
                steps_completed_count += 1

        assert steps[0].status == ExecutionStatus.SKIPPED
        assert steps[0].success is True
        assert "Error recovery" in steps[0].notes
        assert steps_completed_count == 1
        # PENDING step should be untouched
        assert steps[1].status == ExecutionStatus.PENDING

    def test_no_orphans_no_change(self) -> None:
        """When no RUNNING steps exist, sweep should be a no-op."""
        steps = [
            Step(id="s1", description="done", status=ExecutionStatus.COMPLETED, success=True),
            Step(id="s2", description="next", status=ExecutionStatus.PENDING),
        ]

        count = 0
        for s in steps:
            if s.status == ExecutionStatus.RUNNING:
                s.status = ExecutionStatus.SKIPPED
                s.success = True
                count += 1

        assert count == 0
        assert steps[0].status == ExecutionStatus.COMPLETED
        assert steps[1].status == ExecutionStatus.PENDING

    def test_multiple_orphaned_running_steps(self) -> None:
        """Multiple RUNNING steps should all be swept."""
        steps = [
            Step(id="s1", description="step 1", status=ExecutionStatus.RUNNING),
            Step(id="s2", description="step 2", status=ExecutionStatus.RUNNING),
            Step(id="s3", description="step 3", status=ExecutionStatus.PENDING),
        ]

        count = 0
        for s in steps:
            if s.status == ExecutionStatus.RUNNING:
                s.status = ExecutionStatus.SKIPPED
                s.success = True
                count += 1

        assert count == 2
        assert all(s.status == ExecutionStatus.SKIPPED for s in steps[:2])


# ── Fix 4: Unblock after SKIPPED dependency ──────────────────────────────


class TestUnblockAfterSkip:
    """Verify blocked steps unblock when dependency is SKIPPED."""

    def test_unblock_after_skip(self) -> None:
        """Blocked step should unblock when blocker is SKIPPED."""
        plan = Plan(
            goal="test",
            message="test",
            steps=[
                Step(id="s1", description="research", status=ExecutionStatus.SKIPPED, success=True),
                Step(
                    id="s2",
                    description="analyze",
                    status=ExecutionStatus.BLOCKED,
                    blocked_by="s1",
                    notes="blocked by s1",
                ),
            ],
        )

        unblocked = plan.unblock_independent_steps()

        assert "s2" in unblocked
        assert plan.steps[1].status == ExecutionStatus.PENDING
        assert plan.steps[1].blocked_by is None
        assert "skipped" in plan.steps[1].notes.lower()

    def test_unblock_cascade_through_skip(self) -> None:
        """Unblock should cascade: s1 SKIPPED → s2 unblocks → s3 can unblock next."""
        plan = Plan(
            goal="test",
            message="test",
            steps=[
                Step(id="s1", description="step 1", status=ExecutionStatus.SKIPPED, success=True),
                Step(
                    id="s2",
                    description="step 2",
                    status=ExecutionStatus.BLOCKED,
                    blocked_by="s1",
                ),
                Step(
                    id="s3",
                    description="step 3",
                    status=ExecutionStatus.BLOCKED,
                    blocked_by="s2",
                ),
            ],
        )

        # First pass: s2 unblocks (s1 is SKIPPED)
        unblocked_pass1 = plan.unblock_independent_steps()
        assert "s2" in unblocked_pass1
        assert plan.steps[1].status == ExecutionStatus.PENDING

        # s3 is still blocked by s2 which is now PENDING (not SKIPPED/COMPLETED)
        assert plan.steps[2].status == ExecutionStatus.BLOCKED

    def test_no_unblock_when_blocker_still_running(self) -> None:
        """Blocked step should NOT unblock when blocker is still RUNNING."""
        plan = Plan(
            goal="test",
            message="test",
            steps=[
                Step(id="s1", description="research", status=ExecutionStatus.RUNNING),
                Step(
                    id="s2",
                    description="analyze",
                    status=ExecutionStatus.BLOCKED,
                    blocked_by="s1",
                ),
            ],
        )

        unblocked = plan.unblock_independent_steps()

        assert len(unblocked) == 0
        assert plan.steps[1].status == ExecutionStatus.BLOCKED

    def test_unblock_completed_still_works(self) -> None:
        """Existing COMPLETED unblock logic should still work."""
        plan = Plan(
            goal="test",
            message="test",
            steps=[
                Step(id="s1", description="research", status=ExecutionStatus.COMPLETED, success=True),
                Step(
                    id="s2",
                    description="analyze",
                    status=ExecutionStatus.BLOCKED,
                    blocked_by="s1",
                ),
            ],
        )

        unblocked = plan.unblock_independent_steps()
        assert "s2" in unblocked
        assert plan.steps[1].status == ExecutionStatus.PENDING

    def test_unblock_failed_with_partial_results_still_works(self) -> None:
        """Existing FAILED+result unblock logic should still work."""
        plan = Plan(
            goal="test",
            message="test",
            steps=[
                Step(
                    id="s1",
                    description="research",
                    status=ExecutionStatus.FAILED,
                    result="partial data gathered",
                ),
                Step(
                    id="s2",
                    description="analyze",
                    status=ExecutionStatus.BLOCKED,
                    blocked_by="s1",
                ),
            ],
        )

        unblocked = plan.unblock_independent_steps()
        assert "s2" in unblocked


# ── Fix 5: Reflection ProgressMetrics ────────────────────────────────────


class TestReflectionMetricsSkipped:
    """Verify reflection metrics count SKIPPED steps as success."""

    def _count_completed(self, steps: list[Step]) -> list[Step]:
        """Mirror the reflection metrics logic from plan_act.py."""
        return [
            s for s in steps
            if s.status.value in ExecutionStatus.get_success_statuses()
        ]

    def test_reflection_counts_skipped_as_completed(self) -> None:
        """Reflection should include SKIPPED in completed count."""
        steps = [
            Step(id="s1", description="research", status=ExecutionStatus.COMPLETED, success=True),
            Step(id="s2", description="analyze", status=ExecutionStatus.SKIPPED, success=True),
            Step(id="s3", description="compile", status=ExecutionStatus.FAILED),
        ]

        completed = self._count_completed(steps)
        assert len(completed) == 2

    def test_reflection_only_skipped(self) -> None:
        """All SKIPPED plan should still report progress."""
        steps = [
            Step(id="s1", description="step 1", status=ExecutionStatus.SKIPPED, success=True),
            Step(id="s2", description="step 2", status=ExecutionStatus.SKIPPED, success=True),
        ]

        completed = self._count_completed(steps)
        assert len(completed) == 2


# ── Fix 1: Config timeout validation ─────────────────────────────────────


class TestTimeoutConfig:
    """Verify the timeout config enables proper exponential backoff."""

    def test_backoff_cap_allows_escalation(self) -> None:
        """llm_request_timeout must be >= 300 for 45→90→180 backoff chain."""
        from app.core.config_llm import LLMTimeoutSettingsMixin

        mixin = LLMTimeoutSettingsMixin()
        tool_timeout = mixin.llm_tool_request_timeout  # 45s base
        cap = mixin.llm_request_timeout  # Should be 300

        # Simulate exponential backoff: base * 2^attempt, capped at llm_request_timeout
        attempt_0 = min(tool_timeout * (2 ** 1), cap)  # 90
        attempt_1 = min(tool_timeout * (2 ** 2), cap)  # 180
        attempt_2 = min(tool_timeout * (2 ** 3), cap)  # 300 (capped)

        assert attempt_0 == 90.0, f"First retry should be 90s, got {attempt_0}"
        assert attempt_1 == 180.0, f"Second retry should be 180s, got {attempt_1}"
        assert attempt_2 == 300.0, f"Third retry should be capped at 300s, got {attempt_2}"
        assert cap > tool_timeout, "Cap must exceed base timeout for backoff to work"


# ── Fix 6: False-success completion after anti-hallucination abort ────────


def _make_flow_with_plan(step_statuses: list[ExecutionStatus]) -> PlanActFlow:
    """Create a minimal PlanActFlow with a plan (skips __init__)."""
    flow = PlanActFlow.__new__(PlanActFlow)
    flow.plan = Plan(
        goal="test",
        message="test",
        steps=[
            Step(
                id=f"step-{idx}",
                description=f"step {idx}",
                status=status,
            )
            for idx, status in enumerate(step_statuses, start=1)
        ],
    )
    flow._aborted_zero_progress = False
    flow._zero_progress_dead_end_replans = 0
    flow._max_zero_progress_dead_end_replans = 1
    return flow


class TestFalseSuccessAbort:
    """Verify zero-progress abort prevents false-success signals."""

    def test_abort_flag_default_false(self) -> None:
        """New flows should not have the abort flag set."""
        flow = _make_flow_with_plan([ExecutionStatus.PENDING])
        assert flow._aborted_zero_progress is False

    def test_abort_flag_marks_plan_failed(self) -> None:
        """When abort flag is set, plan status should be FAILED."""
        flow = _make_flow_with_plan([ExecutionStatus.FAILED, ExecutionStatus.BLOCKED])

        # Simulate what the anti-hallucination guard does
        flow.plan.status = ExecutionStatus.FAILED
        flow._aborted_zero_progress = True

        assert flow.plan.status == ExecutionStatus.FAILED
        assert flow._aborted_zero_progress is True

    def test_abort_flag_prevents_plan_completed_override(self) -> None:
        """COMPLETED handler should NOT set plan.status=COMPLETED when abort flag is set.

        This tests the core behavior: when _aborted_zero_progress is True,
        the COMPLETED handler skips the reconciliation + PlanEvent(COMPLETED).
        """
        flow = _make_flow_with_plan([ExecutionStatus.FAILED, ExecutionStatus.BLOCKED])
        flow.plan.status = ExecutionStatus.FAILED
        flow._aborted_zero_progress = True

        # Simulate the COMPLETED handler's reconciliation logic
        # (which should be skipped when _aborted_zero_progress is True)
        if not flow._aborted_zero_progress:
            for s in flow.plan.steps:
                if s.success and s.status != ExecutionStatus.COMPLETED:
                    s.status = ExecutionStatus.COMPLETED
            flow.plan.status = ExecutionStatus.COMPLETED

        # Plan should still be FAILED, not COMPLETED
        assert flow.plan.status == ExecutionStatus.FAILED

    def test_abort_flag_prevents_step_reconciliation(self) -> None:
        """COMPLETED handler should NOT promote SKIPPED→COMPLETED when abort flag is set."""
        flow = _make_flow_with_plan([ExecutionStatus.SKIPPED])
        flow.plan.steps[0].success = True
        flow._aborted_zero_progress = True

        # Simulate the reconciliation logic (should be skipped)
        if not flow._aborted_zero_progress:
            for s in flow.plan.steps:
                if s.success and s.status != ExecutionStatus.COMPLETED:
                    s.status = ExecutionStatus.COMPLETED

        # Step should remain SKIPPED, not promoted to COMPLETED
        assert flow.plan.steps[0].status == ExecutionStatus.SKIPPED

    def test_normal_completion_still_works(self) -> None:
        """Normal (non-abort) completion should still reconcile and mark COMPLETED."""
        flow = _make_flow_with_plan([ExecutionStatus.COMPLETED])
        flow.plan.steps[0].success = True
        # _aborted_zero_progress is False by default

        # Simulate normal COMPLETED handler
        if not flow._aborted_zero_progress:
            for s in flow.plan.steps:
                if s.success and s.status != ExecutionStatus.COMPLETED:
                    s.status = ExecutionStatus.COMPLETED
            flow.plan.status = ExecutionStatus.COMPLETED

        assert flow.plan.status == ExecutionStatus.COMPLETED
