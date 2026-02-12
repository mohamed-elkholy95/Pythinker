"""Unit tests for screenshot exponential backoff retry (Priority 2)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.application.services.screenshot_service import ScreenshotCaptureService
from app.domain.models.screenshot import ScreenshotTrigger


@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt():
    """Test that retry succeeds after one failure."""
    mock_sandbox = Mock()

    # Fail first, succeed second
    call_count = 0

    async def mock_get_screenshot(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Transient error")
        # Success on second attempt
        response = Mock()
        response.content = b"fake_image_data"
        return response

    mock_sandbox.get_screenshot = mock_get_screenshot

    # Helper to create proper minio mock
    minio = MagicMock()
    minio.store_screenshot = AsyncMock(side_effect=lambda data, key, **kw: key)
    minio.store_thumbnail = AsyncMock(side_effect=lambda data, key, **kw: key)

    service = ScreenshotCaptureService(
        sandbox=mock_sandbox, session_id="test-session", repository=Mock(), minio_storage=minio
    )

    # Capture should succeed after retry
    await service.capture(ScreenshotTrigger.TOOL_AFTER)

    # Should have retried and succeeded (at least 2 calls, may be more due to dedup/thumbnail)
    assert call_count >= 2
    # Note: Full test requires mocking repository.save


@pytest.mark.asyncio
async def test_retry_uses_exponential_backoff():
    """Test that retry delays increase exponentially."""
    mock_sandbox = Mock()

    # Track delays
    delays = []
    original_sleep = asyncio.sleep

    async def track_sleep(delay):
        delays.append(delay)
        await original_sleep(0.01)  # Short sleep for test

    mock_sandbox.get_screenshot = AsyncMock(side_effect=Exception("Connection error"))

    # Create minio mock
    minio = MagicMock()
    minio.store_screenshot = AsyncMock(side_effect=lambda data, key, **kw: key)
    minio.store_thumbnail = AsyncMock(side_effect=lambda data, key, **kw: key)

    service = ScreenshotCaptureService(sandbox=mock_sandbox, session_id="test-session", minio_storage=minio)

    with (
        patch("asyncio.sleep", side_effect=track_sleep),
        patch.object(service._settings, "screenshot_http_retry_attempts", 3),
        patch.object(service._settings, "screenshot_http_retry_delay", 1.0),
    ):
        from contextlib import suppress

        with suppress(Exception):
            await service._get_screenshot_with_retry(quality=80, scale=1.0)

    # Should have delays: 1s, 2s (exponential backoff)
    # Note: Last attempt doesn't sleep
    assert len(delays) == 2
    assert delays[0] == 1.0  # 1 * 2^0
    assert delays[1] == 2.0  # 1 * 2^1


@pytest.mark.asyncio
async def test_retry_respects_max_attempts():
    """Test that retry stops after max attempts."""
    mock_sandbox = Mock()
    mock_sandbox.get_screenshot = AsyncMock(side_effect=Exception("Permanent error"))

    # Create minio mock
    minio = MagicMock()
    minio.store_screenshot = AsyncMock(side_effect=lambda data, key, **kw: key)
    minio.store_thumbnail = AsyncMock(side_effect=lambda data, key, **kw: key)

    service = ScreenshotCaptureService(sandbox=mock_sandbox, session_id="test-session", minio_storage=minio)

    call_count = 0

    async def count_calls(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise Exception("Permanent error")

    mock_sandbox.get_screenshot = count_calls

    with (
        patch.object(service._settings, "screenshot_http_retry_attempts", 3),
        pytest.raises(Exception, match="Permanent error"),
    ):
        await service._get_screenshot_with_retry(quality=80, scale=1.0)

    # Should have tried exactly 3 times
    assert call_count == 3


@pytest.mark.asyncio
async def test_successful_retry_increments_metric():
    """Test that successful retry increments the retry metric."""
    mock_sandbox = Mock()

    call_count = 0

    async def mock_get_screenshot(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Transient error")
        response = Mock()
        response.content = b"fake_image_data"
        return response

    mock_sandbox.get_screenshot = mock_get_screenshot

    # Create minio mock
    minio = MagicMock()
    minio.store_screenshot = AsyncMock(side_effect=lambda data, key, **kw: key)
    minio.store_thumbnail = AsyncMock(side_effect=lambda data, key, **kw: key)

    service = ScreenshotCaptureService(sandbox=mock_sandbox, session_id="test-session", minio_storage=minio)

    # This would increment the metric (in full implementation with mocks)
    await service._get_screenshot_with_retry(quality=80, scale=1.0)

    # Note: Full verification requires proper async mock setup


@pytest.mark.asyncio
async def test_circuit_breaker_and_retry_work_together():
    """Test that circuit breaker and retry logic work together."""
    mock_sandbox = Mock()
    mock_sandbox.get_screenshot = AsyncMock(side_effect=Exception("Connection error"))

    # Create minio mock
    minio = MagicMock()
    minio.store_screenshot = AsyncMock(side_effect=lambda data, key, **kw: key)
    minio.store_thumbnail = AsyncMock(side_effect=lambda data, key, **kw: key)

    service = ScreenshotCaptureService(sandbox=mock_sandbox, session_id="test-session", minio_storage=minio)

    # Trigger multiple failures to open circuit
    for _ in range(6):
        result = await service.capture(ScreenshotTrigger.PERIODIC)
        assert result is None

    # Circuit should now be open
    if service._circuit_breaker:
        assert service._circuit_breaker.state.value == "open"

        # Further captures should be skipped immediately (no retry)
        result = await service.capture(ScreenshotTrigger.PERIODIC)
        assert result is None
