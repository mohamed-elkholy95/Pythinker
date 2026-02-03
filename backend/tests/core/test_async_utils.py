"""Tests for Python 3.11+ TaskGroup utilities.

Tests cover:
- Basic gather_with_taskgroup functionality
- Exception handling and propagation
- return_exceptions mode
- Timeout handling
- Concurrency limiting
- TaskGroupExecutor class
- Compatibility wrapper
"""

import asyncio
from datetime import datetime

import pytest

from app.core.async_utils import (
    TaskGroupExecutor,
    TaskGroupResult,
    gather_compat,
    gather_with_taskgroup,
    gather_with_taskgroup_detailed,
    gather_with_timeout,
    map_with_taskgroup,
)


class TestGatherWithTaskgroup:
    """Tests for gather_with_taskgroup function."""

    @pytest.mark.asyncio
    async def test_basic_execution(self):
        """Test basic concurrent execution returns correct results."""

        async def task(n: int) -> int:
            await asyncio.sleep(0.01)
            return n * 2

        results = await gather_with_taskgroup(task(1), task(2), task(3))

        assert results == [2, 4, 6]

    @pytest.mark.asyncio
    async def test_empty_coroutines(self):
        """Test with no coroutines returns empty list."""
        results = await gather_with_taskgroup()
        assert results == []

    @pytest.mark.asyncio
    async def test_single_coroutine(self):
        """Test with single coroutine."""

        async def task() -> str:
            return "done"

        results = await gather_with_taskgroup(task())
        assert results == ["done"]

    @pytest.mark.asyncio
    async def test_order_preservation(self):
        """Test that results maintain order of input coroutines."""

        async def task(n: int) -> int:
            # Varying delays to test order preservation
            await asyncio.sleep(0.05 - n * 0.01)
            return n

        results = await gather_with_taskgroup(task(1), task(2), task(3), task(4))

        # Should be in input order, not completion order
        assert results == [1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_exception_raises_by_default(self):
        """Test that exceptions are raised by default."""

        async def failing_task():
            raise ValueError("Task failed")

        async def success_task():
            return "ok"

        with pytest.raises(ExceptionGroup) as exc_info:
            await gather_with_taskgroup(success_task(), failing_task())

        assert len(exc_info.value.exceptions) == 1
        assert isinstance(exc_info.value.exceptions[0], ValueError)

    @pytest.mark.asyncio
    async def test_return_exceptions_true(self):
        """Test return_exceptions=True returns exceptions in results."""

        async def failing_task():
            raise ValueError("Task failed")

        async def success_task():
            return "ok"

        results = await gather_with_taskgroup(success_task(), failing_task(), return_exceptions=True)

        assert results[0] == "ok"
        assert isinstance(results[1], ValueError)

    @pytest.mark.asyncio
    async def test_multiple_exceptions_return_exceptions(self):
        """Test multiple failures with return_exceptions=True."""

        async def task(n: int):
            if n % 2 == 0:
                raise ValueError(f"Failed: {n}")
            return n

        results = await gather_with_taskgroup(task(1), task(2), task(3), task(4), return_exceptions=True)

        assert results[0] == 1  # Success
        assert isinstance(results[1], ValueError)  # Failure
        assert results[2] == 3  # Success
        assert isinstance(results[3], ValueError)  # Failure

    @pytest.mark.asyncio
    async def test_cancellation_propagation(self):
        """Test that cancellation is properly propagated."""
        started = []
        completed = []

        async def slow_task(n: int):
            started.append(n)
            await asyncio.sleep(1)
            completed.append(n)
            return n

        async def run_and_cancel():
            task = asyncio.create_task(gather_with_taskgroup(slow_task(1), slow_task(2), slow_task(3)))
            await asyncio.sleep(0.05)  # Let tasks start
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await run_and_cancel()

        # Tasks should have started but not completed
        assert len(started) == 3
        assert len(completed) == 0


class TestGatherWithTaskgroupDetailed:
    """Tests for gather_with_taskgroup_detailed function."""

    @pytest.mark.asyncio
    async def test_returns_taskgroup_result(self):
        """Test that function returns TaskGroupResult."""

        async def task(n: int) -> int:
            return n

        result = await gather_with_taskgroup_detailed(task(1), task(2))

        assert isinstance(result, TaskGroupResult)
        assert result.results == [1, 2]
        assert result.successful_count == 2
        assert result.failed_count == 0
        assert result.total_count == 2
        assert result.all_successful is True

    @pytest.mark.asyncio
    async def test_tracks_execution_time(self):
        """Test that execution time is tracked."""

        async def task():
            await asyncio.sleep(0.05)
            return "done"

        result = await gather_with_taskgroup_detailed(task())

        assert result.execution_time_ms >= 40  # At least 40ms
        assert result.start_time <= result.end_time

    @pytest.mark.asyncio
    async def test_mixed_success_failure(self):
        """Test with mixed success and failure."""

        async def success():
            return "ok"

        async def failure():
            raise ValueError("fail")

        result = await gather_with_taskgroup_detailed(success(), failure(), return_exceptions=True)

        assert result.successful_count == 1
        assert result.failed_count == 1
        assert result.any_successful is True
        assert result.all_successful is False

    @pytest.mark.asyncio
    async def test_get_successful_results(self):
        """Test get_successful_results filters out exceptions."""

        async def task(n: int):
            if n == 2:
                raise ValueError()
            return n

        result = await gather_with_taskgroup_detailed(task(1), task(2), task(3), return_exceptions=True)

        successful = result.get_successful_results()
        assert successful == [1, 3]

    @pytest.mark.asyncio
    async def test_empty_input(self):
        """Test with empty input."""
        result = await gather_with_taskgroup_detailed()

        assert result.results == []
        assert result.total_count == 0
        assert result.all_successful is True


class TestGatherWithTimeout:
    """Tests for gather_with_timeout function."""

    @pytest.mark.asyncio
    async def test_completes_within_timeout(self):
        """Test tasks complete within timeout."""

        async def fast_task():
            await asyncio.sleep(0.01)
            return "done"

        results = await gather_with_timeout(fast_task(), fast_task(), timeout=1.0)

        assert results == ["done", "done"]

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        """Test timeout raises TimeoutError by default."""

        async def slow_task():
            await asyncio.sleep(10)
            return "done"

        with pytest.raises(asyncio.TimeoutError):
            await gather_with_timeout(slow_task(), timeout=0.05)

    @pytest.mark.asyncio
    async def test_timeout_return_exceptions(self):
        """Test timeout with return_exceptions=True."""

        async def slow_task():
            await asyncio.sleep(10)
            return "done"

        results = await gather_with_timeout(slow_task(), slow_task(), timeout=0.05, return_exceptions=True)

        assert len(results) == 2
        assert all(isinstance(r, asyncio.TimeoutError) for r in results)


class TestMapWithTaskgroup:
    """Tests for map_with_taskgroup function."""

    @pytest.mark.asyncio
    async def test_basic_map(self):
        """Test basic mapping over items."""

        async def double(n: int) -> int:
            return n * 2

        results = await map_with_taskgroup(double, [1, 2, 3, 4, 5])

        assert results == [2, 4, 6, 8, 10]

    @pytest.mark.asyncio
    async def test_empty_items(self):
        """Test with empty items list."""

        async def task(x):
            return x

        results = await map_with_taskgroup(task, [])
        assert results == []

    @pytest.mark.asyncio
    async def test_concurrency_limit(self):
        """Test concurrency limiting with semaphore."""
        concurrent_count = 0
        max_concurrent = 0

        async def track_concurrency(n: int) -> int:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.02)
            concurrent_count -= 1
            return n

        results = await map_with_taskgroup(track_concurrency, list(range(10)), max_concurrency=3)

        assert results == list(range(10))
        assert max_concurrent <= 3

    @pytest.mark.asyncio
    async def test_return_exceptions(self):
        """Test map with return_exceptions."""

        async def task(n: int):
            if n == 2:
                raise ValueError("fail")
            return n

        results = await map_with_taskgroup(task, [1, 2, 3], return_exceptions=True)

        assert results[0] == 1
        assert isinstance(results[1], ValueError)
        assert results[2] == 3


