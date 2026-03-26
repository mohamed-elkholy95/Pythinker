"""Tests for timing utilities: TimingResult, TimingStats, TimingRegistry, and decorators."""

import time

import pytest

from app.infrastructure.observability.timing import (
    TimingRegistry,
    TimingResult,
    TimingStats,
    get_timing_stats,
    timed,
    timed_block,
    timed_block_sync,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Reset TimingRegistry before each test."""
    TimingRegistry.reset()
    yield
    TimingRegistry.reset()


# ─────────────────────────────────────────────────────────────
# TimingResult
# ─────────────────────────────────────────────────────────────


class TestTimingResult:
    def test_context_manager_success(self):
        result = TimingResult(name="test")
        with result:
            time.sleep(0.01)
        assert result.duration_ms > 0
        assert result.success is True
        assert result.error is None

    def test_context_manager_exception(self):
        result = TimingResult(name="test")
        with pytest.raises(ValueError):
            with result:
                raise ValueError("boom")
        assert result.success is False
        assert result.error == "boom"
        assert result.duration_ms > 0

    def test_metadata_default_empty(self):
        result = TimingResult(name="test")
        assert result.metadata == {}


# ─────────────────────────────────────────────────────────────
# TimingStats
# ─────────────────────────────────────────────────────────────


class TestTimingStats:
    def test_empty_stats(self):
        stats = TimingStats(name="test")
        assert stats.count == 0
        assert stats.avg_ms == 0.0
        assert stats.success_rate == 1.0
        assert stats.p50_ms == 0.0
        assert stats.p95_ms == 0.0
        assert stats.p99_ms == 0.0

    def test_single_record(self):
        stats = TimingStats(name="test")
        stats.record(100.0)
        assert stats.count == 1
        assert stats.total_ms == 100.0
        assert stats.avg_ms == 100.0
        assert stats.min_ms == 100.0
        assert stats.max_ms == 100.0
        assert stats.success_count == 1
        assert stats.error_count == 0
        assert stats.success_rate == 1.0

    def test_multiple_records(self):
        stats = TimingStats(name="test")
        stats.record(100.0)
        stats.record(200.0)
        stats.record(300.0)
        assert stats.count == 3
        assert stats.total_ms == 600.0
        assert stats.avg_ms == 200.0
        assert stats.min_ms == 100.0
        assert stats.max_ms == 300.0

    def test_error_record(self):
        stats = TimingStats(name="test")
        stats.record(50.0, success=True)
        stats.record(60.0, success=False)
        assert stats.success_count == 1
        assert stats.error_count == 1
        assert stats.success_rate == 0.5

    def test_p50(self):
        stats = TimingStats(name="test")
        for val in [10, 20, 30, 40, 50]:
            stats.record(float(val))
        assert stats.p50_ms == 30.0

    def test_p95(self):
        stats = TimingStats(name="test")
        for val in range(1, 101):
            stats.record(float(val))
        assert stats.p95_ms >= 95.0

    def test_p99(self):
        stats = TimingStats(name="test")
        for val in range(1, 101):
            stats.record(float(val))
        assert stats.p99_ms >= 99.0

    def test_duration_buffer_limit(self):
        stats = TimingStats(name="test")
        for i in range(1100):
            stats.record(float(i))
        assert len(stats._durations) == 1000

    def test_to_dict(self):
        stats = TimingStats(name="test")
        stats.record(100.0)
        stats.record(200.0, success=False)
        d = stats.to_dict()
        assert d["name"] == "test"
        assert d["count"] == 2
        assert d["avg_ms"] == 150.0
        assert d["min_ms"] == 100.0
        assert d["max_ms"] == 200.0
        assert d["error_count"] == 1
        assert d["success_rate"] == 0.5

    def test_to_dict_empty_min(self):
        stats = TimingStats(name="test")
        d = stats.to_dict()
        assert d["min_ms"] == 0  # inf converted to 0


# ─────────────────────────────────────────────────────────────
# TimingRegistry
# ─────────────────────────────────────────────────────────────


class TestTimingRegistry:
    def test_record_and_get(self):
        TimingRegistry.record("op1", 50.0)
        stats = TimingRegistry.get_stats("op1")
        assert stats is not None
        assert stats.count == 1

    def test_missing_stats_returns_none(self):
        assert TimingRegistry.get_stats("nonexistent") is None

    def test_get_all_stats(self):
        TimingRegistry.record("op1", 10.0)
        TimingRegistry.record("op2", 20.0)
        all_stats = TimingRegistry.get_all_stats()
        assert "op1" in all_stats
        assert "op2" in all_stats

    def test_reset_specific(self):
        TimingRegistry.record("op1", 10.0)
        TimingRegistry.record("op2", 20.0)
        TimingRegistry.reset("op1")
        assert TimingRegistry.get_stats("op1") is None
        assert TimingRegistry.get_stats("op2") is not None

    def test_reset_all(self):
        TimingRegistry.record("op1", 10.0)
        TimingRegistry.record("op2", 20.0)
        TimingRegistry.reset()
        assert TimingRegistry.get_all_stats() == {}

    def test_reset_nonexistent_is_safe(self):
        TimingRegistry.reset("nope")  # Should not raise


# ─────────────────────────────────────────────────────────────
# @timed decorator
# ─────────────────────────────────────────────────────────────


class TestTimedDecorator:
    async def test_async_decorator_records(self):
        @timed("test_async_op")
        async def my_op():
            return 42

        result = await my_op()
        assert result == 42
        stats = TimingRegistry.get_stats("test_async_op")
        assert stats is not None
        assert stats.count == 1
        assert stats.success_count == 1

    async def test_async_decorator_records_failure(self):
        @timed("test_async_fail")
        async def my_op():
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            await my_op()
        stats = TimingRegistry.get_stats("test_async_fail")
        assert stats.error_count == 1

    def test_sync_decorator_records(self):
        @timed("test_sync_op")
        def my_op():
            return 99

        result = my_op()
        assert result == 99
        stats = TimingRegistry.get_stats("test_sync_op")
        assert stats is not None
        assert stats.count == 1

    def test_sync_decorator_records_failure(self):
        @timed("test_sync_fail")
        def my_op():
            raise ValueError("oops")

        with pytest.raises(ValueError):
            my_op()
        stats = TimingRegistry.get_stats("test_sync_fail")
        assert stats.error_count == 1

    async def test_decorator_default_name(self):
        @timed()
        async def custom_function_name():
            return True

        await custom_function_name()
        stats = TimingRegistry.get_stats("custom_function_name")
        assert stats is not None

    def test_decorator_no_record(self):
        @timed("no_record_op", record_stats=False)
        def my_op():
            return 1

        my_op()
        assert TimingRegistry.get_stats("no_record_op") is None


# ─────────────────────────────────────────────────────────────
# timed_block async context manager
# ─────────────────────────────────────────────────────────────


class TestTimedBlock:
    async def test_success(self):
        async with timed_block("block_op") as timer:
            pass
        assert timer.duration_ms >= 0
        assert timer.success is True
        stats = TimingRegistry.get_stats("block_op")
        assert stats.count == 1

    async def test_failure(self):
        with pytest.raises(ValueError):
            async with timed_block("block_fail") as timer:
                raise ValueError("boom")
        assert timer.success is False
        stats = TimingRegistry.get_stats("block_fail")
        assert stats.error_count == 1

    async def test_no_record(self):
        async with timed_block("no_rec", record_stats=False):
            pass
        assert TimingRegistry.get_stats("no_rec") is None


# ─────────────────────────────────────────────────────────────
# timed_block_sync context manager
# ─────────────────────────────────────────────────────────────


class TestTimedBlockSync:
    def test_success(self):
        with timed_block_sync("sync_block") as timer:
            pass
        assert timer.duration_ms >= 0
        assert timer.success is True

    def test_failure(self):
        with pytest.raises(RuntimeError):
            with timed_block_sync("sync_fail") as timer:
                raise RuntimeError("error")
        assert timer.success is False

    def test_no_record(self):
        with timed_block_sync("no_rec_sync", record_stats=False):
            pass
        assert TimingRegistry.get_stats("no_rec_sync") is None


# ─────────────────────────────────────────────────────────────
# get_timing_stats convenience function
# ─────────────────────────────────────────────────────────────


class TestGetTimingStats:
    def test_returns_all_stats(self):
        TimingRegistry.record("x", 1.0)
        result = get_timing_stats()
        assert "x" in result
        assert result["x"]["count"] == 1
