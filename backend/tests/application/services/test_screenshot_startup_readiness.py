"""Unit tests for screenshot startup readiness gate.

Tests the _ensure_endpoint_ready() mechanism that prevents ConnectError at
session startup when the sandbox screenshot handler hasn't fully initialized
after ensure_sandbox() returns.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.services.screenshot_service import ScreenshotCaptureService
from app.domain.models.screenshot import ScreenshotTrigger


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear all caches before each test to prevent state contamination."""
    from app.core.circuit_breaker_registry import CircuitBreakerRegistry
    from app.core.config import get_settings

    get_settings.cache_clear()
    CircuitBreakerRegistry.reset_all()
    yield
    get_settings.cache_clear()
    CircuitBreakerRegistry.reset_all()


def _make_service(sandbox, **kwargs):
    """Create a ScreenshotCaptureService with test mocks."""
    minio = MagicMock()
    minio.store_screenshot = AsyncMock(side_effect=lambda data, key, **kw: key)
    minio.store_thumbnail = AsyncMock(side_effect=lambda data, key, **kw: key)
    return ScreenshotCaptureService(
        sandbox=sandbox,
        session_id=kwargs.get("session_id", "test-session"),
        repository=kwargs.get("repository", MagicMock(save=AsyncMock())),
        minio_storage=minio,
    )


@pytest.mark.asyncio
async def test_readiness_gate_succeeds_on_first_probe():
    """Probe succeeds immediately after grace period — _ready is set."""
    call_count = 0

    async def mock_get_screenshot(**kwargs):
        nonlocal call_count
        call_count += 1
        return SimpleNamespace(content=b"tiny-image", headers={})

    sandbox = MagicMock()
    sandbox.get_screenshot = mock_get_screenshot

    service = _make_service(sandbox)
    # Override grace to 0 for fast test
    service._settings.screenshot_startup_grace_seconds = 0.0

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await service._ensure_endpoint_ready()

    assert service._ready.is_set()
    assert call_count == 1


@pytest.mark.asyncio
async def test_readiness_gate_retries_on_failure():
    """Probe retries with backoff when endpoint fails."""
    call_count = 0

    async def mock_get_screenshot(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("Connection refused")
        return SimpleNamespace(content=b"tiny-image", headers={})

    sandbox = MagicMock()
    sandbox.get_screenshot = mock_get_screenshot

    service = _make_service(sandbox)
    service._settings.screenshot_startup_grace_seconds = 0.0

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await service._ensure_endpoint_ready()

    assert service._ready.is_set()
    assert call_count == 3  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_readiness_gate_sets_ready_after_all_probes_fail():
    """Ready is set even when all probes fail — captures aren't blocked forever."""
    sandbox = MagicMock()
    sandbox.get_screenshot = AsyncMock(side_effect=ConnectionError("Connection refused"))

    service = _make_service(sandbox)
    service._settings.screenshot_startup_grace_seconds = 0.0
    service._settings.screenshot_startup_max_probes = 3
    service._settings.screenshot_startup_probe_timeout = 60.0

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await service._ensure_endpoint_ready()

    # _ready must be set to prevent blocking all subsequent captures
    assert service._ready.is_set()
    assert sandbox.get_screenshot.call_count == 3


@pytest.mark.asyncio
async def test_readiness_gate_runs_only_once():
    """Second call to _ensure_endpoint_ready() returns immediately."""
    call_count = 0

    async def mock_get_screenshot(**kwargs):
        nonlocal call_count
        call_count += 1
        return SimpleNamespace(content=b"tiny-image", headers={})

    sandbox = MagicMock()
    sandbox.get_screenshot = mock_get_screenshot

    service = _make_service(sandbox)
    service._settings.screenshot_startup_grace_seconds = 0.0

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await service._ensure_endpoint_ready()
        await service._ensure_endpoint_ready()  # Should be a no-op

    assert call_count == 1


@pytest.mark.asyncio
async def test_readiness_gate_concurrent_callers_share_single_probe():
    """Multiple concurrent callers don't each run their own probe sequence."""
    call_count = 0

    async def mock_get_screenshot(**kwargs):
        nonlocal call_count
        call_count += 1
        # Simulate slight delay to ensure both callers enter _ensure_endpoint_ready
        await asyncio.sleep(0)
        return SimpleNamespace(content=b"tiny-image", headers={})

    sandbox = MagicMock()
    sandbox.get_screenshot = mock_get_screenshot

    service = _make_service(sandbox)
    service._settings.screenshot_startup_grace_seconds = 0.0

    # Launch two concurrent readiness checks
    await asyncio.gather(
        service._ensure_endpoint_ready(),
        service._ensure_endpoint_ready(),
    )

    assert service._ready.is_set()
    # Only one probe should have run (the lock prevents the second)
    assert call_count == 1


@pytest.mark.asyncio
async def test_capture_waits_for_readiness_gate():
    """capture() waits for _ensure_endpoint_ready before proceeding."""
    probe_calls = 0
    capture_calls = 0

    async def mock_get_screenshot(quality=75, scale=0.5, **kwargs):
        nonlocal probe_calls, capture_calls
        if quality == 10 and scale == 0.1:
            # This is the probe call
            probe_calls += 1
            return SimpleNamespace(content=b"tiny-image", headers={})
        # This is the actual capture call
        capture_calls += 1
        return SimpleNamespace(content=b"full-image", headers={})

    sandbox = MagicMock()
    sandbox.get_screenshot = mock_get_screenshot

    service = _make_service(sandbox)
    service._settings.screenshot_startup_grace_seconds = 0.0

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await service.capture(ScreenshotTrigger.SESSION_START)

    assert probe_calls == 1  # Readiness probe ran
    assert capture_calls >= 1  # Actual capture ran after probe
    assert service._ready.is_set()


@pytest.mark.asyncio
async def test_readiness_gate_respects_probe_timeout():
    """Probe sequence aborts after probe_timeout seconds."""
    sandbox = MagicMock()
    sandbox.get_screenshot = AsyncMock(side_effect=ConnectionError("refused"))

    service = _make_service(sandbox)
    service._settings.screenshot_startup_grace_seconds = 0.0
    service._settings.screenshot_startup_max_probes = 100  # Many probes
    service._settings.screenshot_startup_probe_timeout = 0.0  # Immediate timeout

    await service._ensure_endpoint_ready()

    # Should have aborted quickly due to timeout
    assert service._ready.is_set()
    # With 0s timeout, at most 1 probe runs before the timeout check kicks in
    assert sandbox.get_screenshot.call_count <= 1