class TestTaskGroupExecutor:
    """Tests for TaskGroupExecutor class."""

    @pytest.mark.asyncio
    async def test_basic_execution(self):
        """Test basic executor usage."""

        async def task(n: int) -> int:
            return n

        executor = TaskGroupExecutor()
        results = await executor.run(task(1), task(2), task(3))

        assert results == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_statistics_tracking(self):
        """Test executor tracks statistics."""

        async def success():
            return "ok"

        async def failure():
            raise ValueError()

        executor = TaskGroupExecutor(return_exceptions=True)
        await executor.run(success(), success(), failure())

        stats = executor.stats
        assert stats["total_runs"] == 1
        assert stats["total_tasks"] == 3
        assert stats["total_successes"] == 2
        assert stats["total_failures"] == 1

    @pytest.mark.asyncio
    async def test_multiple_runs_accumulate_stats(self):
        """Test statistics accumulate across runs."""

        async def task():
            return "ok"

        executor = TaskGroupExecutor()
        await executor.run(task(), task())
        await executor.run(task())

        stats = executor.stats
        assert stats["total_runs"] == 2
        assert stats["total_tasks"] == 3

    @pytest.mark.asyncio
    async def test_reset_stats(self):
        """Test statistics reset."""

        async def task():
            return "ok"

        executor = TaskGroupExecutor()
        await executor.run(task())
        executor.reset_stats()

        stats = executor.stats
        assert stats["total_runs"] == 0
        assert stats["total_tasks"] == 0

    @pytest.mark.asyncio
    async def test_concurrency_limit(self):
        """Test executor with concurrency limit."""
        concurrent_count = 0
        max_concurrent = 0

        async def track_concurrency():
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.02)
            concurrent_count -= 1
            return "done"

        executor = TaskGroupExecutor(max_concurrency=2)
        await executor.run(*[track_concurrency() for _ in range(5)])

        assert max_concurrent <= 2

    @pytest.mark.asyncio
    async def test_timeout(self):
        """Test executor with timeout."""

        async def slow_task():
            await asyncio.sleep(10)
            return "done"

        executor = TaskGroupExecutor(timeout=0.05, return_exceptions=True)
        results = await executor.run(slow_task(), slow_task())

        assert all(isinstance(r, asyncio.TimeoutError) for r in results)


