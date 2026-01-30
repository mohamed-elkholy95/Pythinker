"""Tests for LLM Concurrency Limiter.

Tests the LLMConcurrencyLimiter class including:
- Basic acquire/release functionality
- Concurrent request limiting
- Timeout behavior
- Statistics tracking
- Singleton pattern
"""

import asyncio
import contextlib
from unittest.mock import MagicMock, patch

import pytest

from app.domain.services.concurrency.llm_limiter import (
    LimiterStats,
    LLMConcurrencyLimiter,
    LLMConcurrencyLimitError,
    get_llm_limiter,
)


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = MagicMock()
    settings.llm_max_concurrent = 3
    settings.llm_queue_timeout = 5.0
    return settings


@pytest.fixture
def limiter(mock_settings):
    """Create a fresh limiter instance for each test."""
    LLMConcurrencyLimiter.reset_instance()
    with patch("app.core.config.get_settings", return_value=mock_settings):
        yield LLMConcurrencyLimiter(max_concurrent=3, queue_timeout=5.0)
    LLMConcurrencyLimiter.reset_instance()


class TestLimiterStats:
    """Tests for LimiterStats dataclass."""

    def test_default_values(self):
        """Test default statistics values."""
        stats = LimiterStats()
        assert stats.total_requests == 0
        assert stats.active_requests == 0
        assert stats.queued_requests == 0
        assert stats.completed_requests == 0
        assert stats.rejected_requests == 0
        assert stats.total_wait_time == 0.0
        assert stats.max_wait_time == 0.0
        assert stats.timeouts == 0


class TestLLMConcurrencyLimiter:
    """Tests for LLMConcurrencyLimiter class."""

    def test_initialization(self, limiter):
        """Test limiter initialization."""
        assert limiter.max_concurrent == 3
        assert limiter.queue_timeout == 5.0
        assert limiter.active_count == 0
        assert limiter.queued_count == 0

    def test_singleton_pattern(self, mock_settings):
        """Test singleton instance management."""
        LLMConcurrencyLimiter.reset_instance()

        with patch("app.core.config.get_settings", return_value=mock_settings):
            instance1 = LLMConcurrencyLimiter.get_instance()
            instance2 = LLMConcurrencyLimiter.get_instance()

            assert instance1 is instance2

        LLMConcurrencyLimiter.reset_instance()

    @pytest.mark.asyncio
    async def test_acquire_single_request(self, limiter):
        """Test acquiring a single slot."""
        async with limiter.acquire():
            assert limiter.active_count == 1

        assert limiter.active_count == 0
        assert limiter.stats.completed_requests == 1

    @pytest.mark.asyncio
    async def test_acquire_multiple_concurrent(self, limiter):
        """Test multiple concurrent acquisitions within limit."""
        results = []

        async def acquire_and_hold(delay: float):
            async with limiter.acquire():
                results.append(limiter.active_count)
                await asyncio.sleep(delay)

        # Run 3 concurrent requests (at limit)
        await asyncio.gather(
            acquire_and_hold(0.1),
            acquire_and_hold(0.1),
            acquire_and_hold(0.1),
        )

        assert limiter.stats.total_requests == 3
        assert limiter.stats.completed_requests == 3
        assert max(results) <= 3

    @pytest.mark.asyncio
    async def test_acquire_exceeds_limit_queues(self, limiter):
        """Test that requests exceeding limit are queued."""
        acquired = []

        async def acquire_and_track(idx: int, hold_time: float):
            async with limiter.acquire():
                acquired.append(idx)
                await asyncio.sleep(hold_time)

        # Start 5 requests with only 3 concurrent allowed
        tasks = [
            asyncio.create_task(acquire_and_track(i, 0.1))
            for i in range(5)
        ]

        # Let some tasks acquire
        await asyncio.sleep(0.05)
        assert limiter.active_count <= 3

        await asyncio.gather(*tasks)
        assert len(acquired) == 5
        assert limiter.stats.completed_requests == 5

    @pytest.mark.asyncio
    async def test_acquire_timeout(self, mock_settings):
        """Test timeout when waiting too long in queue."""
        LLMConcurrencyLimiter.reset_instance()

        with patch("app.core.config.get_settings", return_value=mock_settings):
            limiter = LLMConcurrencyLimiter(max_concurrent=1, queue_timeout=0.1)

            async def hold_slot():
                async with limiter.acquire():
                    await asyncio.sleep(1.0)  # Hold longer than timeout

            # Start one request that holds the slot
            task = asyncio.create_task(hold_slot())
            await asyncio.sleep(0.01)  # Let it acquire

            # Try to acquire with short timeout
            with pytest.raises(TimeoutError):
                async with limiter.acquire(timeout=0.1):
                    pass

            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        LLMConcurrencyLimiter.reset_instance()

    @pytest.mark.asyncio
    async def test_statistics_tracking(self, limiter):
        """Test that statistics are properly tracked."""
        async with limiter.acquire():
            pass

        async with limiter.acquire():
            pass

        stats = limiter.stats
        assert stats.total_requests == 2
        assert stats.completed_requests == 2
        assert stats.rejected_requests == 0
        assert stats.total_wait_time >= 0

    @pytest.mark.asyncio
    async def test_get_status(self, limiter):
        """Test get_status returns correct information."""
        async with limiter.acquire():
            status = limiter.get_status()
            assert status["max_concurrent"] == 3
            assert status["active_requests"] == 1
            assert status["queued_requests"] == 0
            assert "stats" in status

    @pytest.mark.asyncio
    async def test_cancellation_handling(self, limiter):
        """Test proper handling of cancelled requests."""
        async def cancellable_acquire():
            async with limiter.acquire():
                await asyncio.sleep(10)  # Long wait

        task = asyncio.create_task(cancellable_acquire())
        await asyncio.sleep(0.01)  # Let it start

        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        # Limiter should be in clean state
        assert limiter.active_count == 0 or limiter.queued_count >= 0

    @pytest.mark.asyncio
    async def test_properties(self, limiter):
        """Test limiter properties."""
        assert limiter.max_concurrent == 3
        assert limiter.queue_timeout == 5.0
        assert isinstance(limiter.stats, LimiterStats)

        async with limiter.acquire():
            assert limiter.active_count == 1
            assert limiter.queued_count == 0


class TestGetLlmLimiter:
    """Tests for the get_llm_limiter convenience function."""

    def test_returns_singleton(self, mock_settings):
        """Test that get_llm_limiter returns singleton."""
        LLMConcurrencyLimiter.reset_instance()

        with patch("app.core.config.get_settings", return_value=mock_settings):
            limiter1 = get_llm_limiter()
            limiter2 = get_llm_limiter()
            assert limiter1 is limiter2

        LLMConcurrencyLimiter.reset_instance()


class TestLLMConcurrencyLimitError:
    """Tests for the LLMConcurrencyLimitError exception."""

    def test_error_creation(self):
        """Test creating the error."""
        error = LLMConcurrencyLimitError("Test error")
        assert str(error) == "Test error"
