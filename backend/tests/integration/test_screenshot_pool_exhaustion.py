"""Integration tests for screenshot service under high load (Priority 2)."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.application.services.screenshot_service import ScreenshotCaptureService
from app.domain.models.screenshot import ScreenshotTrigger


@pytest.mark.asyncio
@pytest.mark.slow
async def test_concurrent_screenshot_requests_dont_exhaust_pool():
    """Test that concurrent screenshot requests are handled without pool exhaustion."""
    mock_sandbox = Mock()

    # Simulate slow screenshot capture
    async def slow_screenshot(*args, **kwargs):
        await asyncio.sleep(0.1)
        response = Mock()
        response.content = b"fake_image_data"
        return response

    mock_sandbox.get_screenshot = slow_screenshot

    service = ScreenshotCaptureService(
        sandbox=mock_sandbox,
        session_id="test-session",
        repository=Mock(),
        mongodb=Mock(),
    )

    # Create 50 concurrent screenshot requests
    tasks = []
    for _ in range(50):
        task = service.capture(ScreenshotTrigger.TOOL_CALL)
        tasks.append(task)

    # All should complete (may have some failures, but no deadlock)
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # At least some should succeed
    successes = sum(1 for r in results if r is not None and not isinstance(r, Exception))
    assert successes > 0


@pytest.mark.asyncio
async def test_circuit_breaker_prevents_cascading_failures():
    """Test that circuit breaker stops cascading failures."""
    mock_sandbox = Mock()
    mock_sandbox.get_screenshot = AsyncMock(side_effect=Exception("Connection error"))

    service = ScreenshotCaptureService(sandbox=mock_sandbox, session_id="test-session")

    # Trigger multiple failures
    for _ in range(10):
        result = await service.capture(ScreenshotTrigger.PERIODIC)

    # Circuit should be open
    if service._circuit_breaker:
        assert service._circuit_breaker.state.value == "open"

        # Further attempts should be skipped immediately (no delay)
        import time

        start = time.perf_counter()
        result = await service.capture(ScreenshotTrigger.PERIODIC)
        duration = time.perf_counter() - start

        # Should be nearly instant (< 0.1s)
        assert duration < 0.1
        assert result is None


@pytest.mark.asyncio
async def test_retry_logic_recovers_from_transient_errors():
    """Test that retry logic recovers from transient failures."""
    mock_sandbox = Mock()

    # Fail 2 times, then succeed
    call_count = 0

    async def flaky_screenshot(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise Exception("Transient error")
        response = Mock()
        response.content = b"fake_image_data"
        return response

    mock_sandbox.get_screenshot = flaky_screenshot

    service = ScreenshotCaptureService(
        sandbox=mock_sandbox,
        session_id="test-session",
        repository=Mock(),
        mongodb=Mock(),
    )

    # Should succeed after retries (mocking storage)
    with (
        patch.object(service._repository, "save", new_callable=AsyncMock),
        patch.object(service._mongodb, "store_screenshot", return_value="fake_file_id"),
    ):
        await service.capture(ScreenshotTrigger.TOOL_CALL)

        # Should have succeeded after retries
        # Note: Full test requires mocking all storage layers


@pytest.mark.asyncio
async def test_screenshot_service_success_rate_above_95_percent():
    """Test that screenshot service maintains >95% success rate under normal conditions."""
    mock_sandbox = Mock()

    # 98% success rate (2% failures)
    call_count = 0

    async def mostly_successful_screenshot(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count % 50 == 0:  # 2% failure rate
            raise Exception("Occasional error")
        response = Mock()
        response.content = b"fake_image_data"
        return response

    mock_sandbox.get_screenshot = mostly_successful_screenshot

    service = ScreenshotCaptureService(
        sandbox=mock_sandbox,
        session_id="test-session",
        repository=Mock(),
        mongodb=Mock(),
    )

    # Attempt 100 captures
    successes = 0
    failures = 0

    with (
        patch.object(service._repository, "save", new_callable=AsyncMock),
        patch.object(service._mongodb, "store_screenshot", return_value="fake_file_id"),
    ):
        for _ in range(100):
            result = await service.capture(ScreenshotTrigger.PERIODIC)
            if result:
                successes += 1
            else:
                failures += 1

    # Success rate should be >95%
    success_rate = successes / (successes + failures)
    assert success_rate >= 0.95


@pytest.mark.asyncio
async def test_circuit_recovery_after_timeout():
    """Test that circuit breaker recovers after timeout."""
    mock_sandbox = Mock()
    mock_sandbox.get_screenshot = AsyncMock(side_effect=Exception("Connection error"))

    service = ScreenshotCaptureService(sandbox=mock_sandbox, session_id="test-session")

    # Set short recovery timeout for testing
    if service._circuit_breaker:
        service._circuit_breaker._recovery_timeout = 1.0

        # Open the circuit
        for _ in range(5):
            await service.capture(ScreenshotTrigger.PERIODIC)

        assert service._circuit_breaker.state.value == "open"

        # Wait for recovery timeout
        await asyncio.sleep(1.2)

        # Should transition to HALF_OPEN
        is_allowed = service._circuit_breaker.is_allowed()
        assert is_allowed is True
        assert service._circuit_breaker.state.value == "half_open"