class TestGatherCompat:
    """Tests for gather_compat compatibility wrapper."""

    @pytest.mark.asyncio
    async def test_uses_asyncio_gather_by_default(self):
        """Test uses asyncio.gather when use_taskgroup=False."""

        async def task(n: int) -> int:
            return n

        results = await gather_compat(task(1), task(2), use_taskgroup=False)
        assert results == [1, 2]

    @pytest.mark.asyncio
    async def test_uses_taskgroup_when_enabled(self):
        """Test uses TaskGroup when use_taskgroup=True."""

        async def task(n: int) -> int:
            return n

        results = await gather_compat(task(1), task(2), use_taskgroup=True)
        assert results == [1, 2]

    @pytest.mark.asyncio
    async def test_return_exceptions_with_taskgroup(self):
        """Test return_exceptions works with TaskGroup."""

        async def failing():
            raise ValueError()

        async def success():
            return "ok"

        results = await gather_compat(success(), failing(), return_exceptions=True, use_taskgroup=True)

        assert results[0] == "ok"
        assert isinstance(results[1], ValueError)

    @pytest.mark.asyncio
    async def test_return_exceptions_with_gather(self):
        """Test return_exceptions works with asyncio.gather."""

        async def failing():
            raise ValueError()

        async def success():
            return "ok"

        results = await gather_compat(success(), failing(), return_exceptions=True, use_taskgroup=False)

        assert results[0] == "ok"
        assert isinstance(results[1], ValueError)


class TestTaskGroupResult:
    """Tests for TaskGroupResult dataclass."""

    def test_all_successful(self):
        """Test all_successful property."""
        result = TaskGroupResult(
            results=[1, 2, 3],
            errors=[],
            successful_count=3,
            failed_count=0,
            total_count=3,
        )
        assert result.all_successful is True

        result_with_failure = TaskGroupResult(
            results=[1, ValueError()],
            errors=[ValueError()],
            successful_count=1,
            failed_count=1,
            total_count=2,
        )
        assert result_with_failure.all_successful is False

    def test_any_successful(self):
        """Test any_successful property."""
        result = TaskGroupResult(
            results=[ValueError()],
            errors=[ValueError()],
            successful_count=0,
            failed_count=1,
            total_count=1,
        )
        assert result.any_successful is False

        result_with_success = TaskGroupResult(
            results=[1, ValueError()],
            errors=[ValueError()],
            successful_count=1,
            failed_count=1,
            total_count=2,
        )
        assert result_with_success.any_successful is True


class TestConcurrencyBehavior:
    """Tests for concurrent execution behavior."""

    @pytest.mark.asyncio
    async def test_true_parallelism(self):
        """Test that tasks run in parallel, not sequentially."""
        start = datetime.now()

        async def sleep_task():
            await asyncio.sleep(0.1)
            return "done"

        # 5 tasks of 100ms should complete in ~100ms if parallel
        results = await gather_with_taskgroup(*[sleep_task() for _ in range(5)])

        elapsed = (datetime.now() - start).total_seconds()

        assert len(results) == 5
        # Should be around 100ms, not 500ms
        assert elapsed < 0.3

    @pytest.mark.asyncio
    async def test_error_in_one_doesnt_block_others(self):
        """Test that one error doesn't prevent other results."""
        results_collected = []

        async def task(n: int):
            await asyncio.sleep(0.02)
            if n == 2:
                raise ValueError()
            results_collected.append(n)
            return n

        # With return_exceptions, all tasks should complete
        await gather_with_taskgroup(task(1), task(2), task(3), return_exceptions=True)

        # Tasks 1 and 3 should have completed
        assert 1 in results_collected
        assert 3 in results_collected
