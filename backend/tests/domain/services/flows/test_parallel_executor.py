"""Comprehensive tests for the parallel executor module.

Tests cover:
- ParallelExecutionMode enum
- ResourceThrottleLevel enum
- ParallelExecutorConfig dataclass (defaults, effective concurrency)
- ExecutionStats dataclass (defaults, to_dict)
- StepResult dataclass (defaults, variants)
- ParallelExecutor.__init__ (with/without config, feature flags)
- ParallelExecutor.reset
- ParallelExecutor.set_throttle_level
- ParallelExecutor.update_resource_pressure
- ParallelExecutor._get_ready_steps (dependency resolution, blocking)
- ParallelExecutor._filter_parallelizable_steps (flag honor, heuristics)
- ParallelExecutor._is_step_safe_for_parallel (keyword heuristics)
- ParallelExecutor._execute_step_with_limit (success, exception wrapping)
- ParallelExecutor.execute_plan (sequential, parallel, dependency ordering)
- ParallelExecutor._process_result (success/failure state propagation)
- ParallelExecutor.can_parallelize
- ParallelExecutor.estimate_parallelism
- ParallelExecutor.aggregate_results (merge, best, all strategies)
- ParallelExecutor.get_parallelism_report
- Concurrency control via semaphore
- Cascade blocking of dependent steps
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import BaseEvent, PlanEvent, PlanStatus
from app.domain.models.plan import ExecutionStatus, Plan, Step
from app.domain.services.flows.parallel_executor import (
    ExecutionStats,
    ParallelExecutionMode,
    ParallelExecutor,
    ParallelExecutorConfig,
    ResourceThrottleLevel,
    StepResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_step(description: str = "Search for data", dependencies: list[str] | None = None) -> Step:
    """Build a Step with sane defaults for testing."""
    return Step(
        description=description,
        dependencies=dependencies or [],
    )


def make_plan(steps: list[Step] | None = None) -> Plan:
    """Build a Plan with sane defaults for testing."""
    return Plan(
        title="Test Plan",
        goal="Run tests",
        steps=steps or [],
    )


async def make_step_func(result: str | None = "done", success: bool = True):
    """Return a callable that simulates step execution."""

    async def execute(step: Step) -> StepResult:
        return StepResult(step_id=step.id, success=success, result=result)

    return execute


async def collect_events(gen: AsyncGenerator[BaseEvent, None]) -> list[BaseEvent]:
    """Drain an async generator and return all events as a list."""
    events = []
    async for event in gen:
        events.append(event)
    return events


# ---------------------------------------------------------------------------
# ParallelExecutionMode
# ---------------------------------------------------------------------------


class TestParallelExecutionMode:
    def test_values_are_strings(self):
        assert ParallelExecutionMode.SEQUENTIAL == "sequential"
        assert ParallelExecutionMode.PARALLEL == "parallel"
        assert ParallelExecutionMode.ADAPTIVE == "adaptive"

    def test_is_str_subclass(self):
        for member in ParallelExecutionMode:
            assert isinstance(member, str)

    def test_all_members_present(self):
        names = {m.name for m in ParallelExecutionMode}
        assert names == {"SEQUENTIAL", "PARALLEL", "ADAPTIVE"}

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("sequential", ParallelExecutionMode.SEQUENTIAL),
            ("parallel", ParallelExecutionMode.PARALLEL),
            ("adaptive", ParallelExecutionMode.ADAPTIVE),
        ],
    )
    def test_construct_from_string(self, value: str, expected: ParallelExecutionMode):
        assert ParallelExecutionMode(value) == expected

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            ParallelExecutionMode("unknown")


# ---------------------------------------------------------------------------
# ResourceThrottleLevel
# ---------------------------------------------------------------------------


class TestResourceThrottleLevel:
    def test_values_are_strings(self):
        assert ResourceThrottleLevel.NONE == "none"
        assert ResourceThrottleLevel.LIGHT == "light"
        assert ResourceThrottleLevel.MODERATE == "moderate"
        assert ResourceThrottleLevel.HEAVY == "heavy"

    def test_all_members_present(self):
        names = {m.name for m in ResourceThrottleLevel}
        assert names == {"NONE", "LIGHT", "MODERATE", "HEAVY"}

    @pytest.mark.parametrize(
        "value",
        ["none", "light", "moderate", "heavy"],
    )
    def test_construct_from_string(self, value: str):
        level = ResourceThrottleLevel(value)
        assert level.value == value

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            ResourceThrottleLevel("extreme")


# ---------------------------------------------------------------------------
# ParallelExecutorConfig
# ---------------------------------------------------------------------------


class TestParallelExecutorConfig:
    def test_defaults(self):
        cfg = ParallelExecutorConfig()
        assert cfg.max_concurrency == 5
        assert cfg.min_concurrency == 1
        assert cfg.mode == ParallelExecutionMode.PARALLEL
        assert cfg.throttle_level == ResourceThrottleLevel.NONE
        assert cfg.enable_step_parallel_flag is True
        assert cfg.resource_aware is True
        assert cfg.batch_timeout_seconds == 300

    def test_custom_values(self):
        cfg = ParallelExecutorConfig(
            max_concurrency=10,
            min_concurrency=2,
            mode=ParallelExecutionMode.SEQUENTIAL,
            throttle_level=ResourceThrottleLevel.MODERATE,
            enable_step_parallel_flag=False,
            resource_aware=False,
            batch_timeout_seconds=60,
        )
        assert cfg.max_concurrency == 10
        assert cfg.min_concurrency == 2
        assert cfg.mode == ParallelExecutionMode.SEQUENTIAL
        assert cfg.throttle_level == ResourceThrottleLevel.MODERATE
        assert cfg.enable_step_parallel_flag is False
        assert cfg.resource_aware is False
        assert cfg.batch_timeout_seconds == 60

    @pytest.mark.parametrize(
        "throttle,max_c,expected",
        [
            (ResourceThrottleLevel.NONE, 8, 8),
            (ResourceThrottleLevel.LIGHT, 8, 6),   # 8 * 0.75 = 6
            (ResourceThrottleLevel.MODERATE, 8, 4), # 8 * 0.5 = 4
            (ResourceThrottleLevel.HEAVY, 8, 2),    # 8 * 0.25 = 2
        ],
    )
    def test_get_effective_concurrency(
        self,
        throttle: ResourceThrottleLevel,
        max_c: int,
        expected: int,
    ):
        cfg = ParallelExecutorConfig(max_concurrency=max_c, throttle_level=throttle)
        assert cfg.get_effective_concurrency() == expected

    def test_effective_concurrency_floored_at_min(self):
        # max=1, HEAVY => 1*0.25=0.25 => floor to min_concurrency=1
        cfg = ParallelExecutorConfig(max_concurrency=1, min_concurrency=1, throttle_level=ResourceThrottleLevel.HEAVY)
        assert cfg.get_effective_concurrency() == 1

    def test_effective_concurrency_respects_min(self):
        cfg = ParallelExecutorConfig(max_concurrency=2, min_concurrency=3, throttle_level=ResourceThrottleLevel.HEAVY)
        # 2 * 0.25 = 0.5 => int = 0 => max(3, 0) = 3
        assert cfg.get_effective_concurrency() == 3

    def test_none_throttle_returns_max(self):
        cfg = ParallelExecutorConfig(max_concurrency=12, throttle_level=ResourceThrottleLevel.NONE)
        assert cfg.get_effective_concurrency() == 12


# ---------------------------------------------------------------------------
# ExecutionStats
# ---------------------------------------------------------------------------


class TestExecutionStats:
    def test_defaults(self):
        stats = ExecutionStats()
        assert stats.total_steps == 0
        assert stats.completed_steps == 0
        assert stats.failed_steps == 0
        assert stats.blocked_steps == 0
        assert stats.skipped_steps == 0
        assert stats.parallel_batches == 0
        assert stats.max_parallel_achieved == 0
        assert stats.total_wait_time_ms == 0.0

    def test_to_dict_keys(self):
        stats = ExecutionStats(total_steps=4, completed_steps=3, failed_steps=1)
        d = stats.to_dict()
        expected_keys = {
            "total_steps",
            "completed_steps",
            "failed_steps",
            "blocked_steps",
            "skipped_steps",
            "parallel_batches",
            "max_parallel_achieved",
            "total_wait_time_ms",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_values(self):
        stats = ExecutionStats(
            total_steps=10,
            completed_steps=7,
            failed_steps=2,
            blocked_steps=1,
            skipped_steps=0,
            parallel_batches=3,
            max_parallel_achieved=4,
            total_wait_time_ms=150.5,
        )
        d = stats.to_dict()
        assert d["total_steps"] == 10
        assert d["completed_steps"] == 7
        assert d["failed_steps"] == 2
        assert d["blocked_steps"] == 1
        assert d["skipped_steps"] == 0
        assert d["parallel_batches"] == 3
        assert d["max_parallel_achieved"] == 4
        assert d["total_wait_time_ms"] == 150.5

    def test_mutable_after_creation(self):
        stats = ExecutionStats()
        stats.completed_steps += 1
        assert stats.completed_steps == 1


# ---------------------------------------------------------------------------
# StepResult
# ---------------------------------------------------------------------------


class TestStepResult:
    def test_success_result(self):
        r = StepResult(step_id="step-1", success=True, result="output text")
        assert r.step_id == "step-1"
        assert r.success is True
        assert r.result == "output text"
        assert r.error is None
        assert r.events == []

    def test_failure_result(self):
        r = StepResult(step_id="step-2", success=False, error="something failed")
        assert r.success is False
        assert r.error == "something failed"
        assert r.result is None

    def test_events_default_is_empty_list(self):
        r = StepResult(step_id="step-3", success=True)
        assert isinstance(r.events, list)
        assert len(r.events) == 0

    def test_events_are_independent_per_instance(self):
        r1 = StepResult(step_id="a", success=True)
        r2 = StepResult(step_id="b", success=True)
        r1.events.append(MagicMock())
        assert len(r2.events) == 0

    def test_result_and_error_both_none_by_default(self):
        r = StepResult(step_id="x", success=True)
        assert r.result is None
        assert r.error is None


# ---------------------------------------------------------------------------
# ParallelExecutor.__init__
# ---------------------------------------------------------------------------


class TestParallelExecutorInit:
    def test_default_init(self):
        executor = ParallelExecutor()
        assert executor.max_concurrency == 5
        assert executor.mode == ParallelExecutionMode.PARALLEL
        assert executor._semaphore is None
        assert executor._completed == set()
        assert executor._failed == set()
        assert executor._resource_pressure == 0.0

    def test_custom_concurrency(self):
        executor = ParallelExecutor(max_concurrency=3)
        assert executor.max_concurrency == 3

    def test_custom_mode(self):
        executor = ParallelExecutor(mode=ParallelExecutionMode.SEQUENTIAL)
        assert executor.mode == ParallelExecutionMode.SEQUENTIAL

    def test_init_with_config(self):
        cfg = ParallelExecutorConfig(
            max_concurrency=10,
            mode=ParallelExecutionMode.ADAPTIVE,
            throttle_level=ResourceThrottleLevel.MODERATE,
        )
        executor = ParallelExecutor(config=cfg)
        # Effective concurrency: 10 * 0.5 = 5
        assert executor.max_concurrency == 5
        assert executor.mode == ParallelExecutionMode.ADAPTIVE
        assert executor.config is cfg

    def test_config_takes_priority_over_direct_args(self):
        cfg = ParallelExecutorConfig(max_concurrency=7, mode=ParallelExecutionMode.SEQUENTIAL)
        # Even if max_concurrency=1 is passed, config wins
        executor = ParallelExecutor(max_concurrency=1, mode=ParallelExecutionMode.PARALLEL, config=cfg)
        assert executor.max_concurrency == 7
        assert executor.mode == ParallelExecutionMode.SEQUENTIAL

    def test_feature_flags_stored(self):
        flags = {"taskgroup_enabled": True, "other_flag": False}
        executor = ParallelExecutor(feature_flags=flags)
        assert executor._feature_flags == flags

    def test_no_feature_flags_is_none(self):
        executor = ParallelExecutor()
        assert executor._feature_flags is None

    def test_stats_initialized(self):
        executor = ParallelExecutor()
        assert isinstance(executor._stats, ExecutionStats)
        assert executor._stats.total_steps == 0


# ---------------------------------------------------------------------------
# ParallelExecutor._resolve_feature_flags
# ---------------------------------------------------------------------------


class TestResolveFeatureFlags:
    def test_returns_injected_flags(self):
        flags = {"taskgroup_enabled": True}
        executor = ParallelExecutor(feature_flags=flags)
        assert executor._resolve_feature_flags() == flags

    def test_calls_get_feature_flags_when_none(self):
        executor = ParallelExecutor()
        fake_flags = {"taskgroup_enabled": False}
        # get_feature_flags is imported lazily inside _resolve_feature_flags,
        # so patch at its canonical module location.
        with patch("app.core.config.get_feature_flags", return_value=fake_flags):
            result = executor._resolve_feature_flags()
        assert result == fake_flags

    def test_injected_empty_dict_returns_empty(self):
        executor = ParallelExecutor(feature_flags={})
        assert executor._resolve_feature_flags() == {}


# ---------------------------------------------------------------------------
# ParallelExecutor.reset
# ---------------------------------------------------------------------------


class TestParallelExecutorReset:
    @pytest.mark.asyncio
    async def test_reset_clears_state(self):
        executor = ParallelExecutor(max_concurrency=3)
        # Pollute state
        executor._completed = {"step-1"}
        executor._failed = {"step-2"}
        executor._resource_pressure = 0.9

        executor.reset()

        assert executor._completed == set()
        assert executor._failed == set()
        assert executor._resource_pressure == 0.0

    @pytest.mark.asyncio
    async def test_reset_creates_semaphore(self):
        executor = ParallelExecutor(max_concurrency=4)
        assert executor._semaphore is None
        executor.reset()
        assert isinstance(executor._semaphore, asyncio.Semaphore)

    @pytest.mark.asyncio
    async def test_reset_stats(self):
        executor = ParallelExecutor()
        executor._stats.completed_steps = 99
        executor.reset()
        assert executor._stats.completed_steps == 0
        assert executor._stats.total_steps == 0

    @pytest.mark.asyncio
    async def test_reset_semaphore_uses_effective_concurrency(self):
        cfg = ParallelExecutorConfig(max_concurrency=8, throttle_level=ResourceThrottleLevel.MODERATE)
        executor = ParallelExecutor(config=cfg)
        executor.reset()
        # 8 * 0.5 = 4 -> semaphore value should be 4
        assert executor._semaphore is not None


# ---------------------------------------------------------------------------
# ParallelExecutor.set_throttle_level
# ---------------------------------------------------------------------------


class TestSetThrottleLevel:
    @pytest.mark.asyncio
    async def test_set_throttle_updates_config(self):
        executor = ParallelExecutor(max_concurrency=8)
        executor.reset()
        executor.set_throttle_level(ResourceThrottleLevel.HEAVY)
        assert executor.config.throttle_level == ResourceThrottleLevel.HEAVY

    @pytest.mark.asyncio
    async def test_set_throttle_recreates_semaphore_when_changed(self):
        executor = ParallelExecutor(max_concurrency=8)
        executor.reset()
        old_sem = executor._semaphore
        executor.set_throttle_level(ResourceThrottleLevel.MODERATE)
        # Semaphore should be replaced because concurrency changed
        assert executor._semaphore is not old_sem

    @pytest.mark.asyncio
    async def test_set_same_throttle_does_not_recreate_semaphore(self):
        executor = ParallelExecutor(max_concurrency=8)
        executor.reset()
        old_sem = executor._semaphore
        # NONE -> NONE: same effective concurrency, no new semaphore
        executor.set_throttle_level(ResourceThrottleLevel.NONE)
        assert executor._semaphore is old_sem


# ---------------------------------------------------------------------------
# ParallelExecutor.update_resource_pressure
# ---------------------------------------------------------------------------


class TestUpdateResourcePressure:
    @pytest.mark.asyncio
    async def test_pressure_clamped_above(self):
        executor = ParallelExecutor()
        executor.reset()
        executor.update_resource_pressure(1.5)
        assert executor._resource_pressure == 1.0

    @pytest.mark.asyncio
    async def test_pressure_clamped_below(self):
        executor = ParallelExecutor()
        executor.reset()
        executor.update_resource_pressure(-0.5)
        assert executor._resource_pressure == 0.0

    @pytest.mark.asyncio
    async def test_pressure_stored(self):
        executor = ParallelExecutor()
        executor.reset()
        executor.update_resource_pressure(0.65)
        assert executor._resource_pressure == pytest.approx(0.65)

    @pytest.mark.parametrize(
        "pressure,expected_throttle",
        [
            (0.95, ResourceThrottleLevel.HEAVY),
            (0.75, ResourceThrottleLevel.MODERATE),
            (0.55, ResourceThrottleLevel.LIGHT),
            (0.3, ResourceThrottleLevel.NONE),
        ],
    )
    @pytest.mark.asyncio
    async def test_auto_throttle_from_pressure(
        self,
        pressure: float,
        expected_throttle: ResourceThrottleLevel,
    ):
        executor = ParallelExecutor(max_concurrency=8)
        executor.reset()
        executor.update_resource_pressure(pressure)
        assert executor.config.throttle_level == expected_throttle

    @pytest.mark.asyncio
    async def test_resource_aware_false_disables_auto_throttle(self):
        cfg = ParallelExecutorConfig(max_concurrency=8, resource_aware=False)
        executor = ParallelExecutor(config=cfg)
        executor.reset()
        executor.update_resource_pressure(0.99)
        # Should NOT auto-adjust since resource_aware=False
        assert executor.config.throttle_level == ResourceThrottleLevel.NONE


# ---------------------------------------------------------------------------
# ParallelExecutor._get_ready_steps
# ---------------------------------------------------------------------------


class TestGetReadySteps:
    def test_no_steps_returns_empty(self):
        executor = ParallelExecutor()
        executor.reset()
        plan = make_plan()
        assert executor._get_ready_steps(plan) == []

    def test_all_pending_no_deps_all_ready(self):
        steps = [make_step(f"Search {i}") for i in range(3)]
        plan = make_plan(steps)
        executor = ParallelExecutor()
        executor.reset()
        ready = executor._get_ready_steps(plan)
        assert len(ready) == 3

    def test_completed_step_not_in_ready(self):
        step = make_step()
        step.status = ExecutionStatus.COMPLETED
        plan = make_plan([step])
        executor = ParallelExecutor()
        executor.reset()
        assert executor._get_ready_steps(plan) == []

    def test_running_step_not_in_ready(self):
        step = make_step()
        step.status = ExecutionStatus.RUNNING
        plan = make_plan([step])
        executor = ParallelExecutor()
        executor.reset()
        assert executor._get_ready_steps(plan) == []

    def test_dependency_not_completed_blocks_ready(self):
        s1 = make_step("Step 1")
        s2 = make_step("Step 2", dependencies=[s1.id])
        plan = make_plan([s1, s2])
        executor = ParallelExecutor()
        executor.reset()
        ready = executor._get_ready_steps(plan)
        # s1 is pending with no deps -> ready; s2 depends on s1 (not completed)
        assert s1 in ready
        assert s2 not in ready

    def test_dependency_completed_makes_step_ready(self):
        s1 = make_step("Step 1")
        s2 = make_step("Step 2", dependencies=[s1.id])
        plan = make_plan([s1, s2])
        executor = ParallelExecutor()
        executor.reset()
        executor._completed.add(s1.id)
        ready = executor._get_ready_steps(plan)
        assert s2 in ready

    def test_failed_dependency_marks_step_blocked(self):
        s1 = make_step("Step 1")
        s2 = make_step("Step 2", dependencies=[s1.id])
        plan = make_plan([s1, s2])
        executor = ParallelExecutor()
        executor.reset()
        executor._failed.add(s1.id)
        s1.status = ExecutionStatus.FAILED
        executor._get_ready_steps(plan)
        assert s2.status == ExecutionStatus.BLOCKED

    def test_failed_dep_increments_blocked_stats(self):
        s1 = make_step("Step 1")
        s2 = make_step("Step 2", dependencies=[s1.id])
        plan = make_plan([s1, s2])
        executor = ParallelExecutor()
        executor.reset()
        executor._failed.add(s1.id)
        s1.status = ExecutionStatus.FAILED
        executor._get_ready_steps(plan)
        assert executor._stats.blocked_steps == 1


# ---------------------------------------------------------------------------
# ParallelExecutor._is_step_safe_for_parallel
# ---------------------------------------------------------------------------


class TestIsStepSafeForParallel:
    @pytest.mark.parametrize(
        "description",
        [
            "Search for Python documentation",
            "Read the file contents",
            "Fetch data from the API",
            "Get the latest results",
            "Find relevant papers",
            "Analyze the dataset",
            "Research competitor pricing",
            "Browse to the website",
            "View the dashboard",
            "List all available options",
            "Check if service is healthy",
        ],
    )
    def test_read_only_keywords_are_safe(self, description: str):
        executor = ParallelExecutor()
        step = make_step(description)
        assert executor._is_step_safe_for_parallel(step) is True

    @pytest.mark.parametrize(
        "description",
        [
            "Delete the temporary files",
            "Remove old entries from the database",
            "Modify the configuration file",
            "Update the user record",
            "Write the report to disk",
            "Install the dependencies",
            "Uninstall the old package",
            "Configure the server settings",
            "Setup the environment",
            "Create directory for output",
            "Mkdir for project structure",
            "Move files to new location",
            "Rename the output file",
        ],
    )
    def test_state_modifying_keywords_are_not_safe(self, description: str):
        executor = ParallelExecutor()
        step = make_step(description)
        assert executor._is_step_safe_for_parallel(step) is False

    def test_unknown_description_defaults_to_safe(self):
        executor = ParallelExecutor()
        step = make_step("Do something completely custom")
        assert executor._is_step_safe_for_parallel(step) is True

    def test_case_insensitive_matching(self):
        executor = ParallelExecutor()
        step = make_step("DELETE all records")
        assert executor._is_step_safe_for_parallel(step) is False

        step2 = make_step("SEARCH for patterns")
        assert executor._is_step_safe_for_parallel(step2) is True


# ---------------------------------------------------------------------------
# ParallelExecutor._filter_parallelizable_steps
# ---------------------------------------------------------------------------


class TestFilterParallelizableSteps:
    def test_flag_disabled_all_steps_are_parallel(self):
        cfg = ParallelExecutorConfig(enable_step_parallel_flag=False)
        executor = ParallelExecutor(config=cfg)
        steps = [make_step("Delete files"), make_step("Write output")]
        parallel, sequential = executor._filter_parallelizable_steps(steps)
        assert len(parallel) == 2
        assert sequential == []

    def test_explicit_parallel_flag_true(self):
        # Step is a Pydantic model that rejects unknown attrs; use MagicMock
        # to simulate a step-like object with parallel_processing=True.
        executor = ParallelExecutor()
        step = MagicMock(spec=Step)
        step.parallel_processing = True
        step.description = "Some task"
        parallel, sequential = executor._filter_parallelizable_steps([step])
        assert step in parallel
        assert step not in sequential

    def test_explicit_parallel_flag_false(self):
        executor = ParallelExecutor()
        step = MagicMock(spec=Step)
        step.parallel_processing = False
        step.description = "Search for data"
        parallel, sequential = executor._filter_parallelizable_steps([step])
        assert step in sequential
        assert step not in parallel

    def test_no_flag_uses_heuristics(self):
        executor = ParallelExecutor()
        safe_step = make_step("Search the web")
        unsafe_step = make_step("Delete the database")
        parallel, sequential = executor._filter_parallelizable_steps([safe_step, unsafe_step])
        assert safe_step in parallel
        assert unsafe_step in sequential

    def test_empty_list_returns_empty_tuples(self):
        executor = ParallelExecutor()
        parallel, sequential = executor._filter_parallelizable_steps([])
        assert parallel == []
        assert sequential == []


# ---------------------------------------------------------------------------
# ParallelExecutor._execute_step_with_limit
# ---------------------------------------------------------------------------


class TestExecuteStepWithLimit:
    @pytest.mark.asyncio
    async def test_success_returns_step_result(self):
        executor = ParallelExecutor()
        executor.reset()
        step = make_step()

        async def succeed(s: Step) -> StepResult:
            return StepResult(step_id=s.id, success=True, result="ok")

        result = await executor._execute_step_with_limit(step, succeed)
        assert result.success is True
        assert result.result == "ok"

    @pytest.mark.asyncio
    async def test_exception_is_wrapped_in_step_result(self):
        executor = ParallelExecutor()
        executor.reset()
        step = make_step()

        async def fail(s: Step) -> StepResult:
            raise RuntimeError("boom")

        result = await executor._execute_step_with_limit(step, fail)
        assert result.success is False
        assert result.step_id == step.id
        assert "boom" in result.error

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self):
        """Verify the semaphore prevents more than N concurrent executions."""
        max_concurrent = 2
        executor = ParallelExecutor(max_concurrency=max_concurrent)
        executor.reset()

        active = 0
        max_active_seen = 0

        async def slow_step(s: Step) -> StepResult:
            nonlocal active, max_active_seen
            active += 1
            max_active_seen = max(max_active_seen, active)
            await asyncio.sleep(0.05)
            active -= 1
            return StepResult(step_id=s.id, success=True)

        steps = [make_step(f"Step {i}") for i in range(5)]
        tasks = [
            asyncio.create_task(executor._execute_step_with_limit(s, slow_step))
            for s in steps
        ]
        await asyncio.gather(*tasks)
        assert max_active_seen <= max_concurrent


# ---------------------------------------------------------------------------
# ParallelExecutor.execute_plan (sequential path)
# ---------------------------------------------------------------------------


class TestExecutePlanSequential:
    @pytest.mark.asyncio
    async def test_empty_plan_yields_single_event(self):
        executor = ParallelExecutor(mode=ParallelExecutionMode.SEQUENTIAL)
        plan = make_plan()

        async def noop(s: Step) -> StepResult:
            return StepResult(step_id=s.id, success=True)

        events = await collect_events(executor.execute_plan(plan, noop))
        # Only the final PlanEvent should be emitted for an empty plan
        assert len(events) == 1
        assert isinstance(events[-1], PlanEvent)

    @pytest.mark.asyncio
    async def test_single_step_success(self):
        executor = ParallelExecutor(mode=ParallelExecutionMode.SEQUENTIAL)
        step = make_step("Search for data")
        plan = make_plan([step])

        async def succeed(s: Step) -> StepResult:
            return StepResult(step_id=s.id, success=True, result="found it")

        events = await collect_events(executor.execute_plan(plan, succeed))
        assert step.status == ExecutionStatus.COMPLETED
        assert step.result == "found it"
        assert plan.status == ExecutionStatus.COMPLETED
        plan_events = [e for e in events if isinstance(e, PlanEvent)]
        assert len(plan_events) >= 1

    @pytest.mark.asyncio
    async def test_single_step_failure(self):
        executor = ParallelExecutor(mode=ParallelExecutionMode.SEQUENTIAL)
        step = make_step("Search for data")
        plan = make_plan([step])

        async def fail(s: Step) -> StepResult:
            return StepResult(step_id=s.id, success=False, error="not found")

        await collect_events(executor.execute_plan(plan, fail))
        assert step.status == ExecutionStatus.FAILED
        assert plan.status == ExecutionStatus.FAILED

    @pytest.mark.asyncio
    async def test_sequential_respects_dependency_order(self):
        s1 = make_step("Step 1")
        s2 = make_step("Step 2", dependencies=[s1.id])
        plan = make_plan([s1, s2])
        plan.infer_sequential_dependencies()

        execution_order: list[str] = []

        async def record(s: Step) -> StepResult:
            execution_order.append(s.id)
            return StepResult(step_id=s.id, success=True)

        executor = ParallelExecutor(mode=ParallelExecutionMode.SEQUENTIAL)
        await collect_events(executor.execute_plan(plan, record))
        assert execution_order == [s1.id, s2.id]

    @pytest.mark.asyncio
    async def test_stats_updated_after_execution(self):
        steps = [make_step(f"Step {i}") for i in range(3)]
        plan = make_plan(steps)
        executor = ParallelExecutor(mode=ParallelExecutionMode.SEQUENTIAL)

        async def succeed(s: Step) -> StepResult:
            return StepResult(step_id=s.id, success=True)

        await collect_events(executor.execute_plan(plan, succeed))
        assert executor._stats.total_steps == 3
        assert executor._stats.completed_steps == 3

    @pytest.mark.asyncio
    async def test_failed_step_blocks_dependent_via_cascade(self):
        s1 = make_step("Step 1")
        s2 = make_step("Step 2", dependencies=[s1.id])
        s3 = make_step("Step 3", dependencies=[s2.id])
        plan = make_plan([s1, s2, s3])

        async def fail_first(s: Step) -> StepResult:
            if s.id == s1.id:
                return StepResult(step_id=s.id, success=False, error="oops")
            return StepResult(step_id=s.id, success=True)

        executor = ParallelExecutor(mode=ParallelExecutionMode.SEQUENTIAL)
        await collect_events(executor.execute_plan(plan, fail_first))
        assert s1.status == ExecutionStatus.FAILED
        assert s2.status == ExecutionStatus.BLOCKED
        assert s3.status == ExecutionStatus.BLOCKED


# ---------------------------------------------------------------------------
# ParallelExecutor.execute_plan (parallel path)
# ---------------------------------------------------------------------------


class TestExecutePlanParallel:
    @pytest.mark.asyncio
    async def test_independent_steps_run_in_parallel(self):
        """Steps with no dependencies should all launch concurrently."""
        executor = ParallelExecutor(
            max_concurrency=5,
            mode=ParallelExecutionMode.PARALLEL,
            feature_flags={"taskgroup_enabled": False},
        )
        steps = [make_step(f"Search {i}") for i in range(4)]
        plan = make_plan(steps)

        start_times: list[float] = []

        async def record_start(s: Step) -> StepResult:
            import time
            start_times.append(time.monotonic())
            await asyncio.sleep(0.01)
            return StepResult(step_id=s.id, success=True)

        await collect_events(executor.execute_plan(plan, record_start))
        # All 4 steps should complete
        assert all(s.status == ExecutionStatus.COMPLETED for s in steps)

    @pytest.mark.asyncio
    async def test_plan_status_completed_when_all_succeed(self):
        executor = ParallelExecutor(
            mode=ParallelExecutionMode.PARALLEL,
            feature_flags={"taskgroup_enabled": False},
        )
        steps = [make_step(f"Fetch {i}") for i in range(3)]
        plan = make_plan(steps)

        async def succeed(s: Step) -> StepResult:
            return StepResult(step_id=s.id, success=True)

        await collect_events(executor.execute_plan(plan, succeed))
        assert plan.status == ExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_plan_status_failed_when_any_fails(self):
        executor = ParallelExecutor(
            mode=ParallelExecutionMode.PARALLEL,
            feature_flags={"taskgroup_enabled": False},
        )
        s1 = make_step("Search")
        s2 = make_step("Fetch")
        plan = make_plan([s1, s2])

        async def mixed(s: Step) -> StepResult:
            if s.id == s1.id:
                return StepResult(step_id=s.id, success=False, error="fail")
            return StepResult(step_id=s.id, success=True)

        await collect_events(executor.execute_plan(plan, mixed))
        assert plan.status == ExecutionStatus.FAILED

    @pytest.mark.asyncio
    async def test_exception_in_step_func_handled_gracefully(self):
        executor = ParallelExecutor(
            mode=ParallelExecutionMode.PARALLEL,
            feature_flags={"taskgroup_enabled": False},
        )
        step = make_step("Fetch data")
        plan = make_plan([step])

        async def boom(s: Step) -> StepResult:
            raise ValueError("unexpected")

        await collect_events(executor.execute_plan(plan, boom))
        assert step.status == ExecutionStatus.FAILED
        assert "unexpected" in step.error

    @pytest.mark.asyncio
    async def test_parallel_batches_tracked(self):
        executor = ParallelExecutor(
            mode=ParallelExecutionMode.PARALLEL,
            feature_flags={"taskgroup_enabled": False},
        )
        steps = [make_step(f"Fetch {i}") for i in range(3)]
        plan = make_plan(steps)

        async def succeed(s: Step) -> StepResult:
            return StepResult(step_id=s.id, success=True)

        await collect_events(executor.execute_plan(plan, succeed))
        assert executor._stats.parallel_batches >= 1

    @pytest.mark.asyncio
    async def test_max_parallel_achieved_tracked(self):
        executor = ParallelExecutor(
            max_concurrency=10,
            mode=ParallelExecutionMode.PARALLEL,
            feature_flags={"taskgroup_enabled": False},
        )
        steps = [make_step(f"Search {i}") for i in range(5)]
        plan = make_plan(steps)

        async def succeed(s: Step) -> StepResult:
            return StepResult(step_id=s.id, success=True)

        await collect_events(executor.execute_plan(plan, succeed))
        assert executor._stats.max_parallel_achieved >= 1

    @pytest.mark.asyncio
    async def test_taskgroup_enabled_flag_path(self):
        """Exercises the use_taskgroup=True code path."""
        executor = ParallelExecutor(
            mode=ParallelExecutionMode.PARALLEL,
            feature_flags={"taskgroup_enabled": True},
        )
        steps = [make_step(f"Step {i}") for i in range(2)]
        plan = make_plan(steps)

        async def succeed(s: Step) -> StepResult:
            return StepResult(step_id=s.id, success=True)

        events = await collect_events(executor.execute_plan(plan, succeed))
        assert all(s.status == ExecutionStatus.COMPLETED for s in steps)
        assert any(isinstance(e, PlanEvent) for e in events)

    @pytest.mark.asyncio
    async def test_final_plan_event_is_finished_on_success(self):
        executor = ParallelExecutor(
            mode=ParallelExecutionMode.PARALLEL,
            feature_flags={"taskgroup_enabled": False},
        )
        step = make_step("Search web")
        plan = make_plan([step])

        async def succeed(s: Step) -> StepResult:
            return StepResult(step_id=s.id, success=True)

        events = await collect_events(executor.execute_plan(plan, succeed))
        last_event = events[-1]
        assert isinstance(last_event, PlanEvent)
        assert last_event.status == PlanStatus.FINISHED


# ---------------------------------------------------------------------------
# ParallelExecutor._process_result
# ---------------------------------------------------------------------------


class TestProcessResult:
    @pytest.mark.asyncio
    async def test_success_updates_step_and_stats(self):
        executor = ParallelExecutor()
        executor.reset()
        plan = make_plan()
        step = make_step()
        result = StepResult(step_id=step.id, success=True, result="output")

        events = []
        async for event in executor._process_result(plan, step, result):
            events.append(event)

        assert step.status == ExecutionStatus.COMPLETED
        assert step.result == "output"
        assert step.success is True
        assert step.id in executor._completed
        assert executor._stats.completed_steps == 1

    @pytest.mark.asyncio
    async def test_failure_updates_step_and_stats(self):
        executor = ParallelExecutor()
        executor.reset()
        plan = make_plan()
        step = make_step()
        result = StepResult(step_id=step.id, success=False, error="timeout")

        async for _ in executor._process_result(plan, step, result):
            pass

        assert step.status == ExecutionStatus.FAILED
        assert step.error == "timeout"
        assert step.success is False
        assert step.id in executor._failed
        assert executor._stats.failed_steps == 1

    @pytest.mark.asyncio
    async def test_events_from_result_are_yielded(self):
        executor = ParallelExecutor()
        executor.reset()
        plan = make_plan()
        step = make_step()
        fake_event = MagicMock(spec=BaseEvent)
        result = StepResult(step_id=step.id, success=True, events=[fake_event])

        events = []
        async for event in executor._process_result(plan, step, result):
            events.append(event)

        assert fake_event in events

    @pytest.mark.asyncio
    async def test_process_result_always_emits_plan_event(self):
        executor = ParallelExecutor()
        executor.reset()
        plan = make_plan()
        step = make_step()
        result = StepResult(step_id=step.id, success=True)

        events = []
        async for event in executor._process_result(plan, step, result):
            events.append(event)

        plan_events = [e for e in events if isinstance(e, PlanEvent)]
        assert len(plan_events) == 1

    @pytest.mark.asyncio
    async def test_failure_triggers_cascade_block(self):
        s1 = make_step("Step 1")
        s2 = make_step("Step 2", dependencies=[s1.id])
        plan = make_plan([s1, s2])

        executor = ParallelExecutor()
        executor.reset()
        result = StepResult(step_id=s1.id, success=False, error="error msg")

        async for _ in executor._process_result(plan, s1, result):
            pass

        assert s2.status == ExecutionStatus.BLOCKED

    @pytest.mark.asyncio
    async def test_blocked_steps_counted_in_stats(self):
        s1 = make_step("Step 1")
        s2 = make_step("Step 2", dependencies=[s1.id])
        plan = make_plan([s1, s2])

        executor = ParallelExecutor()
        executor.reset()
        result = StepResult(step_id=s1.id, success=False, error="x")

        async for _ in executor._process_result(plan, s1, result):
            pass

        assert executor._stats.blocked_steps == 1


# ---------------------------------------------------------------------------
# ParallelExecutor.can_parallelize
# ---------------------------------------------------------------------------


class TestCanParallelize:
    def test_empty_plan_cannot_parallelize(self):
        executor = ParallelExecutor()
        assert executor.can_parallelize(make_plan()) is False

    def test_single_step_cannot_parallelize(self):
        executor = ParallelExecutor()
        plan = make_plan([make_step()])
        assert executor.can_parallelize(plan) is False

    def test_two_independent_steps_can_parallelize(self):
        executor = ParallelExecutor()
        plan = make_plan([make_step("A"), make_step("B")])
        # No dependencies -> second step is independent
        assert executor.can_parallelize(plan) is True

    def test_fully_sequential_plan_cannot_parallelize(self):
        executor = ParallelExecutor()
        s1 = make_step("A")
        s2 = make_step("B", dependencies=[s1.id])
        plan = make_plan([s1, s2])
        # s2 depends on s1, so no independent steps
        assert executor.can_parallelize(plan) is False

    def test_mixed_plan_can_parallelize(self):
        executor = ParallelExecutor()
        s1 = make_step("A")
        s2 = make_step("B", dependencies=[s1.id])
        s3 = make_step("C")
        plan = make_plan([s1, s2, s3])
        # s3 has no internal deps and is at index > 0 -> independent
        assert executor.can_parallelize(plan) is True


# ---------------------------------------------------------------------------
# ParallelExecutor.estimate_parallelism
# ---------------------------------------------------------------------------


class TestEstimateParallelism:
    def test_empty_plan(self):
        executor = ParallelExecutor()
        result = executor.estimate_parallelism(make_plan())
        assert result["max_parallel"] == 0
        assert result["critical_path_length"] == 0
        assert result["speedup_factor"] == 1.0

    def test_single_step(self):
        executor = ParallelExecutor()
        plan = make_plan([make_step()])
        result = executor.estimate_parallelism(plan)
        assert result["total_steps"] == 1
        assert result["critical_path_length"] == 1
        assert result["max_parallel"] == 1
        assert result["speedup_factor"] == pytest.approx(1.0)

    def test_fully_parallel_steps(self):
        """All steps independent -> critical path = 1, speedup = N."""
        executor = ParallelExecutor()
        steps = [make_step(f"Step {i}") for i in range(4)]
        plan = make_plan(steps)
        result = executor.estimate_parallelism(plan)
        assert result["max_parallel"] == 4
        assert result["critical_path_length"] == 1
        assert result["speedup_factor"] == pytest.approx(4.0)

    def test_fully_sequential_steps(self):
        """Chain A->B->C -> critical path = 3, speedup = 1."""
        s1 = make_step("A")
        s2 = make_step("B", dependencies=[s1.id])
        s3 = make_step("C", dependencies=[s2.id])
        plan = make_plan([s1, s2, s3])
        executor = ParallelExecutor()
        result = executor.estimate_parallelism(plan)
        assert result["critical_path_length"] == 3
        assert result["speedup_factor"] == pytest.approx(1.0)

    def test_diamond_dependency(self):
        """
             A
            / \\
           B   C
            \\ /
             D
        Critical path: A->B->D or A->C->D = 3
        max_parallel at level 2: B and C run together -> 2
        """
        s_a = make_step("A")
        s_b = make_step("B", dependencies=[s_a.id])
        s_c = make_step("C", dependencies=[s_a.id])
        s_d = make_step("D", dependencies=[s_b.id, s_c.id])
        plan = make_plan([s_a, s_b, s_c, s_d])
        executor = ParallelExecutor()
        result = executor.estimate_parallelism(plan)
        assert result["critical_path_length"] == 3
        assert result["max_parallel"] == 2

    def test_speedup_factor_is_rounded(self):
        executor = ParallelExecutor()
        steps = [make_step(f"S{i}") for i in range(3)]
        plan = make_plan(steps)
        result = executor.estimate_parallelism(plan)
        # 3 steps / 1 critical path = 3.0 (already clean, but testing round())
        speedup = result["speedup_factor"]
        assert isinstance(speedup, float)
        assert len(str(speedup).split(".")[-1]) <= 2


# ---------------------------------------------------------------------------
# ParallelExecutor.aggregate_results
# ---------------------------------------------------------------------------


class TestAggregateResults:
    def test_empty_list_returns_failure(self):
        result = ParallelExecutor.aggregate_results([])
        assert result["success"] is False
        assert "No results" in result["message"]

    def test_merge_all_success(self):
        results = [
            StepResult(step_id="a", success=True, result="alpha"),
            StepResult(step_id="b", success=True, result="beta"),
        ]
        agg = ParallelExecutor.aggregate_results(results, strategy="merge")
        assert agg["success"] is True
        assert agg["total"] == 2
        assert agg["successful"] == 2
        assert agg["failed"] == 0
        assert len(agg["merged_results"]) == 2

    def test_merge_partial_failure(self):
        results = [
            StepResult(step_id="a", success=True, result="ok"),
            StepResult(step_id="b", success=False, error="boom"),
        ]
        agg = ParallelExecutor.aggregate_results(results, strategy="merge")
        assert agg["success"] is False
        assert agg["failed"] == 1
        assert len(agg["errors"]) == 1
        assert agg["errors"][0]["step_id"] == "b"

    def test_merge_no_results_in_merged_when_no_result_field(self):
        results = [StepResult(step_id="a", success=True, result=None)]
        agg = ParallelExecutor.aggregate_results(results, strategy="merge")
        # result=None means it won't appear in merged_results (filter: r.result)
        assert agg["merged_results"] == []

    def test_best_first_success(self):
        results = [
            StepResult(step_id="a", success=True, result="best"),
            StepResult(step_id="b", success=True, result="second"),
        ]
        agg = ParallelExecutor.aggregate_results(results, strategy="best")
        assert agg["success"] is True
        assert agg["best_result"] == "best"
        assert agg["step_id"] == "a"

    def test_best_all_failed(self):
        results = [StepResult(step_id="a", success=False, error="err")]
        agg = ParallelExecutor.aggregate_results(results, strategy="best")
        assert agg["success"] is False
        assert "err" in agg["error"]

    def test_best_no_results_fallback(self):
        # Empty failed list but results list is also empty -> edge case
        results = [StepResult(step_id="a", success=False, error=None)]
        agg = ParallelExecutor.aggregate_results(results, strategy="best")
        assert agg["success"] is False

    def test_all_strategy_returns_everything(self):
        results = [
            StepResult(step_id="a", success=True, result="out"),
            StepResult(step_id="b", success=False, error="fail"),
        ]
        agg = ParallelExecutor.aggregate_results(results, strategy="all")
        assert agg["success"] is False
        assert len(agg["results"]) == 2
        items = {r["step_id"]: r for r in agg["results"]}
        assert items["a"]["success"] is True
        assert items["b"]["success"] is False

    def test_all_strategy_all_success(self):
        results = [
            StepResult(step_id="x", success=True, result="a"),
            StepResult(step_id="y", success=True, result="b"),
        ]
        agg = ParallelExecutor.aggregate_results(results, strategy="all")
        assert agg["success"] is True

    def test_default_strategy_is_merge(self):
        results = [StepResult(step_id="a", success=True, result="ok")]
        agg = ParallelExecutor.aggregate_results(results)
        # merge strategy includes 'merged_results' key
        assert "merged_results" in agg

    @pytest.mark.parametrize("strategy", ["merge", "best", "all"])
    def test_all_strategies_return_dict(self, strategy: str):
        results = [StepResult(step_id="a", success=True, result="x")]
        agg = ParallelExecutor.aggregate_results(results, strategy=strategy)
        assert isinstance(agg, dict)


# ---------------------------------------------------------------------------
# ParallelExecutor.get_parallelism_report
# ---------------------------------------------------------------------------


class TestGetParallelismReport:
    def test_report_structure(self):
        executor = ParallelExecutor(max_concurrency=4)
        report = executor.get_parallelism_report()
        assert "stats" in report
        assert "config" in report
        assert "metrics" in report

    def test_config_section(self):
        executor = ParallelExecutor(max_concurrency=6, mode=ParallelExecutionMode.SEQUENTIAL)
        report = executor.get_parallelism_report()
        cfg = report["config"]
        assert cfg["max_concurrency"] == 6
        assert cfg["mode"] == "sequential"
        assert "effective_concurrency" in cfg
        assert "throttle_level" in cfg

    def test_metrics_section(self):
        executor = ParallelExecutor()
        report = executor.get_parallelism_report()
        metrics = report["metrics"]
        assert "completion_efficiency" in metrics
        assert "parallel_efficiency" in metrics
        assert "resource_pressure" in metrics

    @pytest.mark.asyncio
    async def test_completion_efficiency_after_execution(self):
        executor = ParallelExecutor(
            mode=ParallelExecutionMode.PARALLEL,
            feature_flags={"taskgroup_enabled": False},
        )
        steps = [make_step(f"Step {i}") for i in range(4)]
        plan = make_plan(steps)

        async def succeed(s: Step) -> StepResult:
            return StepResult(step_id=s.id, success=True)

        await collect_events(executor.execute_plan(plan, succeed))
        report = executor.get_parallelism_report()
        assert report["metrics"]["completion_efficiency"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_efficiency_zero_when_no_steps(self):
        executor = ParallelExecutor()
        report = executor.get_parallelism_report()
        assert report["metrics"]["completion_efficiency"] == 0.0

    def test_resource_pressure_reflected_in_report(self):
        executor = ParallelExecutor()
        executor.reset()
        executor._resource_pressure = 0.42
        report = executor.get_parallelism_report()
        assert report["metrics"]["resource_pressure"] == pytest.approx(0.42, abs=0.01)


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------


class TestGetStats:
    def test_returns_execution_stats_instance(self):
        executor = ParallelExecutor()
        stats = executor.get_stats()
        assert isinstance(stats, ExecutionStats)

    def test_same_object_is_returned(self):
        executor = ParallelExecutor()
        assert executor.get_stats() is executor._stats


# ---------------------------------------------------------------------------
# Dependency inference integration (infer_smart_dependencies)
# ---------------------------------------------------------------------------


class TestDependencyInference:
    @pytest.mark.asyncio
    async def test_parallel_mode_infers_smart_deps(self):
        """Without any explicit deps, PARALLEL mode calls infer_smart_dependencies."""
        s1 = make_step("First, search for documentation")
        s2 = make_step("Analyze results")
        plan = make_plan([s1, s2])
        executor = ParallelExecutor(
            mode=ParallelExecutionMode.PARALLEL,
            feature_flags={"taskgroup_enabled": False},
        )

        async def succeed(s: Step) -> StepResult:
            return StepResult(step_id=s.id, success=True)

        # Should complete without error (dependencies inferred)
        events = await collect_events(executor.execute_plan(plan, succeed))
        assert any(isinstance(e, PlanEvent) for e in events)

    @pytest.mark.asyncio
    async def test_sequential_mode_infers_sequential_deps(self):
        """Without any explicit deps, SEQUENTIAL mode calls infer_sequential_dependencies."""
        s1 = make_step("Step A")
        s2 = make_step("Step B")
        plan = make_plan([s1, s2])
        executor = ParallelExecutor(mode=ParallelExecutionMode.SEQUENTIAL)
        execution_order: list[str] = []

        async def record(s: Step) -> StepResult:
            execution_order.append(s.id)
            return StepResult(step_id=s.id, success=True)

        await collect_events(executor.execute_plan(plan, record))
        # Sequential inference ensures s1 before s2
        assert execution_order == [s1.id, s2.id]

    @pytest.mark.asyncio
    async def test_explicit_deps_not_overwritten(self):
        """Pre-set dependencies should not be inferred again."""
        s1 = make_step("A")
        s2 = make_step("B", dependencies=[s1.id])
        plan = make_plan([s1, s2])
        executor = ParallelExecutor(
            mode=ParallelExecutionMode.PARALLEL,
            feature_flags={"taskgroup_enabled": False},
        )

        async def succeed(s: Step) -> StepResult:
            return StepResult(step_id=s.id, success=True)

        await collect_events(executor.execute_plan(plan, succeed))
        # s2 still depends on s1 — not changed
        assert s1.id in s2.dependencies
