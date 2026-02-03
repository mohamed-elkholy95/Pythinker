"""Performance Timing Utilities.

Provides decorators and context managers for measuring and logging
execution time of operations.

Usage:
    # As decorator
    @timed("database_query")
    async def query_database():
        ...

    # As context manager
    async with timed_block("llm_call") as timer:
        result = await llm.ask(...)
    print(f"Took {timer.duration_ms}ms")

    # With threshold warning
    @timed("slow_operation", threshold_ms=1000)
    async def potentially_slow():
        ...
"""

import asyncio
import functools
import logging
import time
from collections.abc import Callable
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Any, ClassVar, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class TimingResult:
    """Result of a timing measurement."""

    name: str
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        if exc_type is not None:
            self.success = False
            self.error = str(exc_val)
        return False


@dataclass
class TimingStats:
    """Aggregated timing statistics."""

    name: str
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0
    success_count: int = 0
    error_count: int = 0
    _durations: list[float] = field(default_factory=list)

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count > 0 else 0.0

    @property
    def success_rate(self) -> float:
        return self.success_count / self.count if self.count > 0 else 1.0

    @property
    def p50_ms(self) -> float:
        """Median duration."""
        if not self._durations:
            return 0.0
        sorted_d = sorted(self._durations)
        return sorted_d[len(sorted_d) // 2]

    @property
    def p95_ms(self) -> float:
        """95th percentile duration."""
        if not self._durations:
            return 0.0
        sorted_d = sorted(self._durations)
        idx = int(len(sorted_d) * 0.95)
        return sorted_d[min(idx, len(sorted_d) - 1)]

    @property
    def p99_ms(self) -> float:
        """99th percentile duration."""
        if not self._durations:
            return 0.0
        sorted_d = sorted(self._durations)
        idx = int(len(sorted_d) * 0.99)
        return sorted_d[min(idx, len(sorted_d) - 1)]

    def record(self, duration_ms: float, success: bool = True) -> None:
        """Record a timing measurement."""
        self.count += 1
        self.total_ms += duration_ms
        self.min_ms = min(self.min_ms, duration_ms)
        self.max_ms = max(self.max_ms, duration_ms)

        if success:
            self.success_count += 1
        else:
            self.error_count += 1

        # Keep last 1000 durations for percentile calculation
        self._durations.append(duration_ms)
        if len(self._durations) > 1000:
            self._durations.pop(0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "count": self.count,
            "total_ms": round(self.total_ms, 2),
            "avg_ms": round(self.avg_ms, 2),
            "min_ms": round(self.min_ms, 2) if self.min_ms != float("inf") else 0,
            "max_ms": round(self.max_ms, 2),
            "p50_ms": round(self.p50_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
            "success_rate": round(self.success_rate, 4),
            "error_count": self.error_count,
        }


class TimingRegistry:
    """Registry for collecting timing statistics."""

    _stats: ClassVar[dict[str, TimingStats]] = {}

    @classmethod
    def record(
        cls,
        name: str,
        duration_ms: float,
        success: bool = True,
    ) -> None:
        """Record a timing measurement."""
        if name not in cls._stats:
            cls._stats[name] = TimingStats(name=name)
        cls._stats[name].record(duration_ms, success)

    @classmethod
    def get_stats(cls, name: str) -> TimingStats | None:
        """Get stats for a specific operation."""
        return cls._stats.get(name)

    @classmethod
    def get_all_stats(cls) -> dict[str, dict[str, Any]]:
        """Get stats for all operations."""
        return {name: stats.to_dict() for name, stats in cls._stats.items()}

    @classmethod
    def reset(cls, name: str | None = None) -> None:
        """Reset stats for one or all operations."""
        if name:
            if name in cls._stats:
                del cls._stats[name]
        else:
            cls._stats.clear()


def timed(
    name: str | None = None,
    threshold_ms: float | None = None,
    log_level: int = logging.DEBUG,
    record_stats: bool = True,
) -> Callable:
    """Decorator to measure and log execution time.

    Args:
        name: Operation name (defaults to function name)
        threshold_ms: Log warning if duration exceeds this
        log_level: Log level for timing messages
        record_stats: Whether to record in TimingRegistry

    Returns:
        Decorated function
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        operation_name = name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            start_time = time.perf_counter()
            success = True
            error_msg = None

            try:
                return await func(*args, **kwargs)
            except Exception as e:
                success = False
                error_msg = str(e)
                raise
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000

                if record_stats:
                    TimingRegistry.record(operation_name, duration_ms, success)

                # Log based on threshold and success
                if not success:
                    logger.warning(f"{operation_name} failed in {duration_ms:.2f}ms: {error_msg}")
                elif threshold_ms and duration_ms > threshold_ms:
                    logger.warning(f"{operation_name} exceeded threshold: {duration_ms:.2f}ms > {threshold_ms}ms")
                else:
                    logger.log(log_level, f"{operation_name} completed in {duration_ms:.2f}ms")

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            start_time = time.perf_counter()
            success = True
            error_msg = None

            try:
                return func(*args, **kwargs)
            except Exception as e:
                success = False
                error_msg = str(e)
                raise
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000

                if record_stats:
                    TimingRegistry.record(operation_name, duration_ms, success)

                if not success:
                    logger.warning(f"{operation_name} failed in {duration_ms:.2f}ms: {error_msg}")
                elif threshold_ms and duration_ms > threshold_ms:
                    logger.warning(f"{operation_name} exceeded threshold: {duration_ms:.2f}ms > {threshold_ms}ms")
                else:
                    logger.log(log_level, f"{operation_name} completed in {duration_ms:.2f}ms")

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


@asynccontextmanager
async def timed_block(
    name: str,
    threshold_ms: float | None = None,
    record_stats: bool = True,
):
    """Async context manager for timing a code block.

    Usage:
        async with timed_block("database_query") as timer:
            result = await db.query(...)
        print(f"Query took {timer.duration_ms}ms")
    """
    result = TimingResult(name=name)
    start_time = time.perf_counter()

    try:
        yield result
        result.success = True
    except Exception as e:
        result.success = False
        result.error = str(e)
        raise
    finally:
        result.end_time = time.perf_counter()
        result.duration_ms = (result.end_time - start_time) * 1000

        if record_stats:
            TimingRegistry.record(name, result.duration_ms, result.success)

        if not result.success:
            logger.warning(f"{name} failed in {result.duration_ms:.2f}ms: {result.error}")
        elif threshold_ms and result.duration_ms > threshold_ms:
            logger.warning(f"{name} exceeded threshold: {result.duration_ms:.2f}ms > {threshold_ms}ms")


@contextmanager
def timed_block_sync(
    name: str,
    threshold_ms: float | None = None,
    record_stats: bool = True,
):
    """Sync context manager for timing a code block."""
    result = TimingResult(name=name)
    start_time = time.perf_counter()

    try:
        yield result
        result.success = True
    except Exception as e:
        result.success = False
        result.error = str(e)
        raise
    finally:
        result.end_time = time.perf_counter()
        result.duration_ms = (result.end_time - start_time) * 1000

        if record_stats:
            TimingRegistry.record(name, result.duration_ms, result.success)

        if not result.success:
            logger.warning(f"{name} failed in {result.duration_ms:.2f}ms: {result.error}")
        elif threshold_ms and result.duration_ms > threshold_ms:
            logger.warning(f"{name} exceeded threshold: {result.duration_ms:.2f}ms > {threshold_ms}ms")


def get_timing_stats() -> dict[str, dict[str, Any]]:
    """Get all timing statistics.

    Convenience function for TimingRegistry.get_all_stats().
    """
    return TimingRegistry.get_all_stats()
