"""Tests for retry success tracking (Phase 4 P1).

Ensures retry outcomes are tracked per error type.
"""

import contextlib

import pytest

from app.domain.services.agents.error_handler import ErrorContext, ErrorHandler, ErrorType


class TestRetrySuccessTracking:
    """Test retry success tracking."""

    @pytest.mark.asyncio
    async def test_successful_retry_recorded(self):
        """Test that successful retries are recorded."""
        handler = ErrorHandler()
        context = ErrorContext(
            error_type=ErrorType.LLM_API,
            message="Test error",
            max_retries=2,
        )

        # Mock operation that succeeds on second try
        attempts = []

        async def operation():
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("First attempt fails")
            return "success"

        result = await handler.retry_with_backoff(operation, context)

        assert result == "success"
        assert context.retry_count == 1

        # Check success rate
        success_rate = handler.get_retry_success_rate(ErrorType.LLM_API)
        assert success_rate == 1.0

    @pytest.mark.asyncio
    async def test_failed_retry_recorded(self):
        """Test that failed retries are recorded."""
        handler = ErrorHandler()
        context = ErrorContext(
            error_type=ErrorType.TOOL_EXECUTION,
            message="Test error",
            max_retries=2,
        )

        async def operation():
            raise RuntimeError("Always fails")

        with pytest.raises(RuntimeError):
            await handler.retry_with_backoff(operation, context)

        # Check that failures were recorded
        success_rate = handler.get_retry_success_rate(ErrorType.TOOL_EXECUTION)
        assert success_rate == 0.0

    @pytest.mark.asyncio
    async def test_retry_stats_aggregation(self):
        """Test that retry statistics are aggregated correctly."""
        handler = ErrorHandler()

        # Multiple successful retries
        for _ in range(3):
            context = ErrorContext(
                error_type=ErrorType.BROWSER_TIMEOUT,
                message="Timeout",
                max_retries=1,
            )

            async def ok_op():
                return "ok"

            await handler.retry_with_backoff(ok_op, context)

        # One failed retry
        context_fail = ErrorContext(
            error_type=ErrorType.BROWSER_TIMEOUT,
            message="Timeout",
            max_retries=1,
        )

        async def fail_op():
            raise RuntimeError("Fail")

        with contextlib.suppress(RuntimeError):
            await handler.retry_with_backoff(fail_op, context_fail)

        # Check aggregated stats
        stats = handler.get_all_retry_stats()
        assert ErrorType.BROWSER_TIMEOUT.value in stats
        browser_stats = stats[ErrorType.BROWSER_TIMEOUT.value]
        assert browser_stats["successes"] == 3
        assert browser_stats["failures"] >= 1
        assert browser_stats["success_rate"] > 0.5

    def test_retry_success_rate_no_data(self):
        """Test that success rate is 0.0 when no data available."""
        handler = ErrorHandler()
        success_rate = handler.get_retry_success_rate(ErrorType.JSON_PARSE)
        assert success_rate == 0.0

    @pytest.mark.asyncio
    async def test_retry_backoff_delays(self):
        """Test that retry delays follow exponential backoff."""
        context = ErrorContext(
            error_type=ErrorType.LLM_API,
            message="Test",
            max_retries=3,
            min_retry_delay=0.1,
            backoff_factor=2.0,
        )

        delays = []
        for _i in range(3):
            delays.append(context.get_retry_delay())
            context.increment_retry()

        # Delays should increase exponentially
        assert delays[1] > delays[0]
        assert delays[2] > delays[1]


@pytest.mark.asyncio
class TestRetryTrackingIntegration:
    """Integration tests for retry tracking."""

    async def test_error_handler_metrics_export(self):
        """Test that retry metrics can be exported for monitoring."""
        # This would be an integration test with monitoring system
        # Placeholder for full implementation
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
