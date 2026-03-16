"""Tests for SandboxPool - sandbox pre-warming pool manager.

Tests cover:
- Initialization with config defaults and explicit overrides
- start() / stop() lifecycle management
- acquire() from pool vs. on-demand fallback
- Circuit breaker: opens after consecutive failures, exponential backoff, resets on success
- _warm_pool: fills to min_size, handles creation failures gracefully
- Pool size: respects max_pool_size boundary
- _monitor_docker_events: non-blocking iteration, graceful shutdown, error recovery
- _process_docker_event: OOM kill detection, pool removal, replenishment
- Global singleton helpers: get_sandbox_pool, start_sandbox_pool, stop_sandbox_pool
"""

import asyncio
import contextlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.sandbox_pool import (
    SandboxPool,
    get_sandbox_pool,
    start_sandbox_pool,
    stop_sandbox_pool,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_settings(
    min_size: int = 2,
    max_size: int = 4,
    warmup_interval: int = 30,
) -> MagicMock:
    """Return a mock Settings object with pool-related attributes."""
    settings = MagicMock()
    settings.sandbox_pool_min_size = min_size
    settings.sandbox_pool_max_size = max_size
    settings.sandbox_pool_warmup_interval = warmup_interval
    settings.sandbox_health_check_interval = 0
    settings.sandbox_oom_monitor_enabled = False
    settings.sandbox_pool_pause_idle = False
    settings.sandbox_image = None
    settings.sandbox_name_prefix = None
    return settings


def _make_mock_sandbox(sandbox_id: str = "sb-1") -> MagicMock:
    """Return a mock sandbox instance with async lifecycle methods."""
    sandbox = MagicMock()
    sandbox.id = sandbox_id
    sandbox.ip_address = "172.17.0.2"
    sandbox.destroy = AsyncMock(return_value=True)
    sandbox.ensure_sandbox = AsyncMock()
    return sandbox


def _make_mock_sandbox_cls(sandboxes: list[MagicMock] | None = None) -> MagicMock:
    """Return a mock sandbox *class* whose async create() yields sandboxes.

    If *sandboxes* is provided, create() will return them in order,
    then fall back to generating new ones on the fly.
    """
    cls = MagicMock()
    if sandboxes:
        remaining = list(sandboxes)

        async def _create():
            if remaining:
                return remaining.pop(0)
            return _make_mock_sandbox(f"sb-extra-{id(object())}")

        cls.create = AsyncMock(side_effect=_create)
    else:
        cls.create = AsyncMock(side_effect=lambda: _make_mock_sandbox())
    return cls


SETTINGS_PATH = "app.core.sandbox_pool.get_settings"
PREWARM_PATH = "app.core.sandbox_pool.SandboxPool._prewarm_browser"


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInitialization:
    """SandboxPool.__init__ configuration tests."""

    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    def test_defaults_from_settings(self, mock_settings: MagicMock) -> None:
        """Pool picks up min/max/interval from settings when no overrides given."""
        pool = SandboxPool(MagicMock())
        assert pool._min_size == 2
        assert pool._max_size == 4
        assert pool._warmup_interval == 30

    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    def test_explicit_overrides(self, mock_settings: MagicMock) -> None:
        """Explicit arguments override settings values."""
        pool = SandboxPool(MagicMock(), min_pool_size=5, max_pool_size=10, warmup_interval=60)
        assert pool._min_size == 5
        assert pool._max_size == 10
        assert pool._warmup_interval == 60

    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    def test_initial_state(self, mock_settings: MagicMock) -> None:
        """Freshly created pool has size 0 and is not started."""
        pool = SandboxPool(MagicMock())
        assert pool.size == 0
        assert pool.is_started is False
        assert pool._circuit_open is False
        assert pool._consecutive_failures == 0


# ---------------------------------------------------------------------------
# start() tests
# ---------------------------------------------------------------------------


class TestStart:
    """SandboxPool.start() tests."""

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_start_sets_started(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """start() flips is_started to True."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=2, warmup_interval=300)
        await pool.start()

        assert pool.is_started is True

        # Cleanup
        await pool.stop()

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_start_idempotent(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """Calling start() twice does not create a second warming task."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=2, warmup_interval=300)
        await pool.start()
        first_task = pool._warming_task

        await pool.start()  # second call — should be a no-op
        assert pool._warming_task is first_task

        await pool.stop()

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_start_creates_warming_task(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """start() creates a background warming task."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=2, warmup_interval=300)
        await pool.start()

        assert pool._warming_task is not None
        assert not pool._warming_task.done()

        await pool.stop()


# ---------------------------------------------------------------------------
# stop() tests
# ---------------------------------------------------------------------------


class TestStop:
    """SandboxPool.stop() tests."""

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_stop_resets_started(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """stop() sets is_started back to False."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=2, warmup_interval=300)
        await pool.start()
        await pool.stop()

        assert pool.is_started is False

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_stop_destroys_pooled_sandboxes(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """stop() destroys every sandbox remaining in the pool."""
        sb1 = _make_mock_sandbox("sb-1")
        sb2 = _make_mock_sandbox("sb-2")
        sandbox_cls = _make_mock_sandbox_cls([sb1, sb2])

        pool = SandboxPool(sandbox_cls, min_pool_size=2, max_pool_size=4, warmup_interval=300)
        await pool.start()

        # Give time for the warm_pool background task to create sandboxes
        await asyncio.sleep(0.2)

        await pool.stop()

        sb1.destroy.assert_awaited_once()
        sb2.destroy.assert_awaited_once()
        assert pool.size == 0

    @pytest.mark.asyncio
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_stop_on_empty_pool(self, mock_settings: MagicMock) -> None:
        """stop() succeeds even when pool has no sandboxes."""
        pool = SandboxPool(MagicMock(), min_pool_size=0, max_pool_size=2, warmup_interval=300)
        await pool.start()
        await pool.stop()

        assert pool.is_started is False

    @pytest.mark.asyncio
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_stop_when_not_started_is_noop(self, mock_settings: MagicMock) -> None:
        """stop() is a no-op when pool was never started."""
        pool = SandboxPool(MagicMock(), min_pool_size=0, max_pool_size=2, warmup_interval=300)
        await pool.stop()  # should not raise
        assert pool.is_started is False

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_stop_cancels_warming_task(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """stop() cancels the background _warm_pool_loop task."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=2, warmup_interval=300)
        await pool.start()

        warming_task = pool._warming_task
        assert warming_task is not None

        await pool.stop()
        assert pool._warming_task is None
        assert warming_task.cancelled() or warming_task.done()

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_stop_handles_destroy_timeout(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """stop() handles sandboxes whose destroy() times out."""
        sb = _make_mock_sandbox("sb-slow")

        async def _slow_destroy() -> None:
            await asyncio.sleep(999)  # never finishes

        sb.destroy = AsyncMock(side_effect=_slow_destroy)

        sandbox_cls = _make_mock_sandbox_cls([sb])
        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=2, warmup_interval=300)
        await pool.start()
        await asyncio.sleep(0.2)

        # stop should not hang — the per-sandbox 15s timeout in the source
        # is too long for tests, so we patch wait_for.
        with patch("app.core.sandbox_pool.asyncio.wait_for", side_effect=TimeoutError):
            await pool.stop()

        assert pool.is_started is False


# ---------------------------------------------------------------------------
# acquire() tests
# ---------------------------------------------------------------------------


class TestAcquire:
    """SandboxPool.acquire() tests."""

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_acquire_returns_pooled_sandbox(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """acquire() returns a sandbox from the pool when one is available."""
        sb = _make_mock_sandbox("sb-pooled")
        sandbox_cls = _make_mock_sandbox_cls([sb])
        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=4, warmup_interval=300)
        await pool.start()
        await asyncio.sleep(0.2)

        result = await pool.acquire(timeout=5.0)
        assert result.id == "sb-pooled"
        assert pool._total_acquisitions == 1

        await pool.stop()

    @pytest.mark.asyncio
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_acquire_falls_back_to_on_demand(self, mock_settings: MagicMock) -> None:
        """acquire() creates on-demand when pool is empty and get() times out."""
        on_demand_sb = _make_mock_sandbox("sb-ondemand")
        sandbox_cls = MagicMock()
        sandbox_cls.create = AsyncMock(return_value=on_demand_sb)

        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=4, warmup_interval=300)
        # Don't start — pool stays empty
        pool._started = True
        pool._stopping = False

        result = await pool.acquire(timeout=0.1)
        assert result.id == "sb-ondemand"
        sandbox_cls.create.assert_awaited_once()

        pool._started = False  # cleanup

    @pytest.mark.asyncio
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_acquire_unhealthy_pooled_sandbox_does_not_increment_total(self, mock_settings: MagicMock) -> None:
        """Failed health checks in acquire() do not count as successful acquisitions."""
        unhealthy = _make_mock_sandbox("sb-unhealthy")
        unhealthy.unpause = AsyncMock(return_value=True)
        unhealthy.ensure_sandbox = AsyncMock(side_effect=RuntimeError("health-check failed"))

        async def _slow_destroy() -> None:
            await asyncio.sleep(999)

        unhealthy.destroy = AsyncMock(side_effect=_slow_destroy)

        on_demand_sb = _make_mock_sandbox("sb-ondemand")
        sandbox_cls = MagicMock()
        sandbox_cls.create = AsyncMock(return_value=on_demand_sb)

        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=4, warmup_interval=300)
        pool._started = True
        pool._stopping = True  # disable replenishment side effects for deterministic assertions
        pool._pool.put_nowait(unhealthy)
        pool._pool_timestamps[unhealthy.id] = time.time()
        pool._paused_ids.add(unhealthy.id)

        real_wait_for = asyncio.tasks.wait_for

        async def _wait_for_with_short_destroy_timeout(awaitable: asyncio.Future, timeout: float):  # noqa: ASYNC109
            if timeout == 15.0:
                return await real_wait_for(awaitable, timeout=0.01)
            return await real_wait_for(awaitable, timeout=timeout)

        with patch("app.core.sandbox_pool.asyncio.wait_for", side_effect=_wait_for_with_short_destroy_timeout):
            result = await pool.acquire(timeout=0.1)

        assert result.id == "sb-ondemand"
        assert pool._total_acquisitions == 0
        unhealthy.destroy.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_acquire_triggers_replenishment(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """acquire() spawns a background replenishment task when not stopping."""
        sb = _make_mock_sandbox("sb-1")
        sandbox_cls = _make_mock_sandbox_cls([sb])
        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=4, warmup_interval=300)
        await pool.start()
        await asyncio.sleep(0.2)

        await pool.acquire(timeout=5.0)

        # A replenishment task should have been added
        # (it may already have completed, but it was created)
        # We verify by checking that create was called more than once
        # (once for initial warm, once for replenishment)
        await asyncio.sleep(0.2)
        assert sandbox_cls.create.await_count >= 2

        await pool.stop()

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_acquire_no_replenish_when_stopping(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """acquire() does not trigger replenishment when pool is stopping."""
        sb = _make_mock_sandbox("sb-1")
        sandbox_cls = _make_mock_sandbox_cls([sb])
        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=4, warmup_interval=300)
        await pool.start()
        await asyncio.sleep(0.2)

        pool._stopping = True
        initial_create_count = sandbox_cls.create.await_count

        await pool.acquire(timeout=5.0)
        await asyncio.sleep(0.1)

        # No additional create calls for replenishment
        assert sandbox_cls.create.await_count == initial_create_count

        pool._stopping = False  # so stop() actually runs
        await pool.stop()


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    """Circuit breaker logic in _create_and_verify_sandbox."""

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_circuit_opens_after_max_failures(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """Circuit breaker opens after _max_consecutive_failures (5) creation failures."""
        sandbox_cls = MagicMock()
        sandbox_cls.create = AsyncMock(side_effect=RuntimeError("docker error"))

        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=4, warmup_interval=300)

        for _ in range(5):
            result = await pool._create_and_verify_sandbox()
            assert result is None

        assert pool._circuit_open is True
        assert pool._consecutive_failures == 5
        assert pool._circuit_open_count == 1

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_circuit_blocks_creation(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """When circuit is open and reset time not reached, creation is skipped."""
        pool = SandboxPool(MagicMock(), min_pool_size=1, max_pool_size=4, warmup_interval=300)
        pool._circuit_open = True
        pool._circuit_reset_time = time.time() + 3600  # far in the future

        result = await pool._create_and_verify_sandbox()
        assert result is None

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_circuit_resets_after_backoff(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """Circuit resets (closes) when reset time has passed and next attempt succeeds."""
        sb = _make_mock_sandbox("sb-recovered")
        sandbox_cls = MagicMock()
        sandbox_cls.create = AsyncMock(return_value=sb)

        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=4, warmup_interval=300)
        pool._circuit_open = True
        pool._circuit_reset_time = time.time() - 1  # already passed
        pool._consecutive_failures = 5
        pool._circuit_open_count = 1

        result = await pool._create_and_verify_sandbox()

        assert result is not None
        assert result.id == "sb-recovered"
        assert pool._circuit_open is False
        assert pool._consecutive_failures == 0
        assert pool._circuit_open_count == 0

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_exponential_backoff(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """Circuit breaker uses exponential backoff: 60s, 120s, 240s, 300s (cap)."""
        sandbox_cls = MagicMock()
        sandbox_cls.create = AsyncMock(side_effect=RuntimeError("fail"))

        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=4, warmup_interval=300)

        expected_backoffs = [60, 120, 240, 300]

        for expected_seconds in expected_backoffs:
            # Open the circuit by failing 5 times
            pool._circuit_open = False
            pool._consecutive_failures = 0
            for _ in range(5):
                await pool._create_and_verify_sandbox()

            assert pool._circuit_open is True

            # Verify backoff duration (with small tolerance for time.time() drift)
            expected_reset = time.time() + expected_seconds
            assert abs(pool._circuit_reset_time - expected_reset) < 2.0

            # Pretend reset time passed so next round can re-open
            pool._circuit_reset_time = time.time() - 1

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_success_resets_failure_counters(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """A successful creation resets consecutive_failures and circuit_open_count."""
        sb = _make_mock_sandbox("sb-ok")
        sandbox_cls = MagicMock()
        sandbox_cls.create = AsyncMock(return_value=sb)

        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=4, warmup_interval=300)
        pool._consecutive_failures = 3
        pool._circuit_open_count = 2

        result = await pool._create_and_verify_sandbox()
        assert result is not None
        assert pool._consecutive_failures == 0
        assert pool._circuit_open_count == 0

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_circuit_does_not_open_below_threshold(
        self, mock_settings: MagicMock, mock_prewarm: AsyncMock
    ) -> None:
        """Circuit stays closed when failures are below max_consecutive_failures."""
        sandbox_cls = MagicMock()
        sandbox_cls.create = AsyncMock(side_effect=RuntimeError("fail"))

        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=4, warmup_interval=300)

        for _ in range(4):  # one below threshold
            await pool._create_and_verify_sandbox()

        assert pool._circuit_open is False
        assert pool._consecutive_failures == 4


# ---------------------------------------------------------------------------
# _warm_pool
# ---------------------------------------------------------------------------


class TestWarmPool:
    """Tests for _warm_pool filling logic."""

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_fills_to_min_size(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """_warm_pool fills the pool up to min_size."""
        sb1 = _make_mock_sandbox("sb-1")
        sb2 = _make_mock_sandbox("sb-2")
        sandbox_cls = _make_mock_sandbox_cls([sb1, sb2])

        pool = SandboxPool(sandbox_cls, min_pool_size=2, max_pool_size=4, warmup_interval=300)
        await pool._warm_pool()

        assert pool.size == 2

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_warm_pool_handles_creation_failure(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """_warm_pool continues when _create_and_verify_sandbox returns None."""
        call_count = 0

        async def _create_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError("fail")
            return _make_mock_sandbox(f"sb-{call_count}")

        sandbox_cls = MagicMock()
        sandbox_cls.create = AsyncMock(side_effect=_create_side_effect)

        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=4, warmup_interval=300)

        # Patch sleep to avoid 5s wait in the except branch
        with patch("app.core.sandbox_pool.sleep", new_callable=AsyncMock):
            await pool._warm_pool()

        # Should eventually succeed after failures
        assert pool.size >= 1

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_warm_pool_stops_when_stopping(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """_warm_pool exits early if _stopping becomes True."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=5, max_pool_size=10, warmup_interval=300)
        pool._stopping = True

        await pool._warm_pool()
        assert pool.size == 0

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_warm_pool_skips_if_already_at_min(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """_warm_pool does nothing if pool already has min_size sandboxes."""
        sb1 = _make_mock_sandbox("sb-1")
        sb2 = _make_mock_sandbox("sb-2")
        sandbox_cls = _make_mock_sandbox_cls([sb1, sb2])

        pool = SandboxPool(sandbox_cls, min_pool_size=2, max_pool_size=4, warmup_interval=300)
        # Pre-fill the pool
        pool._pool.put_nowait(sb1)
        pool._pool.put_nowait(sb2)

        sandbox_cls.create.reset_mock()
        await pool._warm_pool()

        # No new sandboxes should have been created
        sandbox_cls.create.assert_not_awaited()


# ---------------------------------------------------------------------------
# Pool Size / Max Size
# ---------------------------------------------------------------------------


class TestPoolSize:
    """Tests that pool respects max_pool_size."""

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_pool_respects_max_size(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """Pool does not exceed max_pool_size even if more sandboxes are created."""
        sandboxes = [_make_mock_sandbox(f"sb-{i}") for i in range(6)]
        sandbox_cls = _make_mock_sandbox_cls(sandboxes)

        pool = SandboxPool(sandbox_cls, min_pool_size=3, max_pool_size=4, warmup_interval=300)

        # Manually try to add more than max
        for sb in sandboxes[:4]:
            pool._pool.put_nowait(sb)

        assert pool.size == 4

        # Queue should reject the 5th
        with pytest.raises(asyncio.QueueFull):
            pool._pool.put_nowait(sandboxes[4])

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_warm_pool_destroys_extra_on_queue_full(
        self, mock_settings: MagicMock, mock_prewarm: AsyncMock
    ) -> None:
        """When _warm_pool encounters QueueFull, it destroys the extra sandbox and stops."""
        sandboxes = [_make_mock_sandbox(f"sb-{i}") for i in range(5)]
        sandbox_cls = _make_mock_sandbox_cls(sandboxes)

        pool = SandboxPool(sandbox_cls, min_pool_size=5, max_pool_size=2, warmup_interval=300)

        await pool._warm_pool()

        # Should have exactly max_size sandboxes (2)
        assert pool.size == 2

        # The 3rd sandbox should have been destroyed because the queue was full
        assert sandboxes[2].destroy.await_count == 1


# ---------------------------------------------------------------------------
# _create_and_verify_sandbox
# ---------------------------------------------------------------------------


class TestCreateAndVerify:
    """Tests for _create_and_verify_sandbox."""

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_calls_ensure_sandbox(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """_create_and_verify_sandbox calls ensure_sandbox on the created sandbox."""
        sb = _make_mock_sandbox("sb-1")
        sandbox_cls = MagicMock()
        sandbox_cls.create = AsyncMock(return_value=sb)

        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=4, warmup_interval=300)
        result = await pool._create_and_verify_sandbox()

        assert result is sb
        sb.ensure_sandbox.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_calls_prewarm_browser(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """_create_and_verify_sandbox pre-warms the browser."""
        sb = _make_mock_sandbox("sb-1")
        sandbox_cls = MagicMock()
        sandbox_cls.create = AsyncMock(return_value=sb)

        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=4, warmup_interval=300)
        await pool._create_and_verify_sandbox()

        mock_prewarm.assert_awaited_once_with(sb)

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_returns_none_on_create_failure(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """_create_and_verify_sandbox returns None when create() raises."""
        sandbox_cls = MagicMock()
        sandbox_cls.create = AsyncMock(side_effect=RuntimeError("docker unavailable"))

        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=4, warmup_interval=300)
        result = await pool._create_and_verify_sandbox()

        assert result is None
        assert pool._consecutive_failures == 1

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_returns_none_on_ensure_failure(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """_create_and_verify_sandbox returns None when ensure_sandbox() raises."""
        sb = _make_mock_sandbox("sb-1")
        sb.ensure_sandbox = AsyncMock(side_effect=RuntimeError("sandbox unhealthy"))
        sandbox_cls = MagicMock()
        sandbox_cls.create = AsyncMock(return_value=sb)

        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=4, warmup_interval=300)
        result = await pool._create_and_verify_sandbox()

        assert result is None
        assert pool._consecutive_failures == 1

    @pytest.mark.asyncio
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_skips_ensure_if_not_available(self, mock_settings: MagicMock) -> None:
        """_create_and_verify_sandbox skips ensure_sandbox if sandbox lacks the method."""
        sb = MagicMock()
        sb.id = "sb-noensure"
        sb.ip_address = None
        # Remove ensure_sandbox by using spec that doesn't include it
        del sb.ensure_sandbox

        sandbox_cls = MagicMock()
        sandbox_cls.create = AsyncMock(return_value=sb)

        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=4, warmup_interval=300)

        with patch(PREWARM_PATH, new_callable=AsyncMock):
            result = await pool._create_and_verify_sandbox()

        assert result is sb


# ---------------------------------------------------------------------------
# _replenish_one
# ---------------------------------------------------------------------------


class TestReplenishOne:
    """Tests for _replenish_one."""

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_replenish_when_below_min(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """_replenish_one calls _warm_pool when pool is below min_size."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=2, max_pool_size=4, warmup_interval=300)

        assert pool.size == 0  # below min
        await pool._replenish_one()

        assert pool.size == 2  # filled to min

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_replenish_skips_when_at_min(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """_replenish_one does nothing when pool already at min_size."""
        sb1 = _make_mock_sandbox("sb-1")
        sb2 = _make_mock_sandbox("sb-2")
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=2, max_pool_size=4, warmup_interval=300)

        pool._pool.put_nowait(sb1)
        pool._pool.put_nowait(sb2)

        sandbox_cls.create.reset_mock()
        await pool._replenish_one()

        sandbox_cls.create.assert_not_awaited()

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_replenish_skips_when_stopping(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """_replenish_one does nothing when pool is stopping."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=2, max_pool_size=4, warmup_interval=300)
        pool._stopping = True

        await pool._replenish_one()

        sandbox_cls.create.assert_not_awaited()


# ---------------------------------------------------------------------------
# _warm_pool_loop
# ---------------------------------------------------------------------------


class TestWarmPoolLoop:
    """Tests for _warm_pool_loop background maintenance."""

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_loop_runs_periodically(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """_warm_pool_loop calls _warm_pool after each interval."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=4, warmup_interval=0.05)

        loop_task = asyncio.create_task(pool._warm_pool_loop())

        # Let it run a couple of iterations
        await asyncio.sleep(0.2)

        pool._stopping = True
        loop_task.cancel()
        # _warm_pool_loop catches CancelledError internally and breaks,
        # so the task completes normally (no CancelledError propagated).
        await loop_task

        # Pool should have been warmed at least once
        assert sandbox_cls.create.await_count >= 1

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_loop_exits_on_cancel(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """_warm_pool_loop exits cleanly on CancelledError."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=4, warmup_interval=300)

        loop_task = asyncio.create_task(pool._warm_pool_loop())
        await asyncio.sleep(0.05)

        loop_task.cancel()
        # _warm_pool_loop catches CancelledError internally and breaks,
        # so the task completes normally — no exception propagated.
        await loop_task
        assert loop_task.done()
        assert loop_task.exception() is None


# ---------------------------------------------------------------------------
# _monitor_docker_events / _process_docker_event
# ---------------------------------------------------------------------------


class TestMonitorDockerEvents:
    """Tests for _monitor_docker_events non-blocking Docker event monitoring."""

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_event_loop_not_blocked_during_monitoring(
        self, mock_settings: MagicMock, mock_prewarm: AsyncMock
    ) -> None:
        """Event loop remains responsive while _monitor_docker_events waits for events.

        Uses a ticker pattern: a concurrent coroutine increments a counter
        every 10ms. If the event loop were blocked, the ticker would stall
        and the count would be near zero.
        """
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=4, warmup_interval=300)

        ticker_count = 0
        ticker_running = True

        async def _ticker():
            nonlocal ticker_count
            while ticker_running:
                await asyncio.sleep(0.01)
                ticker_count += 1

        # Mock docker.from_env().events() to block for 200ms then raise StopIteration
        def _slow_event_stream():
            """Generator that blocks briefly per next() call, simulating Docker daemon."""
            import time as _time

            _time.sleep(0.05)  # Block 50ms on first next()
            yield {
                "Actor": {"ID": "abc123456789", "Attributes": {"exitCode": "0"}},
            }
            _time.sleep(0.05)  # Block 50ms on second next()
            yield {
                "Actor": {"ID": "def456789012", "Attributes": {"exitCode": "1"}},
            }
            # Stream ends (StopIteration), monitor will try to reconnect

        mock_docker_client = MagicMock()
        mock_docker_client.events.return_value = _slow_event_stream()

        with patch("app.core.sandbox_pool.docker") as mock_docker_mod:
            mock_docker_mod.from_env.return_value = mock_docker_client

            # After first stream ends, stop the monitor on reconnect
            call_count = 0
            original_from_env = mock_docker_mod.from_env

            def _from_env_then_stop():
                nonlocal call_count
                call_count += 1
                if call_count > 1:
                    # Signal stop before second stream creation
                    pool._stopping = True
                    raise RuntimeError("stopping")
                return original_from_env.return_value

            mock_docker_mod.from_env.side_effect = _from_env_then_stop

            ticker_task = asyncio.create_task(_ticker())
            monitor_task = asyncio.create_task(pool._monitor_docker_events())

            # Wait for the monitor to finish processing both events
            await asyncio.sleep(0.3)

            pool._stopping = True
            ticker_running = False

            # Clean up tasks
            monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await monitor_task
            await ticker_task

        # The ticker should have incremented many times while the blocking
        # reads happened in threads. If iteration were blocking the event
        # loop, ticker_count would be near 0.
        assert ticker_count >= 5, (
            f"Event loop was blocked: ticker only incremented {ticker_count} times "
            f"(expected >= 5 in 300ms with 10ms ticks)"
        )

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_processes_events_correctly(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """Events from Docker are dispatched to _process_docker_event."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=4, warmup_interval=300)

        processed_events: list[dict] = []

        async def _capture_event(event):
            processed_events.append(event)

        pool._process_docker_event = _capture_event  # type: ignore[assignment]

        events = [
            {"Actor": {"ID": "aaa111222333", "Attributes": {"exitCode": "137", "oomKilled": "true"}}},
            {"Actor": {"ID": "bbb444555666", "Attributes": {"exitCode": "0"}}},
        ]

        def _event_gen():
            yield from events

        mock_client = MagicMock()
        mock_client.events.return_value = _event_gen()

        with patch("app.core.sandbox_pool.docker") as mock_docker_mod:
            mock_docker_mod.from_env.return_value = mock_client

            # Stop after first stream exhaustion
            call_count = 0

            def _from_env_stop():
                nonlocal call_count
                call_count += 1
                if call_count > 1:
                    pool._stopping = True
                    raise RuntimeError("done")
                return mock_client

            mock_docker_mod.from_env.side_effect = _from_env_stop

            monitor_task = asyncio.create_task(pool._monitor_docker_events())
            await asyncio.sleep(0.1)

            pool._stopping = True
            monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await monitor_task

        assert len(processed_events) == 2
        assert processed_events[0]["Actor"]["ID"] == "aaa111222333"
        assert processed_events[1]["Actor"]["ID"] == "bbb444555666"

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_graceful_shutdown_stops_monitoring(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """Setting _stopping=True causes _monitor_docker_events to exit."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=4, warmup_interval=300)

        def _blocking_event_gen():
            """Generator that blocks indefinitely -- simulates a quiet Docker daemon."""
            import time as _time

            # Spin until stopping flag is set, then let generator end
            while not pool._stopping:
                _time.sleep(0.02)
            # Generator ends here -- StopIteration raised on next call
            yield from ()

        mock_client = MagicMock()
        mock_client.events.return_value = _blocking_event_gen()

        with patch("app.core.sandbox_pool.docker") as mock_docker_mod:
            mock_docker_mod.from_env.return_value = mock_client

            monitor_task = asyncio.create_task(pool._monitor_docker_events())
            await asyncio.sleep(0.1)

            # Signal shutdown
            pool._stopping = True

            # Should exit within a reasonable time (the thread will unblock)
            try:
                await asyncio.wait_for(monitor_task, timeout=2.0)
            except TimeoutError:
                monitor_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await monitor_task
                pytest.fail("_monitor_docker_events did not exit within 2s after _stopping=True")

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_reconnects_after_docker_api_error(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """Monitor reconnects after a Docker API error with backoff."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=4, warmup_interval=300)

        connect_attempts = 0

        def _failing_from_env():
            nonlocal connect_attempts
            connect_attempts += 1
            if connect_attempts >= 3:
                pool._stopping = True
            raise ConnectionError("Docker daemon unavailable")

        with (
            patch("app.core.sandbox_pool.docker") as mock_docker_mod,
            patch("app.core.sandbox_pool.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_docker_mod.from_env.side_effect = _failing_from_env

            monitor_task = asyncio.create_task(pool._monitor_docker_events())

            try:
                await asyncio.wait_for(monitor_task, timeout=2.0)
            except TimeoutError:
                monitor_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await monitor_task

        # Should have retried at least twice before stopping
        assert connect_attempts >= 2
        # Should have called sleep(5) between retries
        assert mock_sleep.await_count >= 1
        mock_sleep.assert_awaited_with(5)

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_stream_end_triggers_reconnect(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """When the event stream ends (StopIteration), monitor reconnects."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=4, warmup_interval=300)

        events_call_count = 0

        def _empty_then_stop(**kwargs):
            """Return an empty generator, then stop on third call."""
            nonlocal events_call_count
            events_call_count += 1
            if events_call_count >= 3:
                pool._stopping = True
                raise RuntimeError("stopping")
            return iter([])  # Empty stream -- immediate StopIteration

        mock_client = MagicMock()
        mock_client.events.side_effect = _empty_then_stop

        with patch("app.core.sandbox_pool.docker") as mock_docker_mod:
            mock_docker_mod.from_env.return_value = mock_client

            monitor_task = asyncio.create_task(pool._monitor_docker_events())

            try:
                await asyncio.wait_for(monitor_task, timeout=2.0)
            except TimeoutError:
                pool._stopping = True
                monitor_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await monitor_task

        # events() was called multiple times due to reconnection
        assert events_call_count >= 2


class TestProcessDockerEvent:
    """Tests for _process_docker_event OOM kill detection and pool management."""

    @pytest.mark.asyncio
    @patch("app.core.sandbox_pool.record_sandbox_oom_kill")
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_oom_kill_detected_by_exit_code_137(
        self,
        mock_settings: MagicMock,
        mock_prewarm: AsyncMock,
        mock_record_oom: MagicMock,
    ) -> None:
        """Exit code 137 triggers OOM kill detection."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=4, warmup_interval=300)

        event = {
            "Actor": {
                "ID": "abc123456789extra",
                "Attributes": {"exitCode": "137", "oomKilled": "false"},
            }
        }

        await pool._process_docker_event(event)

        mock_record_oom.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.core.sandbox_pool.record_sandbox_oom_kill")
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_oom_kill_detected_by_oom_flag(
        self,
        mock_settings: MagicMock,
        mock_prewarm: AsyncMock,
        mock_record_oom: MagicMock,
    ) -> None:
        """oomKilled=true attribute triggers OOM kill detection."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=4, warmup_interval=300)

        event = {
            "Actor": {
                "ID": "def456789012extra",
                "Attributes": {"exitCode": "1", "oomKilled": "true"},
            }
        }

        await pool._process_docker_event(event)

        mock_record_oom.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.core.sandbox_pool.record_sandbox_oom_kill")
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_non_oom_event_ignored(
        self,
        mock_settings: MagicMock,
        mock_prewarm: AsyncMock,
        mock_record_oom: MagicMock,
    ) -> None:
        """Normal exit (non-137, non-OOM) does not trigger OOM detection."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=4, warmup_interval=300)

        event = {
            "Actor": {
                "ID": "ghi789012345extra",
                "Attributes": {"exitCode": "0", "oomKilled": "false"},
            }
        }

        await pool._process_docker_event(event)

        mock_record_oom.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.core.sandbox_pool.record_sandbox_oom_kill")
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_oom_removes_sandbox_from_pool(
        self,
        mock_settings: MagicMock,
        mock_prewarm: AsyncMock,
        mock_record_oom: MagicMock,
    ) -> None:
        """OOM kill removes the matching sandbox from the pool and triggers replenishment."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=1, max_pool_size=4, warmup_interval=300)

        # Add sandboxes to pool
        sb_target = _make_mock_sandbox("sb-target")
        sb_target.container_id = "abc123456789"
        sb_other = _make_mock_sandbox("sb-other")
        sb_other.container_id = "zzz999888777"

        pool._pool.put_nowait(sb_target)
        pool._pool.put_nowait(sb_other)
        assert pool.size == 2

        event = {
            "Actor": {
                "ID": "abc123456789extra",  # First 12 chars match sb_target
                "Attributes": {"exitCode": "137", "oomKilled": "false"},
            }
        }

        with patch.object(pool, "_replenish_one", new_callable=AsyncMock) as mock_replenish:
            await pool._process_docker_event(event)
            mock_replenish.assert_awaited_once()

        # Only the non-matching sandbox should remain
        assert pool.size == 1
        remaining = pool._pool.get_nowait()
        assert remaining.container_id == "zzz999888777"

    @pytest.mark.asyncio
    @patch("app.core.sandbox_pool.record_sandbox_oom_kill")
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_oom_no_replenish_when_not_in_pool(
        self,
        mock_settings: MagicMock,
        mock_prewarm: AsyncMock,
        mock_record_oom: MagicMock,
    ) -> None:
        """OOM kill for an unknown container does not trigger replenishment."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=4, warmup_interval=300)

        event = {
            "Actor": {
                "ID": "unknown123456extra",
                "Attributes": {"exitCode": "137", "oomKilled": "false"},
            }
        }

        with patch.object(pool, "_replenish_one", new_callable=AsyncMock) as mock_replenish:
            await pool._process_docker_event(event)
            mock_replenish.assert_not_awaited()

        # OOM was still recorded even though container wasn't in pool
        mock_record_oom.assert_called_once()

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_malformed_event_handled_gracefully(
        self,
        mock_settings: MagicMock,
        mock_prewarm: AsyncMock,
    ) -> None:
        """Malformed events do not crash the processing method."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = SandboxPool(sandbox_cls, min_pool_size=0, max_pool_size=4, warmup_interval=300)

        # Event with missing Actor
        await pool._process_docker_event({})

        # Event with None Actor
        await pool._process_docker_event({"Actor": None})

        # Empty event — should not raise
        assert pool.size == 0  # Pool unchanged


# ---------------------------------------------------------------------------
# Global Singleton Helpers
# ---------------------------------------------------------------------------


class TestGlobalHelpers:
    """Tests for module-level get_sandbox_pool, start_sandbox_pool, stop_sandbox_pool."""

    @pytest.fixture(autouse=True)
    def _reset_global_pool(self) -> None:
        """Reset the global _sandbox_pool before/after each test."""
        import app.core.sandbox_pool as mod

        original = mod._sandbox_pool
        mod._sandbox_pool = None
        yield
        mod._sandbox_pool = original

    @pytest.mark.asyncio
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_get_sandbox_pool_creates_instance(self, mock_settings: MagicMock) -> None:
        """get_sandbox_pool creates the pool on first call."""
        sandbox_cls = MagicMock()
        pool = await get_sandbox_pool(sandbox_cls)

        assert isinstance(pool, SandboxPool)
        assert pool._sandbox_cls is sandbox_cls

    @pytest.mark.asyncio
    async def test_get_sandbox_pool_raises_without_cls(self) -> None:
        """get_sandbox_pool raises RuntimeError if sandbox_cls not provided on first call."""
        with pytest.raises(RuntimeError, match="sandbox_cls must be provided"):
            await get_sandbox_pool(None)

    @pytest.mark.asyncio
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_get_sandbox_pool_returns_same_instance(self, mock_settings: MagicMock) -> None:
        """get_sandbox_pool returns the same instance on subsequent calls."""
        sandbox_cls = MagicMock()
        pool1 = await get_sandbox_pool(sandbox_cls)
        pool2 = await get_sandbox_pool()

        assert pool1 is pool2

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_start_sandbox_pool(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """start_sandbox_pool creates, starts, and returns the pool."""
        sandbox_cls = _make_mock_sandbox_cls()
        pool = await start_sandbox_pool(sandbox_cls)

        assert pool.is_started is True

        await pool.stop()

    @pytest.mark.asyncio
    @patch(PREWARM_PATH, new_callable=AsyncMock)
    @patch(SETTINGS_PATH, return_value=_make_mock_settings())
    async def test_stop_sandbox_pool(self, mock_settings: MagicMock, mock_prewarm: AsyncMock) -> None:
        """stop_sandbox_pool stops and clears the global instance."""
        import app.core.sandbox_pool as mod

        sandbox_cls = _make_mock_sandbox_cls()
        await start_sandbox_pool(sandbox_cls)

        await stop_sandbox_pool()

        assert mod._sandbox_pool is None

    @pytest.mark.asyncio
    async def test_stop_sandbox_pool_when_none(self) -> None:
        """stop_sandbox_pool is a no-op when no pool exists."""
        await stop_sandbox_pool()  # should not raise
