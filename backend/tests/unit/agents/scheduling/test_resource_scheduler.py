"""Tests for ResourceScheduler — budgets, task scheduling, priority ordering, singleton."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.services.agents.scheduling.resource_scheduler import (
    ResourceBudget,
    ResourceScheduler,
    ResourceType,
    ScheduledTask,
    SchedulePriority,
    SchedulerMetrics,
    get_resource_scheduler,
    reset_resource_scheduler,
)

# ---------------------------------------------------------------------------
# ResourceType enum
# ---------------------------------------------------------------------------


class TestResourceType:
    def test_tokens_value(self):
        assert ResourceType.TOKENS == "tokens"

    def test_api_calls_value(self):
        assert ResourceType.API_CALLS == "api_calls"

    def test_time_value(self):
        assert ResourceType.TIME == "time"

    def test_memory_value(self):
        assert ResourceType.MEMORY == "memory"

    def test_concurrent_tasks_value(self):
        assert ResourceType.CONCURRENT_TASKS == "concurrent_tasks"

    def test_all_five_members_exist(self):
        values = {m.value for m in ResourceType}
        assert values == {"tokens", "api_calls", "time", "memory", "concurrent_tasks"}


# ---------------------------------------------------------------------------
# SchedulePriority enum
# ---------------------------------------------------------------------------


class TestSchedulePriority:
    def test_critical_value(self):
        assert SchedulePriority.CRITICAL == "critical"

    def test_high_value(self):
        assert SchedulePriority.HIGH == "high"

    def test_normal_value(self):
        assert SchedulePriority.NORMAL == "normal"

    def test_low_value(self):
        assert SchedulePriority.LOW == "low"

    def test_background_value(self):
        assert SchedulePriority.BACKGROUND == "background"

    def test_all_five_members_exist(self):
        values = {m.value for m in SchedulePriority}
        assert values == {"critical", "high", "normal", "low", "background"}


# ---------------------------------------------------------------------------
# ResourceBudget
# ---------------------------------------------------------------------------


class TestResourceBudget:
    def _make_budget(self, total: float = 100.0, used: float = 0.0, reserved: float = 0.0) -> ResourceBudget:
        return ResourceBudget(
            resource_type=ResourceType.TOKENS,
            total=total,
            used=used,
            reserved=reserved,
        )

    def test_available_fresh(self):
        b = self._make_budget(total=100.0)
        assert b.available == 100.0

    def test_available_with_used(self):
        b = self._make_budget(total=100.0, used=40.0)
        assert b.available == 60.0

    def test_available_with_reserved(self):
        b = self._make_budget(total=100.0, reserved=25.0)
        assert b.available == 75.0

    def test_available_combined_used_and_reserved(self):
        b = self._make_budget(total=100.0, used=30.0, reserved=20.0)
        assert b.available == 50.0

    def test_available_never_negative(self):
        b = self._make_budget(total=10.0, used=8.0, reserved=8.0)
        assert b.available == 0.0

    def test_usage_percent_zero_when_empty(self):
        b = self._make_budget(total=100.0)
        assert b.usage_percent == 0.0

    def test_usage_percent_full(self):
        b = self._make_budget(total=100.0, used=100.0)
        assert b.usage_percent == 100.0

    def test_usage_percent_partial(self):
        b = self._make_budget(total=200.0, used=50.0, reserved=50.0)
        assert b.usage_percent == 50.0

    def test_usage_percent_zero_total(self):
        b = self._make_budget(total=0.0)
        assert b.usage_percent == 0.0

    def test_can_allocate_true_when_enough(self):
        b = self._make_budget(total=100.0)
        assert b.can_allocate(50.0) is True

    def test_can_allocate_false_when_insufficient(self):
        b = self._make_budget(total=100.0, used=80.0)
        assert b.can_allocate(30.0) is False

    def test_can_allocate_exact_amount(self):
        b = self._make_budget(total=100.0)
        assert b.can_allocate(100.0) is True

    def test_allocate_success_increases_used(self):
        b = self._make_budget(total=100.0)
        result = b.allocate(40.0)
        assert result is True
        assert b.used == 40.0

    def test_allocate_failure_when_insufficient(self):
        b = self._make_budget(total=100.0, used=90.0)
        result = b.allocate(20.0)
        assert result is False
        assert b.used == 90.0

    def test_reserve_success_increases_reserved(self):
        b = self._make_budget(total=100.0)
        result = b.reserve(30.0)
        assert result is True
        assert b.reserved == 30.0

    def test_reserve_failure_when_insufficient(self):
        b = self._make_budget(total=100.0, used=80.0)
        result = b.reserve(30.0)
        assert result is False
        assert b.reserved == 0.0

    def test_release_decreases_used(self):
        b = self._make_budget(total=100.0, used=60.0)
        b.release(20.0)
        assert b.used == 40.0

    def test_release_does_not_go_below_zero(self):
        b = self._make_budget(total=100.0, used=10.0)
        b.release(50.0)
        assert b.used == 0.0

    def test_release_reservation_decreases_reserved(self):
        b = self._make_budget(total=100.0, reserved=40.0)
        b.release_reservation(15.0)
        assert b.reserved == 25.0

    def test_release_reservation_does_not_go_below_zero(self):
        b = self._make_budget(total=100.0, reserved=5.0)
        b.release_reservation(50.0)
        assert b.reserved == 0.0

    def test_should_reset_returns_false_when_no_reset_at(self):
        b = self._make_budget()
        assert b.should_reset() is False

    def test_should_reset_returns_false_when_future(self):
        b = self._make_budget()
        b.reset_at = datetime.now(UTC) + timedelta(minutes=5)
        assert b.should_reset() is False

    def test_should_reset_returns_true_when_past(self):
        b = self._make_budget()
        b.reset_at = datetime.now(UTC) - timedelta(seconds=1)
        assert b.should_reset() is True


# ---------------------------------------------------------------------------
# ScheduledTask
# ---------------------------------------------------------------------------


class TestScheduledTask:
    def _make_task(self, **kwargs) -> ScheduledTask:
        defaults = {"task_id": "t1", "description": "test task"}
        defaults.update(kwargs)
        return ScheduledTask(**defaults)

    def test_is_ready_no_execute_after(self):
        task = self._make_task()
        assert task.is_ready() is True

    def test_is_ready_execute_after_in_past(self):
        task = self._make_task(execute_after=datetime.now(UTC) - timedelta(seconds=10))
        assert task.is_ready() is True

    def test_is_ready_execute_after_in_future(self):
        task = self._make_task(execute_after=datetime.now(UTC) + timedelta(seconds=60))
        assert task.is_ready() is False

    def test_is_overdue_no_deadline(self):
        task = self._make_task()
        assert task.is_overdue() is False

    def test_is_overdue_deadline_in_future(self):
        task = self._make_task(deadline=datetime.now(UTC) + timedelta(hours=1))
        assert task.is_overdue() is False

    def test_is_overdue_deadline_in_past(self):
        task = self._make_task(deadline=datetime.now(UTC) - timedelta(seconds=1))
        assert task.is_overdue() is True

    def test_can_retry_when_below_max(self):
        task = self._make_task(retry_count=1, max_retries=3)
        assert task.can_retry() is True

    def test_can_retry_at_max_returns_false(self):
        task = self._make_task(retry_count=3, max_retries=3)
        assert task.can_retry() is False

    def test_can_retry_default_max(self):
        task = self._make_task()
        assert task.can_retry() is True

    def test_default_priority_is_normal(self):
        task = self._make_task()
        assert task.priority == SchedulePriority.NORMAL

    def test_default_retry_count_is_zero(self):
        task = self._make_task()
        assert task.retry_count == 0


# ---------------------------------------------------------------------------
# SchedulerMetrics defaults
# ---------------------------------------------------------------------------


class TestSchedulerMetrics:
    def test_all_defaults_are_zero(self):
        m = SchedulerMetrics()
        assert m.tasks_scheduled == 0
        assert m.tasks_executed == 0
        assert m.tasks_delayed == 0
        assert m.tasks_dropped == 0
        assert m.average_wait_ms == 0.0
        assert m.resource_exhaustion_count == 0


# ---------------------------------------------------------------------------
# ResourceScheduler.__init__
# ---------------------------------------------------------------------------


class TestResourceSchedulerInit:
    def test_default_budgets_created(self):
        scheduler = ResourceScheduler()
        assert ResourceType.TOKENS in scheduler._budgets
        assert ResourceType.API_CALLS in scheduler._budgets
        assert ResourceType.CONCURRENT_TASKS in scheduler._budgets

    def test_token_budget_total(self):
        scheduler = ResourceScheduler(token_budget=50000)
        assert scheduler._budgets[ResourceType.TOKENS].total == 50000

    def test_api_call_limit_total(self):
        scheduler = ResourceScheduler(api_call_limit=30)
        assert scheduler._budgets[ResourceType.API_CALLS].total == 30

    def test_max_concurrent_total(self):
        scheduler = ResourceScheduler(max_concurrent=3)
        assert scheduler._budgets[ResourceType.CONCURRENT_TASKS].total == 3

    def test_queue_starts_empty(self):
        scheduler = ResourceScheduler()
        assert scheduler._queue == []

    def test_running_starts_empty(self):
        scheduler = ResourceScheduler()
        assert scheduler._running == {}

    def test_tokens_budget_has_reset_at(self):
        scheduler = ResourceScheduler()
        assert scheduler._budgets[ResourceType.TOKENS].reset_at is not None

    def test_api_calls_budget_has_reset_at(self):
        scheduler = ResourceScheduler()
        assert scheduler._budgets[ResourceType.API_CALLS].reset_at is not None

    def test_concurrent_tasks_budget_has_no_reset_at(self):
        scheduler = ResourceScheduler()
        assert scheduler._budgets[ResourceType.CONCURRENT_TASKS].reset_at is None


# ---------------------------------------------------------------------------
# schedule
# ---------------------------------------------------------------------------


class TestSchedule:
    @pytest.mark.asyncio
    async def test_schedule_creates_task(self):
        scheduler = ResourceScheduler()
        task = await scheduler.schedule("t1", "test task")
        assert task.task_id == "t1"
        assert task.description == "test task"

    @pytest.mark.asyncio
    async def test_schedule_increments_metrics(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task one")
        await scheduler.schedule("t2", "task two")
        assert scheduler._metrics.tasks_scheduled == 2

    @pytest.mark.asyncio
    async def test_schedule_adds_to_queue(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task")
        assert len(scheduler._queue) == 1

    @pytest.mark.asyncio
    async def test_schedule_with_token_requirement(self):
        scheduler = ResourceScheduler()
        task = await scheduler.schedule("t1", "heavy task", token_requirement=5000)
        assert ResourceType.TOKENS in task.resource_requirements
        assert task.resource_requirements[ResourceType.TOKENS] == 5000

    @pytest.mark.asyncio
    async def test_schedule_always_includes_concurrent_and_api_requirements(self):
        scheduler = ResourceScheduler()
        task = await scheduler.schedule("t1", "task")
        assert ResourceType.CONCURRENT_TASKS in task.resource_requirements
        assert ResourceType.API_CALLS in task.resource_requirements

    @pytest.mark.asyncio
    async def test_schedule_inserts_critical_before_normal(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("normal", "normal task", priority=SchedulePriority.NORMAL)
        await scheduler.schedule("critical", "critical task", priority=SchedulePriority.CRITICAL)
        assert scheduler._queue[0].task_id == "critical"

    @pytest.mark.asyncio
    async def test_schedule_with_deadline(self):
        scheduler = ResourceScheduler()
        dl = datetime.now(UTC) + timedelta(hours=1)
        task = await scheduler.schedule("t1", "task", deadline=dl)
        assert task.deadline == dl


# ---------------------------------------------------------------------------
# get_next_task
# ---------------------------------------------------------------------------


class TestGetNextTask:
    @pytest.mark.asyncio
    async def test_returns_none_when_empty(self):
        scheduler = ResourceScheduler()
        result = await scheduler.get_next_task()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_highest_priority_task(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("low", "low task", priority=SchedulePriority.LOW)
        await scheduler.schedule("high", "high task", priority=SchedulePriority.HIGH)
        task = await scheduler.get_next_task()
        assert task is not None
        assert task.task_id == "high"

    @pytest.mark.asyncio
    async def test_removes_task_from_queue(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task")
        await scheduler.get_next_task()
        assert len(scheduler._queue) == 0

    @pytest.mark.asyncio
    async def test_adds_task_to_running(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task")
        task = await scheduler.get_next_task()
        assert task is not None
        assert "t1" in scheduler._running

    @pytest.mark.asyncio
    async def test_allocates_resources_on_dequeue(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task", token_requirement=1000)
        await scheduler.get_next_task()
        tokens_budget = scheduler._budgets[ResourceType.TOKENS]
        assert tokens_budget.used > 0

    @pytest.mark.asyncio
    async def test_skips_not_ready_task(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "deferred task")
        # Manually set execute_after to future
        scheduler._queue[0].execute_after = datetime.now(UTC) + timedelta(hours=1)
        result = await scheduler.get_next_task()
        assert result is None
        assert len(scheduler._queue) == 1

    @pytest.mark.asyncio
    async def test_returns_none_when_resources_exhausted(self):
        scheduler = ResourceScheduler(max_concurrent=1)
        await scheduler.schedule("t1", "first task")
        await scheduler.schedule("t2", "second task")
        # Consume the only concurrent slot
        await scheduler.get_next_task()
        result = await scheduler.get_next_task()
        assert result is None


# ---------------------------------------------------------------------------
# complete_task
# ---------------------------------------------------------------------------


class TestCompleteTask:
    @pytest.mark.asyncio
    async def test_complete_removes_from_running(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task")
        await scheduler.get_next_task()
        await scheduler.complete_task("t1", success=True)
        assert "t1" not in scheduler._running

    @pytest.mark.asyncio
    async def test_complete_increments_tasks_executed(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task")
        await scheduler.get_next_task()
        await scheduler.complete_task("t1", success=True)
        assert scheduler._metrics.tasks_executed == 1

    @pytest.mark.asyncio
    async def test_complete_releases_concurrent_slot(self):
        scheduler = ResourceScheduler(max_concurrent=1)
        await scheduler.schedule("t1", "task")
        await scheduler.get_next_task()
        concurrent_before = scheduler._budgets[ResourceType.CONCURRENT_TASKS].used
        await scheduler.complete_task("t1", success=True)
        concurrent_after = scheduler._budgets[ResourceType.CONCURRENT_TASKS].used
        assert concurrent_after < concurrent_before

    @pytest.mark.asyncio
    async def test_complete_with_actual_tokens_adjusts_token_budget(self):
        scheduler = ResourceScheduler(token_budget=10000)
        await scheduler.schedule("t1", "task", token_requirement=5000)
        await scheduler.get_next_task()
        # Only 3000 tokens were actually used — surplus should be released
        await scheduler.complete_task("t1", success=True, actual_tokens_used=3000)
        tokens_budget = scheduler._budgets[ResourceType.TOKENS]
        # Release is applied to the difference: 5000 - 3000 = 2000 released
        assert tokens_budget.used == 3000

    @pytest.mark.asyncio
    async def test_complete_unknown_task_id_is_noop(self):
        scheduler = ResourceScheduler()
        # Must not raise
        await scheduler.complete_task("nonexistent", success=True)
        assert scheduler._metrics.tasks_executed == 0

    @pytest.mark.asyncio
    async def test_complete_updates_average_wait_ms(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task")
        await scheduler.get_next_task()
        await scheduler.complete_task("t1", success=True)
        assert scheduler._metrics.average_wait_ms >= 0.0


# ---------------------------------------------------------------------------
# retry_task
# ---------------------------------------------------------------------------


class TestRetryTask:
    @pytest.mark.asyncio
    async def test_retry_returns_true_when_requeued(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task")
        await scheduler.get_next_task()
        result = await scheduler.retry_task("t1")
        assert result is True

    @pytest.mark.asyncio
    async def test_retry_increments_retry_count(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task")
        await scheduler.get_next_task()
        await scheduler.retry_task("t1")
        assert scheduler._queue[0].retry_count == 1

    @pytest.mark.asyncio
    async def test_retry_adds_task_back_to_queue(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task")
        await scheduler.get_next_task()
        assert len(scheduler._queue) == 0
        await scheduler.retry_task("t1")
        assert len(scheduler._queue) == 1

    @pytest.mark.asyncio
    async def test_retry_sets_execute_after_in_future(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task")
        await scheduler.get_next_task()
        await scheduler.retry_task("t1")
        assert scheduler._queue[0].execute_after is not None
        assert scheduler._queue[0].execute_after > datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_retry_returns_false_when_max_retries_exceeded(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task")
        await scheduler.get_next_task()
        # Exhaust retries
        scheduler._running["t1"].retry_count = 3
        scheduler._running["t1"].max_retries = 3
        result = await scheduler.retry_task("t1")
        assert result is False

    @pytest.mark.asyncio
    async def test_retry_increments_tasks_dropped_on_max_retries(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task")
        await scheduler.get_next_task()
        scheduler._running["t1"].retry_count = 3
        scheduler._running["t1"].max_retries = 3
        await scheduler.retry_task("t1")
        assert scheduler._metrics.tasks_dropped == 1

    @pytest.mark.asyncio
    async def test_retry_unknown_task_id_returns_false(self):
        scheduler = ResourceScheduler()
        result = await scheduler.retry_task("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_retry_releases_resources(self):
        scheduler = ResourceScheduler(max_concurrent=1)
        await scheduler.schedule("t1", "task")
        await scheduler.get_next_task()
        concurrent_used_before = scheduler._budgets[ResourceType.CONCURRENT_TASKS].used
        await scheduler.retry_task("t1")
        concurrent_used_after = scheduler._budgets[ResourceType.CONCURRENT_TASKS].used
        assert concurrent_used_after < concurrent_used_before


# ---------------------------------------------------------------------------
# check_budget
# ---------------------------------------------------------------------------


class TestCheckBudget:
    def test_returns_token_budget(self):
        scheduler = ResourceScheduler(token_budget=80000)
        budget = scheduler.check_budget(ResourceType.TOKENS)
        assert budget is not None
        assert budget.total == 80000

    def test_returns_api_calls_budget(self):
        scheduler = ResourceScheduler(api_call_limit=45)
        budget = scheduler.check_budget(ResourceType.API_CALLS)
        assert budget.total == 45

    def test_returns_concurrent_tasks_budget(self):
        scheduler = ResourceScheduler(max_concurrent=7)
        budget = scheduler.check_budget(ResourceType.CONCURRENT_TASKS)
        assert budget.total == 7

    def test_returns_none_for_untracked_resource(self):
        scheduler = ResourceScheduler()
        budget = scheduler.check_budget(ResourceType.TIME)
        assert budget is None


# ---------------------------------------------------------------------------
# get_queue_status
# ---------------------------------------------------------------------------


class TestGetQueueStatus:
    @pytest.mark.asyncio
    async def test_empty_scheduler_status(self):
        scheduler = ResourceScheduler()
        status = scheduler.get_queue_status()
        assert status["queue_length"] == 0
        assert status["running_tasks"] == 0
        assert status["by_priority"] == {}

    @pytest.mark.asyncio
    async def test_queue_length_reflects_scheduled_tasks(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task one")
        await scheduler.schedule("t2", "task two")
        status = scheduler.get_queue_status()
        assert status["queue_length"] == 2

    @pytest.mark.asyncio
    async def test_running_tasks_count_after_dequeue(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task")
        await scheduler.get_next_task()
        status = scheduler.get_queue_status()
        assert status["running_tasks"] == 1

    @pytest.mark.asyncio
    async def test_by_priority_groups_correctly(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task", priority=SchedulePriority.HIGH)
        await scheduler.schedule("t2", "task", priority=SchedulePriority.HIGH)
        await scheduler.schedule("t3", "task", priority=SchedulePriority.LOW)
        status = scheduler.get_queue_status()
        assert status["by_priority"]["high"] == 2
        assert status["by_priority"]["low"] == 1

    def test_budgets_included_in_status(self):
        scheduler = ResourceScheduler(token_budget=10000)
        status = scheduler.get_queue_status()
        assert "budgets" in status
        assert "tokens" in status["budgets"]
        assert status["budgets"]["tokens"]["total"] == 10000


# ---------------------------------------------------------------------------
# get_metrics
# ---------------------------------------------------------------------------


class TestGetMetrics:
    def test_initial_metrics_all_zero(self):
        scheduler = ResourceScheduler()
        metrics = scheduler.get_metrics()
        assert metrics["tasks_scheduled"] == 0
        assert metrics["tasks_executed"] == 0
        assert metrics["tasks_delayed"] == 0
        assert metrics["tasks_dropped"] == 0
        assert metrics["average_wait_ms"] == 0.0
        assert metrics["resource_exhaustion_count"] == 0

    @pytest.mark.asyncio
    async def test_metrics_update_after_schedule(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task")
        metrics = scheduler.get_metrics()
        assert metrics["tasks_scheduled"] == 1

    @pytest.mark.asyncio
    async def test_metrics_update_after_complete(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task")
        await scheduler.get_next_task()
        await scheduler.complete_task("t1", success=True)
        metrics = scheduler.get_metrics()
        assert metrics["tasks_executed"] == 1

    @pytest.mark.asyncio
    async def test_metrics_update_dropped_on_max_retry(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("t1", "task")
        await scheduler.get_next_task()
        scheduler._running["t1"].retry_count = 3
        scheduler._running["t1"].max_retries = 3
        await scheduler.retry_task("t1")
        metrics = scheduler.get_metrics()
        assert metrics["tasks_dropped"] == 1


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------


class TestPriorityOrdering:
    @pytest.mark.asyncio
    async def test_critical_before_high(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("high", "high", priority=SchedulePriority.HIGH)
        await scheduler.schedule("critical", "critical", priority=SchedulePriority.CRITICAL)
        assert scheduler._queue[0].task_id == "critical"

    @pytest.mark.asyncio
    async def test_high_before_normal(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("normal", "normal", priority=SchedulePriority.NORMAL)
        await scheduler.schedule("high", "high", priority=SchedulePriority.HIGH)
        assert scheduler._queue[0].task_id == "high"

    @pytest.mark.asyncio
    async def test_normal_before_low(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("low", "low", priority=SchedulePriority.LOW)
        await scheduler.schedule("normal", "normal", priority=SchedulePriority.NORMAL)
        assert scheduler._queue[0].task_id == "normal"

    @pytest.mark.asyncio
    async def test_low_before_background(self):
        scheduler = ResourceScheduler()
        await scheduler.schedule("bg", "background", priority=SchedulePriority.BACKGROUND)
        await scheduler.schedule("low", "low", priority=SchedulePriority.LOW)
        assert scheduler._queue[0].task_id == "low"

    @pytest.mark.asyncio
    async def test_full_priority_order(self):
        scheduler = ResourceScheduler()
        for label, pri in [
            ("bg", SchedulePriority.BACKGROUND),
            ("low", SchedulePriority.LOW),
            ("normal", SchedulePriority.NORMAL),
            ("high", SchedulePriority.HIGH),
            ("critical", SchedulePriority.CRITICAL),
        ]:
            await scheduler.schedule(label, label, priority=pri)
        ids = [t.task_id for t in scheduler._queue]
        assert ids == ["critical", "high", "normal", "low", "bg"]

    @pytest.mark.asyncio
    async def test_same_priority_earlier_deadline_wins(self):
        scheduler = ResourceScheduler()
        later = datetime.now(UTC) + timedelta(hours=2)
        earlier = datetime.now(UTC) + timedelta(hours=1)
        await scheduler.schedule("later", "later", priority=SchedulePriority.NORMAL, deadline=later)
        await scheduler.schedule("earlier", "earlier", priority=SchedulePriority.NORMAL, deadline=earlier)
        assert scheduler._queue[0].task_id == "earlier"


# ---------------------------------------------------------------------------
# _reset_budgets_if_needed
# ---------------------------------------------------------------------------


class TestResetBudgetsIfNeeded:
    def test_resets_expired_budget_used_and_reserved(self):
        scheduler = ResourceScheduler()
        token_budget = scheduler._budgets[ResourceType.TOKENS]
        token_budget.used = 5000.0
        token_budget.reserved = 1000.0
        # Push reset_at into the past
        token_budget.reset_at = datetime.now(UTC) - timedelta(seconds=1)
        scheduler._reset_budgets_if_needed()
        assert token_budget.used == 0
        assert token_budget.reserved == 0

    def test_does_not_reset_future_budget(self):
        scheduler = ResourceScheduler()
        token_budget = scheduler._budgets[ResourceType.TOKENS]
        token_budget.used = 3000.0
        token_budget.reset_at = datetime.now(UTC) + timedelta(minutes=5)
        scheduler._reset_budgets_if_needed()
        assert token_budget.used == 3000.0

    def test_reset_sets_new_reset_at_one_minute_in_future(self):
        scheduler = ResourceScheduler()
        token_budget = scheduler._budgets[ResourceType.TOKENS]
        token_budget.reset_at = datetime.now(UTC) - timedelta(seconds=1)
        before = datetime.now(UTC)
        scheduler._reset_budgets_if_needed()
        assert token_budget.reset_at > before
        assert token_budget.reset_at <= before + timedelta(minutes=1, seconds=1)

    def test_no_reset_at_budget_is_untouched(self):
        scheduler = ResourceScheduler()
        concurrent_budget = scheduler._budgets[ResourceType.CONCURRENT_TASKS]
        concurrent_budget.used = 2.0
        scheduler._reset_budgets_if_needed()
        assert concurrent_budget.used == 2.0


# ---------------------------------------------------------------------------
# Singleton helpers: get_resource_scheduler and reset_resource_scheduler
# ---------------------------------------------------------------------------


class TestSingleton:
    def setup_method(self):
        reset_resource_scheduler()

    def teardown_method(self):
        reset_resource_scheduler()

    def test_get_returns_instance(self):
        scheduler = get_resource_scheduler()
        assert isinstance(scheduler, ResourceScheduler)

    def test_get_returns_same_instance_on_second_call(self):
        s1 = get_resource_scheduler()
        s2 = get_resource_scheduler()
        assert s1 is s2

    def test_reset_clears_singleton(self):
        s1 = get_resource_scheduler()
        reset_resource_scheduler()
        s2 = get_resource_scheduler()
        assert s1 is not s2

    def test_get_with_custom_params(self):
        scheduler = get_resource_scheduler(token_budget=200000, api_call_limit=120, max_concurrent=10)
        assert scheduler._budgets[ResourceType.TOKENS].total == 200000
        assert scheduler._budgets[ResourceType.API_CALLS].total == 120
        assert scheduler._budgets[ResourceType.CONCURRENT_TASKS].total == 10

    def test_second_call_ignores_params(self):
        get_resource_scheduler(token_budget=1000)
        scheduler = get_resource_scheduler(token_budget=9999)
        # First call wins; second call params are ignored
        assert scheduler._budgets[ResourceType.TOKENS].total == 1000
