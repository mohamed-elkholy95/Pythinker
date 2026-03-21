"""Tests for CDP keepalive lifecycle: shutdown safety, disconnect guard, and guarded probe."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser


def _make_browser() -> PlaywrightBrowser:
    """Create a PlaywrightBrowser with mocked dependencies."""
    with (
        patch("app.infrastructure.external.browser.playwright_browser.get_llm"),
        patch("app.infrastructure.external.browser.playwright_browser.get_settings") as mock_settings,
    ):
        settings = MagicMock()
        settings.browser_cdp_keepalive_enabled = True
        settings.browser_cdp_keepalive_interval = 45.0
        settings.browser_crash_circuit_breaker_enabled = True
        settings.browser_crash_window_seconds = 300.0
        settings.browser_crash_threshold = 3
        settings.browser_crash_cooldown_seconds = 60.0
        settings.browser_quick_health_check_enabled = True
        settings.browser_quick_health_check_timeout = 3.0
        settings.browser_blocked_types_set = None
        mock_settings.return_value = settings
        browser = PlaywrightBrowser(cdp_url="ws://localhost:9222")
    # Wire up a mock page
    browser.page = MagicMock()
    browser.page.is_closed = MagicMock(return_value=False)
    browser.page.evaluate = AsyncMock(return_value=True)
    browser.browser = MagicMock()
    browser._connection_healthy = True
    return browser


# ── Teardown / shutdown safety ──────────────────────────────────────


@pytest.mark.asyncio
async def test_cleanup_cancels_keepalive_and_background_tasks():
    """cleanup() must cancel the keepalive task and all background tasks."""
    browser = _make_browser()
    browser._shutting_down = False
    # Simulate a long-running keepalive
    browser._keepalive_task = asyncio.create_task(asyncio.sleep(60))
    browser._background_tasks.add(browser._keepalive_task)

    await browser.cleanup()

    assert browser._keepalive_task is None
    assert browser._shutting_down is True
    # All tasks either cancelled or done
    assert all(task.done() for task in browser._background_tasks)


def test_on_browser_disconnected_skips_reconnect_during_intentional_shutdown():
    """_on_browser_disconnected() should not schedule reconnect when shutting down."""
    browser = _make_browser()
    browser._shutting_down = True

    with patch("asyncio.get_running_loop") as get_loop:
        browser._on_browser_disconnected()
        get_loop.assert_not_called()


def test_on_browser_disconnected_reconnects_when_not_shutting_down():
    """_on_browser_disconnected() should schedule reconnect for unexpected disconnect."""
    browser = _make_browser()
    browser._shutting_down = False

    mock_loop = MagicMock()
    mock_task = MagicMock()
    mock_loop.create_task.return_value = mock_task
    mock_task.add_done_callback = MagicMock()

    with patch("asyncio.get_running_loop", return_value=mock_loop):
        browser._on_browser_disconnected()
        mock_loop.create_task.assert_called_once()


# ── Guarded keepalive probe ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_keepalive_skips_when_navigation_lock_is_held():
    """_keepalive_ping() should not probe when the navigation lock is held."""
    browser = _make_browser()
    browser._connection_healthy = True

    async with browser._navigation_lock:
        await browser._keepalive_ping()

    browser.page.evaluate.assert_not_called()


@pytest.mark.asyncio
async def test_keepalive_treats_execution_context_destroyed_as_non_fatal():
    """Execution context destroyed during keepalive is a navigation race, not a crash."""
    browser = _make_browser()
    browser._connection_healthy = True
    browser.page.evaluate = AsyncMock(side_effect=Exception("Execution context was destroyed"))

    await browser._keepalive_ping()

    assert browser._connection_healthy is True


@pytest.mark.asyncio
async def test_keepalive_marks_unhealthy_on_real_failure():
    """A real failure (not context destroyed) should mark the connection unhealthy."""
    browser = _make_browser()
    browser._connection_healthy = True
    browser.page.evaluate = AsyncMock(side_effect=Exception("Connection closed"))

    await browser._keepalive_ping()

    assert browser._connection_healthy is False


@pytest.mark.asyncio
async def test_keepalive_skips_when_shutting_down():
    """_keepalive_ping() should be a no-op when _shutting_down is True."""
    browser = _make_browser()
    browser._shutting_down = True
    browser._connection_healthy = True

    await browser._keepalive_ping()

    browser.page.evaluate.assert_not_called()


@pytest.mark.asyncio
async def test_keepalive_skips_when_unhealthy():
    """_keepalive_ping() should be a no-op when connection is already unhealthy."""
    browser = _make_browser()
    browser._connection_healthy = False

    await browser._keepalive_ping()

    browser.page.evaluate.assert_not_called()


@pytest.mark.asyncio
async def test_keepalive_ping_success_keeps_healthy():
    """A successful ping should keep the connection marked healthy."""
    browser = _make_browser()
    browser._connection_healthy = True
    browser.page.evaluate = AsyncMock(return_value=True)

    await browser._keepalive_ping()

    assert browser._connection_healthy is True
    browser.page.evaluate.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_keepalive_creates_task():
    """_start_keepalive() should create a keepalive task when enabled."""
    browser = _make_browser()
    browser._keepalive_task = None

    browser._start_keepalive()

    assert browser._keepalive_task is not None
    assert not browser._keepalive_task.done()
    # Cleanup
    browser._keepalive_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await browser._keepalive_task


@pytest.mark.asyncio
async def test_stop_keepalive_cancels_task():
    """_stop_keepalive() should cancel the keepalive task."""
    browser = _make_browser()
    browser._keepalive_task = asyncio.create_task(asyncio.sleep(60))

    await browser._stop_keepalive()

    assert browser._keepalive_task is None


@pytest.mark.asyncio
async def test_cancel_background_tasks_cleans_up():
    """_cancel_background_tasks() should cancel all tasks and clear the set."""
    browser = _make_browser()
    t1 = asyncio.create_task(asyncio.sleep(60))
    t2 = asyncio.create_task(asyncio.sleep(60))
    browser._background_tasks.add(t1)
    browser._background_tasks.add(t2)
    browser._keepalive_task = t1

    await browser._cancel_background_tasks()

    assert browser._keepalive_task is None
    assert len(browser._background_tasks) == 0
    assert t1.cancelled()
    assert t2.cancelled()
