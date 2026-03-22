"""Tests for on-demand Chrome lifecycle management."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chrome_lifecycle import (
    ChromeLifecycleManager,
    ChromeState,
    get_chrome_lifecycle,
    init_chrome_lifecycle,
)


@pytest.fixture
def mock_rpc():
    """Create a mock supervisord XML-RPC proxy."""
    rpc = MagicMock()
    rpc.supervisor.startProcess = MagicMock(return_value=True)
    rpc.supervisor.stopProcess = MagicMock(return_value=True)
    rpc.supervisor.getProcessInfo = MagicMock(
        return_value={"statename": "STOPPED", "state": 0}
    )
    return rpc


@pytest.fixture
def lifecycle(mock_rpc):
    """Create a ChromeLifecycleManager with mocked dependencies."""
    return ChromeLifecycleManager(
        supervisor_rpc=mock_rpc,
        idle_timeout=5,
        ready_timeout=3,
        idle_check_interval=1,
        cdp_port=8222,
    )


class TestChromeState:
    def test_initial_state_is_stopped(self, lifecycle):
        assert lifecycle.state == ChromeState.STOPPED
        assert not lifecycle.is_running

    def test_stats_when_stopped(self, lifecycle):
        stats = lifecycle.stats
        assert stats["state"] == "stopped"
        assert stats["startup_count"] == 0
        assert stats["stop_count"] == 0


class TestEnsureRunning:
    @pytest.mark.asyncio
    async def test_cold_start(self, lifecycle):
        """Chrome starts when ensure_running is called and it's stopped."""
        with patch.object(
            lifecycle, "_is_cdp_responsive", new_callable=AsyncMock, return_value=True
        ):
            result = await lifecycle.ensure_running()
            assert result["cold_start"] is True
            assert result["startup_ms"] is not None
            assert result["startup_ms"] > 0
            assert lifecycle.state == ChromeState.RUNNING
            assert lifecycle.stats["startup_count"] == 1

    @pytest.mark.asyncio
    async def test_warm_hit(self, lifecycle):
        """Already-running Chrome returns immediately."""
        lifecycle._state = ChromeState.RUNNING
        with patch.object(
            lifecycle, "_is_cdp_responsive", new_callable=AsyncMock, return_value=True
        ):
            result = await lifecycle.ensure_running()
            assert result["cold_start"] is False
            assert result["startup_ms"] is None
            assert result["state"] == "running"

    @pytest.mark.asyncio
    async def test_timeout_raises(self, lifecycle):
        """Raises TimeoutError if CDP never becomes responsive."""
        lifecycle._ready_timeout = 1  # 1 second timeout for fast test
        with patch.object(
            lifecycle, "_is_cdp_responsive", new_callable=AsyncMock, return_value=False
        ):
            with pytest.raises(TimeoutError, match="CDP not responsive"):
                await lifecycle.ensure_running()
            assert lifecycle.state == ChromeState.STOPPED

    @pytest.mark.asyncio
    async def test_restart_on_unresponsive_running(self, lifecycle):
        """Restarts Chrome if marked RUNNING but CDP is unresponsive."""
        lifecycle._state = ChromeState.RUNNING

        call_count = 0

        async def mock_cdp_responsive():
            nonlocal call_count
            call_count += 1
            # First call: unresponsive (triggers restart)
            # Subsequent calls: responsive (startup succeeds)
            return call_count > 1

        with patch.object(
            lifecycle, "_is_cdp_responsive", side_effect=mock_cdp_responsive
        ):
            result = await lifecycle.ensure_running()
            assert result["cold_start"] is True
            assert lifecycle.state == ChromeState.RUNNING

    @pytest.mark.asyncio
    async def test_ensure_is_idempotent(self, lifecycle):
        """Multiple concurrent ensure calls result in one startup."""
        lifecycle._state = ChromeState.STOPPED

        with patch.object(
            lifecycle, "_is_cdp_responsive", new_callable=AsyncMock, return_value=True
        ):
            results = await asyncio.gather(
                lifecycle.ensure_running(),
                lifecycle.ensure_running(),
                lifecycle.ensure_running(),
            )
            # Only one should be a cold start
            cold_starts = [r for r in results if r["cold_start"]]
            assert len(cold_starts) == 1
            assert lifecycle.stats["startup_count"] == 1

    @pytest.mark.asyncio
    async def test_touch_updates_last_touch(self, lifecycle):
        """touch() updates the idle timer."""
        assert lifecycle._last_touch == 0.0
        lifecycle.touch()
        assert lifecycle._last_touch > 0.0
        first_touch = lifecycle._last_touch
        await asyncio.sleep(0.01)
        lifecycle.touch()
        assert lifecycle._last_touch > first_touch


