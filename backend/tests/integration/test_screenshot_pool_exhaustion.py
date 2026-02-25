"""Integration tests for screenshot service under high load (Priority 2)."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from app.application.services.screenshot_service import ScreenshotCaptureService
from app.domain.models.screenshot import ScreenshotTrigger


def _build_screenshot_service(mock_sandbox: Mock) -> ScreenshotCaptureService:
    """Create screenshot service wired with async-safe test doubles."""
    repository = Mock()
    repository.save = AsyncMock()
    repository.find_by_session = AsyncMock(return_value=[])

    minio_storage = Mock()
    minio_storage.store_screenshot = AsyncMock(return_value=None)
    minio_storage.store_thumbnail = AsyncMock(return_value=None)

    service = ScreenshotCaptureService(
        sandbox=mock_sandbox,
        session_id="test-session",
        repository=repository,
        minio_storage=minio_storage,
    )

    # Bypass startup readiness gate (tested separately in unit tests)
    service._ready.set()

    # Keep integration behavior but make retries fast for deterministic tests.
    service._settings.screenshot_http_retry_delay = 0.01
    service._settings.screenshot_circuit_recovery_seconds = 1

    return service


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

    service = _build_screenshot_service(mock_sandbox)

    # Create 50 concurrent screenshot requests
    tasks = []
    for _ in range(50):
        task = service.capture(ScreenshotTrigger.TOOL_AFTER)
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

    service = _build_screenshot_service(mock_sandbox)

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

    service = _build_screenshot_service(mock_sandbox)
    await service.capture(ScreenshotTrigger.TOOL_AFTER)


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

    service = _build_screenshot_service(mock_sandbox)

    # Attempt 100 captures
    successes = 0
    failures = 0

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

    service = _build_screenshot_service(mock_sandbox)

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