class TestStop:
    @pytest.mark.asyncio
    async def test_stop_running_chrome(self, lifecycle):
        lifecycle._state = ChromeState.RUNNING
        await lifecycle.stop()
        assert lifecycle.state == ChromeState.STOPPED
        assert lifecycle.stats["stop_count"] == 1

    @pytest.mark.asyncio
    async def test_stop_already_stopped_is_noop(self, lifecycle):
        await lifecycle.stop()
        assert lifecycle.stats["stop_count"] == 0

    @pytest.mark.asyncio
    async def test_stop_stopping_is_noop(self, lifecycle):
        lifecycle._state = ChromeState.STOPPING
        await lifecycle.stop()
        assert lifecycle.stats["stop_count"] == 0


class TestIdleChecker:
    @pytest.mark.asyncio
    async def test_stops_chrome_when_idle(self, lifecycle):
        """Idle checker stops Chrome after timeout with no active connections."""
        lifecycle._state = ChromeState.RUNNING
        lifecycle._last_touch = time.monotonic() - 10  # 10s ago, timeout is 5s
        lifecycle._idle_timeout = 1

        with (
            patch.object(
                lifecycle,
                "_has_active_cdp_connections",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch.object(lifecycle, "stop", new_callable=AsyncMock) as mock_stop,
        ):
            await lifecycle.start_idle_checker()
            await asyncio.sleep(1.5)  # Wait for one check cycle
            await lifecycle.stop_idle_checker()
            mock_stop.assert_called()

    @pytest.mark.asyncio
    async def test_extends_when_cdp_active(self, lifecycle):
        """Idle checker extends timeout when CDP connections exist."""
        lifecycle._state = ChromeState.RUNNING
        lifecycle._last_touch = time.monotonic() - 10
        lifecycle._idle_timeout = 1

        with (
            patch.object(
                lifecycle,
                "_has_active_cdp_connections",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch.object(lifecycle, "stop", new_callable=AsyncMock) as mock_stop,
        ):
            await lifecycle.start_idle_checker()
            await asyncio.sleep(1.5)
            await lifecycle.stop_idle_checker()
            mock_stop.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_stopped(self, lifecycle):
        """Idle checker skips when Chrome is not running."""
        lifecycle._state = ChromeState.STOPPED
        lifecycle._idle_timeout = 0  # Would trigger immediately if checked

        with patch.object(lifecycle, "stop", new_callable=AsyncMock) as mock_stop:
            await lifecycle.start_idle_checker()
            await asyncio.sleep(1.5)
            await lifecycle.stop_idle_checker()
            mock_stop.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_idle_checker_idempotent(self, lifecycle):
        """Starting idle checker twice doesn't create duplicate tasks."""
        await lifecycle.start_idle_checker()
        first_task = lifecycle._idle_task
        await lifecycle.start_idle_checker()
        assert lifecycle._idle_task is first_task
        await lifecycle.stop_idle_checker()


class TestSyncState:
    @pytest.mark.asyncio
    async def test_syncs_running_state(self, lifecycle, mock_rpc):
        mock_rpc.supervisor.getProcessInfo.return_value = {
            "statename": "RUNNING",
            "state": 20,
        }
        await lifecycle.sync_state_from_supervisor()
        assert lifecycle.state == ChromeState.RUNNING
        assert lifecycle._last_touch > 0

    @pytest.mark.asyncio
    async def test_syncs_stopped_state(self, lifecycle, mock_rpc):
        mock_rpc.supervisor.getProcessInfo.return_value = {
            "statename": "STOPPED",
            "state": 0,
        }
        await lifecycle.sync_state_from_supervisor()
        assert lifecycle.state == ChromeState.STOPPED

    @pytest.mark.asyncio
    async def test_handles_rpc_error(self, lifecycle, mock_rpc):
        mock_rpc.supervisor.getProcessInfo.side_effect = Exception("connection refused")
        await lifecycle.sync_state_from_supervisor()
        assert lifecycle.state == ChromeState.STOPPED


class TestSingleton:
    def test_init_and_get(self, mock_rpc):
        mgr = init_chrome_lifecycle(mock_rpc, idle_timeout=30)
        assert get_chrome_lifecycle() is mgr
        assert isinstance(mgr, ChromeLifecycleManager)
