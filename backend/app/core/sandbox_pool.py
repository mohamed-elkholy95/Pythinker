"""
Sandbox Pool Manager - Enhanced for 2 Concurrent Tasks

Maintains a pool of pre-warmed sandboxes for instant allocation,
reducing session initialization time from 15-20s to 2-5s.

Enhancements:
- Docker pause/unpause for idle pooled sandboxes (CPU reclamation)
- Idle TTL eviction to prevent stale resource consumption
- Host memory pressure guard to avoid over-provisioning
- Container image pre-pull on startup
- Periodic orphan reaper for crash recovery
- Pool statistics counters for monitoring
"""

import asyncio
import contextlib
import logging
import time
from asyncio import CancelledError, Queue, create_task, sleep
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Optional

import docker
from docker.errors import NotFound as DockerNotFound

from app.core import config as core_config
from app.core.prometheus_metrics import (
    record_sandbox_health_check,
    record_sandbox_oom_kill,
    record_sandbox_runtime_crash,
)

if TYPE_CHECKING:
    from app.domain.external.sandbox import Sandbox

logger = logging.getLogger(__name__)


def get_settings():
    """Resolve settings at call-time to support multiple patch targets in tests."""
    return core_config.get_settings()


# Soft dependency for host memory monitoring
try:
    import psutil

    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


class SandboxPool:
    """Manages a pool of pre-warmed sandboxes for instant allocation.

    The pool maintains a minimum number of ready-to-use sandboxes and
    automatically replenishes when sandboxes are acquired. Idle sandboxes
    are paused to reclaim CPU and evicted after a configurable TTL.

    Usage:
        pool = SandboxPool(DockerSandbox)
        await pool.start()

        # Get a pre-warmed sandbox (instant if pool has available)
        sandbox = await pool.acquire(timeout=5.0)

        # When done with the pool
        await pool.stop()
    """

    BROWSER_PREWARM_TIMEOUT_SECONDS = 12.0
    _PAUSE_DELAY_SECONDS = 5.0  # Delay before pausing a newly pooled sandbox
    _DEFAULT_IDLE_TTL_SECONDS = 300
    _DEFAULT_HOST_MEMORY_THRESHOLD = 0.80
    _DEFAULT_REAPER_INTERVAL_SECONDS = 60.0
    _DEFAULT_REAPER_GRACE_PERIOD_SECONDS = 120.0

    def __init__(
        self,
        sandbox_cls: type["Sandbox"],
        min_pool_size: int | None = None,
        max_pool_size: int | None = None,
        warmup_interval: int | None = None,
        *,
        min_size: int | None = None,
        max_size: int | None = None,
    ):
        # Backward compatibility with legacy constructor keyword names used in some tests/callers.
        if min_pool_size is None and min_size is not None:
            min_pool_size = min_size
        if max_pool_size is None and max_size is not None:
            max_pool_size = max_size

        settings = get_settings()
        self._sandbox_cls = sandbox_cls
        self._min_size = min_pool_size if min_pool_size is not None else settings.sandbox_pool_min_size
        self._max_size = max_pool_size if max_pool_size is not None else settings.sandbox_pool_max_size
        self._warmup_interval = (
            warmup_interval if warmup_interval is not None else settings.sandbox_pool_warmup_interval
        )
        self._pool: Queue[Sandbox] = Queue(maxsize=self._max_size)
        self._warming_task: asyncio.Task | None = None
        self._background_tasks: set[asyncio.Task] = set()
        self._started = False
        self._stopping = False

        # Priority 3: Health monitoring tasks
        self._health_monitor_task: asyncio.Task | None = None
        self._docker_events_task: asyncio.Task | None = None
        self._health_check_interval = self._coerce_non_negative_float(
            getattr(settings, "sandbox_health_check_interval", 30),
            default=30.0,
        )
        self._oom_monitor_enabled = self._coerce_bool(
            getattr(settings, "sandbox_oom_monitor_enabled", True),
            default=True,
        )

        # Circuit breaker for sandbox creation failures
        self._consecutive_failures = 0
        self._max_consecutive_failures = 5
        self._circuit_open = False
        self._circuit_reset_time: float = 0
        self._circuit_open_count = 0

        # Idle management settings
        self._idle_ttl = self._coerce_int(
            getattr(settings, "sandbox_pool_idle_ttl_seconds", self._DEFAULT_IDLE_TTL_SECONDS),
            default=self._DEFAULT_IDLE_TTL_SECONDS,
        )
        self._pause_idle = settings.sandbox_pool_pause_idle
        self._host_memory_threshold = self._coerce_float(
            getattr(settings, "sandbox_pool_host_memory_threshold", self._DEFAULT_HOST_MEMORY_THRESHOLD),
            default=self._DEFAULT_HOST_MEMORY_THRESHOLD,
        )
        self._reaper_interval = self._coerce_float(
            getattr(settings, "sandbox_pool_reaper_interval", self._DEFAULT_REAPER_INTERVAL_SECONDS),
            default=self._DEFAULT_REAPER_INTERVAL_SECONDS,
        )
        self._reaper_grace_period = self._coerce_float(
            getattr(settings, "sandbox_pool_reaper_grace_period", self._DEFAULT_REAPER_GRACE_PERIOD_SECONDS),
            default=self._DEFAULT_REAPER_GRACE_PERIOD_SECONDS,
        )

        # Pool entry timestamps: sandbox.id → time added to pool
        self._pool_timestamps: dict[str, float] = {}
        # Track paused sandbox IDs
        self._paused_ids: set[str] = set()

        # Async callback returning sandbox IDs held by active sessions.
        # Set via set_active_sandbox_provider() to avoid hard dependency on session layer.
        self._active_sandbox_provider: Callable[[], Awaitable[set[str]]] | None = None

        # Statistics counters
        self._total_acquisitions = 0
        self._total_on_demand = 0
        self._total_evictions = 0
        self._last_reaper_run: float = 0

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        """Coerce settings values to finite positive float with fallback."""
        if isinstance(value, bool):
            return default
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        if not (parsed > 0):
            return default
        return parsed

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        """Coerce settings values to positive int with fallback."""
        if isinstance(value, bool):
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        if parsed <= 0:
            return default
        return parsed

    @staticmethod
    def _coerce_non_negative_float(value: Any, default: float) -> float:
        """Coerce settings values to finite non-negative float with fallback."""
        if isinstance(value, bool):
            return default
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        if parsed < 0:
            return default
        return parsed

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        """Coerce settings values to boolean with fallback."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        return default

    @property
    def size(self) -> int:
        """Current number of sandboxes in the pool."""
        return self._pool.qsize()

    @property
    def is_started(self) -> bool:
        """Whether the pool has been started."""
        return self._started

    def get_pool_stats(self) -> dict[str, Any]:
        """Return pool statistics for monitoring endpoints."""
        return {
            "pool_size": self._pool.qsize(),
            "min_size": self._min_size,
            "max_size": self._max_size,
            "is_started": self._started,
            "circuit_open": self._circuit_open,
            "consecutive_failures": self._consecutive_failures,
            "circuit_open_count": self._circuit_open_count,
            "total_acquisitions": self._total_acquisitions,
            "total_on_demand_creates": self._total_on_demand,
            "total_evictions": self._total_evictions,
            "paused_count": len(self._paused_ids),
        }

    def set_active_sandbox_provider(self, provider: Callable[[], Awaitable[set[str]]]) -> None:
        """Set callback that returns sandbox IDs held by active sessions.

        Used by the orphan reaper to avoid killing containers that are
        in use but not tracked by the pool (e.g. acquired and running).

        Args:
            provider: Async callable returning a set of active sandbox IDs/names.
        """
        self._active_sandbox_provider = provider

    async def start(self) -> None:
        """Start the pool warmer.

        Pre-pulls the sandbox image, then performs initial warm-up
        and starts the background maintenance loop.
        """
        if self._started:
            logger.warning("Sandbox pool already started")
            return

        self._started = True
        self._stopping = False
        logger.info(
            f"Starting sandbox pool (min={self._min_size}, max={self._max_size}, interval={self._warmup_interval}s)"
        )

        # Pre-pull sandbox image to eliminate image pull latency
        await self._ensure_image_pulled()

        # Start background maintenance loop
        self._warming_task = create_task(self._warm_pool_loop())

        # Initial warmup (don't await full completion, let it run in background)
        task = create_task(self._warm_pool())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        # Priority 3: Start health monitoring tasks
        if self._health_check_interval > 0:
            self._health_monitor_task = create_task(self._continuous_health_monitor())
            logger.info(f"Started continuous health monitoring (interval={self._health_check_interval}s)")

        if self._oom_monitor_enabled:
            self._docker_events_task = create_task(self._monitor_docker_events())
            logger.info("Started Docker events monitoring for OOM detection")

        logger.info("Sandbox pool started")

    async def stop(self) -> None:
        """Stop the pool warmer and cleanup all pooled sandboxes."""
        if not self._started:
            return

        self._stopping = True
        logger.info("Stopping sandbox pool...")

        # Cancel the warming task
        if self._warming_task:
            self._warming_task.cancel()
            with contextlib.suppress(CancelledError):
                await self._warming_task
            self._warming_task = None

        # Priority 3: Cancel health monitoring tasks
        if self._health_monitor_task:
            self._health_monitor_task.cancel()
            with contextlib.suppress(CancelledError):
                await self._health_monitor_task
            self._health_monitor_task = None

        if self._docker_events_task:
            self._docker_events_task.cancel()
            with contextlib.suppress(CancelledError):
                await self._docker_events_task
            self._docker_events_task = None

        # Cleanup all pooled sandboxes (unpause first if paused, then destroy)
        cleanup_count = 0
        while not self._pool.empty():
            try:
                sandbox = self._pool.get_nowait()
                sandbox_id = getattr(sandbox, "id", "?")
                try:
                    # Unpause before destroy to avoid Docker API errors
                    if sandbox_id in self._paused_ids:
                        if hasattr(sandbox, "unpause"):
                            await asyncio.wait_for(sandbox.unpause(), timeout=5.0)
                        self._paused_ids.discard(sandbox_id)
                    await asyncio.wait_for(sandbox.destroy(), timeout=15.0)
                    cleanup_count += 1
                except TimeoutError:
                    logger.warning(f"Timeout destroying pooled sandbox {sandbox_id}")
                except Exception as e:
                    logger.warning(f"Error destroying pooled sandbox: {e}")
                finally:
                    self._pool_timestamps.pop(sandbox_id, None)
            except asyncio.QueueEmpty:
                break

        self._paused_ids.clear()
        self._pool_timestamps.clear()
        self._started = False
        logger.info(f"Sandbox pool stopped, cleaned up {cleanup_count} sandboxes")

    async def acquire(self, timeout: float = 30.0) -> "Sandbox":  # noqa: ASYNC109
        """Get a pre-warmed sandbox from the pool.

        If the pool has available sandboxes, returns immediately (unpausing if needed).
        If the pool is empty, waits up to timeout seconds for one to become available,
        then falls back to creating on-demand.

        Args:
            timeout: Maximum seconds to wait for a pooled sandbox

        Returns:
            A ready-to-use Sandbox instance
        """
        max_health_retries = 2
        for _attempt in range(max_health_retries + 1):
            try:
                sandbox = await asyncio.wait_for(self._pool.get(), timeout=min(timeout, 5.0))
                sandbox_id = getattr(sandbox, "id", "?")
                self._pool_timestamps.pop(sandbox_id, None)

                # Unpause if sandbox was paused
                if sandbox_id in self._paused_ids:
                    self._paused_ids.discard(sandbox_id)
                    if hasattr(sandbox, "unpause"):
                        await sandbox.unpause()
                        # Quick health check after unpause
                        try:
                            if hasattr(sandbox, "ensure_sandbox"):
                                await asyncio.wait_for(sandbox.ensure_sandbox(), timeout=10.0)
                        except (TimeoutError, Exception) as e:
                            logger.warning(
                                f"Unpaused sandbox {sandbox_id} failed health check: {e}, "
                                f"destroying (attempt {_attempt + 1}/{max_health_retries + 1})"
                            )
                            try:
                                await asyncio.wait_for(sandbox.destroy(), timeout=15.0)
                            except TimeoutError:
                                logger.warning(f"Timeout destroying unhealthy sandbox {sandbox_id}")
                            except Exception as destroy_error:
                                logger.warning(f"Error destroying unhealthy sandbox {sandbox_id}: {destroy_error}")
                            # Trigger replenishment and retry from pool
                            if not self._stopping:
                                task = create_task(self._replenish_one())
                                self._background_tasks.add(task)
                                task.add_done_callback(self._background_tasks.discard)
                            continue

                logger.info(f"Acquired sandbox from pool (remaining: {self._pool.qsize()})")

                # Trigger background replenishment
                if not self._stopping:
                    task = create_task(self._replenish_one())
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)

                self._total_acquisitions += 1
                return sandbox

            except TimeoutError:
                break

        # Pool exhausted or all health check retries failed, create on-demand
        self._total_on_demand += 1
        logger.warning(f"Sandbox pool exhausted (size={self._pool.qsize()}), creating on-demand")
        return await self._sandbox_cls.create()

    async def _warm_pool(self) -> None:
        """Fill pool to minimum size, respecting host memory pressure."""
        if self._check_host_memory_pressure():
            logger.warning("Host memory pressure high, skipping sandbox pre-warming")
            return

        while self._pool.qsize() < self._min_size and not self._stopping:
            if self._check_host_memory_pressure():
                logger.warning("Host memory pressure reached during warm-up, stopping")
                break
            try:
                sandbox = await self._create_and_verify_sandbox()
                if sandbox:
                    try:
                        self._pool.put_nowait(sandbox)
                        sandbox_id = getattr(sandbox, "id", "?")
                        self._pool_timestamps[sandbox_id] = time.time()
                        logger.info(
                            f"Sandbox pool: added sandbox {sandbox_id}, size={self._pool.qsize()}/{self._max_size}"
                        )
                        # Schedule deferred pause for idle CPU reclamation
                        if self._pause_idle and hasattr(sandbox, "pause"):
                            task = create_task(self._deferred_pause(sandbox))
                            self._background_tasks.add(task)
                            task.add_done_callback(self._background_tasks.discard)
                    except asyncio.QueueFull:
                        await sandbox.destroy()
                        break
            except Exception as e:
                logger.error(f"Failed to warm sandbox: {e}")
                await sleep(5)

    async def _create_and_verify_sandbox(self) -> Optional["Sandbox"]:
        """Create a sandbox and verify it's ready.

        Includes circuit breaker to prevent rapid failure loops
        and browser pre-warming for instant availability.

        Returns:
            A verified sandbox, or None if creation/verification failed
        """
        # Circuit breaker check
        if self._circuit_open:
            if time.time() < self._circuit_reset_time:
                logger.warning("Circuit breaker open - skipping sandbox creation")
                return None
            logger.info("Circuit breaker reset - attempting sandbox creation")
            self._circuit_open = False
            self._consecutive_failures = 0

        try:
            sandbox = await self._sandbox_cls.create()

            # Run full health check to ensure sandbox is ready
            if hasattr(sandbox, "ensure_sandbox"):
                await sandbox.ensure_sandbox()

            # Pre-warm browser context for instant use
            await self._prewarm_browser(sandbox)

            # Success - reset failure counters
            self._consecutive_failures = 0
            self._circuit_open_count = 0
            return sandbox

        except Exception as e:
            logger.error(f"Failed to create/verify sandbox for pool: {e}")
            self._consecutive_failures += 1

            # Open circuit breaker after too many failures (exponential backoff)
            if self._consecutive_failures >= self._max_consecutive_failures:
                self._circuit_open = True
                self._circuit_open_count += 1
                backoff_seconds = min(60 * (2 ** (self._circuit_open_count - 1)), 300)
                self._circuit_reset_time = time.time() + backoff_seconds
                logger.error(
                    f"Circuit breaker opened after {self._consecutive_failures} consecutive failures "
                    f"(open count: {self._circuit_open_count}). Will retry in {backoff_seconds} seconds."
                )

            return None

    async def _prewarm_browser(self, sandbox: "Sandbox") -> None:
        """Pre-warm browser context in sandbox for instant availability.

        Warms the Chrome browser via CDP. Disconnects Playwright but
        does NOT close the browser context - it stays ready for later use.
        """
        browser = None
        had_error = False
        release_browser = callable(getattr(sandbox, "release_pooled_browser", None))
        try:
            try:
                browser = await asyncio.wait_for(
                    sandbox.get_browser(clear_session=False, verify_connection=False, use_pool=True),
                    timeout=self.BROWSER_PREWARM_TIMEOUT_SECONDS,
                )
            except TypeError:
                browser = await asyncio.wait_for(
                    sandbox.get_browser(clear_session=False),
                    timeout=self.BROWSER_PREWARM_TIMEOUT_SECONDS,
                )

            if not browser:
                logger.warning(f"Browser pre-warm could not acquire browser for sandbox {sandbox.id}")
                return

            result = await asyncio.wait_for(
                browser.navigate("about:blank", timeout=10000, auto_extract=False),
                timeout=self.BROWSER_PREWARM_TIMEOUT_SECONDS,
            )

            if result.success:
                logger.info(f"Browser pre-warmed for pooled sandbox {sandbox.id}")
            else:
                logger.warning(f"Browser pre-warm navigation failed for sandbox {sandbox.id}: {result.message}")

        except TimeoutError:
            had_error = True
            logger.warning(
                "Browser pre-warm timed out after %.1fs for sandbox %s",
                self.BROWSER_PREWARM_TIMEOUT_SECONDS,
                sandbox.id,
            )
        except Exception as e:
            had_error = True
            logger.warning(f"Browser pre-warm failed (non-fatal) for sandbox {sandbox.id}: {e}")
        finally:
            if browser:
                released_to_pool = False
                try:
                    if release_browser:
                        released_to_pool = bool(await sandbox.release_pooled_browser(browser, had_error=had_error))
                    if not released_to_pool:
                        if callable(getattr(browser, "cleanup", None)):
                            await browser.cleanup()
                        else:
                            if getattr(browser, "playwright", None):
                                await browser.playwright.stop()
                            browser.page = None
                            browser.context = None
                            browser.browser = None
                            browser.playwright = None
                except Exception as pw_err:
                    logger.debug(f"Playwright disconnect error (non-fatal): {pw_err}")

    # --- Idle Container Management ---

    async def _deferred_pause(self, sandbox: "Sandbox") -> None:
        """Pause a sandbox after a short delay to allow immediate acquisition."""
        sandbox_id = getattr(sandbox, "id", "?")
        try:
            await sleep(self._PAUSE_DELAY_SECONDS)
            if self._stopping:
                return
            # Atomically reserve by popping timestamp before awaiting pause
            # to prevent TOCTOU race with concurrent acquire()
            timestamp = self._pool_timestamps.pop(sandbox_id, None)
            if timestamp is None:
                return  # Already acquired or evicted
            try:
                if await sandbox.pause():
                    self._paused_ids.add(sandbox_id)
                    self._pool_timestamps[sandbox_id] = timestamp
                    logger.info(f"Paused idle pooled sandbox {sandbox_id}")
                else:
                    self._pool_timestamps[sandbox_id] = timestamp
            except Exception:
                self._pool_timestamps[sandbox_id] = timestamp
                raise
        except CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Deferred pause failed for {sandbox_id}: {e}")

    async def _evict_stale_sandboxes(self) -> None:
        """Evict sandboxes that have been idle beyond the TTL.

        Only evicts down to min_size to always keep minimum warm.
        """
        now = time.time()
        to_evict: list[str] = []

        for sandbox_id, added_at in list(self._pool_timestamps.items()):
            if now - added_at > self._idle_ttl and self._pool.qsize() > self._min_size:
                to_evict.append(sandbox_id)

        if not to_evict:
            return

        # Drain pool, evict stale, re-queue the rest
        remaining: list = []
        evicted = 0
        while not self._pool.empty():
            try:
                sandbox = self._pool.get_nowait()
                sid = getattr(sandbox, "id", "?")
                if sid in to_evict:
                    try:
                        if sid in self._paused_ids:
                            if hasattr(sandbox, "unpause"):
                                await asyncio.wait_for(sandbox.unpause(), timeout=5.0)
                            self._paused_ids.discard(sid)
                        await asyncio.wait_for(sandbox.destroy(), timeout=15.0)
                        evicted += 1
                        self._total_evictions += 1
                    except Exception as e:
                        logger.warning(f"Error evicting stale sandbox {sid}: {e}")
                    self._pool_timestamps.pop(sid, None)
                else:
                    remaining.append(sandbox)
            except asyncio.QueueEmpty:
                break

        # Re-queue non-evicted sandboxes
        for sandbox in remaining:
            try:
                self._pool.put_nowait(sandbox)
            except asyncio.QueueFull:
                await sandbox.destroy()

        if evicted:
            logger.info(f"Evicted {evicted} stale sandboxes (TTL={self._idle_ttl}s)")

    def _check_host_memory_pressure(self) -> bool:
        """Return True if host memory usage exceeds threshold."""
        if not _HAS_PSUTIL:
            return False
        try:
            return psutil.virtual_memory().percent > (self._host_memory_threshold * 100)
        except Exception:
            return False

    # --- Image Pre-Pull ---

    async def _ensure_image_pulled(self) -> None:
        """Pre-pull sandbox image to eliminate image pull latency on first container creation."""
        settings = get_settings()
        if not settings.sandbox_image:
            return

        def _pull() -> None:
            try:
                dc = docker.from_env()
                try:
                    dc.images.get(settings.sandbox_image)
                    logger.info(f"Sandbox image already cached: {settings.sandbox_image}")
                except DockerNotFound:
                    logger.info(f"Pulling sandbox image: {settings.sandbox_image}")
                    dc.images.pull(settings.sandbox_image)
                    logger.info(f"Sandbox image pulled: {settings.sandbox_image}")
            except Exception as e:
                logger.warning(f"Image pre-pull failed (non-fatal): {e}")

        await asyncio.to_thread(_pull)

    # --- Orphan Reaper ---

    async def _reap_orphan_containers(self) -> int:
        """Detect and destroy sandbox containers not tracked by pool or active sessions.

        Returns:
            Number of orphan containers destroyed
        """
        settings = get_settings()
        prefix = settings.sandbox_name_prefix
        if not prefix:
            return 0

        now = time.time()
        pool_ids = set(self._pool_timestamps.keys())

        # Fetch active session sandbox IDs to avoid killing in-use containers
        active_session_ids: set[str] = set()
        if self._active_sandbox_provider:
            try:
                active_session_ids = await self._active_sandbox_provider()
            except Exception as e:
                logger.debug(f"Failed to fetch active session sandbox IDs: {e}")

        def _find_orphans() -> list[tuple[str, str, float]]:
            """Find containers matching sandbox prefix that aren't tracked."""
            orphans = []
            try:
                dc = docker.from_env()
                containers = dc.containers.list(all=True, filters={"name": prefix})
                for container in containers:
                    name = container.name
                    created_str = container.attrs.get("Created", "")
                    # Parse Docker creation timestamp to epoch
                    try:
                        from datetime import datetime

                        created_dt = datetime.fromisoformat(created_str)
                        created_epoch = created_dt.timestamp()
                    except Exception:
                        created_epoch = now  # Assume recent if can't parse
                    orphans.append((name, container.id[:12], created_epoch))
            except Exception as e:
                logger.debug(f"Orphan scan failed: {e}")
            return orphans

        candidates = await asyncio.to_thread(_find_orphans)
        if not candidates:
            return 0

        reaped = 0
        for name, container_id, created_epoch in candidates:
            # Skip containers younger than grace period
            if now - created_epoch < self._reaper_grace_period:
                continue
            # Skip containers tracked by the pool or held by active sessions
            known_ids = pool_ids | active_session_ids
            if name in known_ids or container_id in known_ids:
                continue
            # Destroy orphan
            try:

                def _remove(n: str) -> None:
                    dc = docker.from_env()
                    try:
                        c = dc.containers.get(n)
                        if c.status == "paused":
                            c.unpause()
                        c.remove(force=True)
                    except DockerNotFound:
                        pass

                await asyncio.to_thread(_remove, name)
                reaped += 1
                logger.info(f"Reaped orphan sandbox container: {name} ({container_id})")
            except Exception as e:
                logger.debug(f"Failed to reap orphan {name}: {e}")

        if reaped:
            logger.info(f"Orphan reaper: cleaned up {reaped} containers")
        return reaped

    # --- Priority 3: Health Monitoring ---

    async def _continuous_health_monitor(self) -> None:
        """Continuously monitor pooled sandboxes for crashes.

        Priority 3: Sandbox health monitoring - detect crashes proactively.
        Runs every N seconds checking all pooled sandboxes via Docker API.
        """
        while not self._stopping:
            try:
                await sleep(self._health_check_interval)
                if self._stopping:
                    break

                # Check health of all pooled sandboxes
                failed_sandboxes: list[Sandbox] = []
                pool_snapshot = list(self._pool._queue)  # type: ignore

                for sandbox in pool_snapshot:
                    try:
                        is_healthy = await self._check_sandbox_health(sandbox)
                        if is_healthy:
                            record_sandbox_health_check(status="success")
                        else:
                            record_sandbox_health_check(status="failure")
                            failed_sandboxes.append(sandbox)
                            logger.warning(
                                f"Health check failed for sandbox {sandbox.container_id}: container not running"
                            )
                    except Exception as e:
                        record_sandbox_health_check(status="error")
                        logger.error(f"Error checking sandbox health: {e}")

                # Remove failed sandboxes from pool
                for failed_sandbox in failed_sandboxes:
                    try:
                        # Remove from queue
                        temp_queue: asyncio.Queue[Sandbox] = asyncio.Queue()
                        while not self._pool.empty():
                            item = await self._pool.get()
                            if item != failed_sandbox:
                                await temp_queue.put(item)
                            else:
                                record_sandbox_runtime_crash()
                                logger.warning(f"Removed crashed sandbox from pool: {failed_sandbox.container_id}")
                        # Restore remaining sandboxes
                        while not temp_queue.empty():
                            await self._pool.put(await temp_queue.get())

                        # Clean up the failed sandbox
                        try:
                            await failed_sandbox.cleanup()
                        except Exception as cleanup_error:
                            logger.debug(f"Failed to cleanup crashed sandbox: {cleanup_error}")
                    except Exception as e:
                        logger.error(f"Error removing failed sandbox from pool: {e}")

                # Trigger replenishment if needed
                if failed_sandboxes and not self._stopping:
                    await self._replenish_one()

            except CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health monitor loop: {e}")
                await sleep(5)

    async def _check_sandbox_health(self, sandbox: "Sandbox") -> bool:
        """Check if a sandbox is still healthy using Docker API.

        Returns:
            True if healthy (container running/paused), False if crashed/exited.
        """
        try:
            # Use Docker API to verify container status
            def _check_container_status(container_id: str) -> str | None:
                import docker

                dc = docker.from_env()
                try:
                    container = dc.containers.get(container_id)
                    return container.status
                except docker.errors.NotFound:
                    return None

            status = await asyncio.to_thread(_check_container_status, sandbox.container_id)

            # Healthy states: running, paused
            # Unhealthy states: exited, dead, None (not found)
            if status in ("running", "paused"):
                return True

            logger.debug(f"Sandbox {sandbox.container_id} unhealthy: status={status}")
            return False

        except Exception as e:
            logger.error(f"Error checking sandbox health for {sandbox.container_id}: {e}")
            return False

    async def _monitor_docker_events(self) -> None:
        """Monitor Docker events for OOM kills and crashes.

        Priority 3: Instant OOM detection via Docker events API.
        Subscribes to 'die' events and checks for OOM kill exit codes.

        Uses per-event ``asyncio.to_thread(next, ...)`` so that each blocking
        read from the Docker daemon socket runs in a worker thread, keeping
        the event loop free for health checks and other coroutines.
        """
        sentinel = object()  # marker for StopIteration / stream end

        while not self._stopping:
            try:

                def _create_event_stream():
                    dc = docker.from_env()
                    return dc.events(
                        decode=True,
                        filters={"type": "container", "event": "die"},
                    )

                # Create the generator in a thread (connects to Docker daemon)
                events_gen = await asyncio.to_thread(_create_event_stream)

                def _read_next_event(gen=events_gen):
                    """Read one event from the generator (blocking).

                    Returns the event dict, or ``sentinel`` when the
                    stream is exhausted.
                    """
                    try:
                        return next(gen)
                    except StopIteration:
                        return sentinel

                # Non-blocking iteration: each next() runs in a worker thread
                while not self._stopping:
                    event = await asyncio.to_thread(_read_next_event)

                    if event is sentinel:
                        break  # Stream ended — reconnect via outer loop

                    await self._process_docker_event(event)

            except CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Docker events monitor: {e}")
                await sleep(5)

    async def _process_docker_event(self, event: dict[str, Any]) -> None:
        """Process a single Docker 'die' event.

        Detects OOM kills (exit code 137 or ``oomKilled`` attribute),
        removes the affected sandbox from the pool, and triggers
        replenishment.
        """
        try:
            container_id = event.get("Actor", {}).get("ID", "")[:12]
            attributes = event.get("Actor", {}).get("Attributes", {})
            exit_code = attributes.get("exitCode", "")
            oom_killed = attributes.get("oomKilled", "false") == "true"

            # Detect OOM kills (exit code 137 or oomKilled flag)
            if oom_killed or exit_code == "137":
                record_sandbox_oom_kill()
                logger.warning(
                    f"OOM kill detected for container {container_id} (exit_code={exit_code}, oomKilled={oom_killed})"
                )

                # Remove from pool if present
                temp_queue: asyncio.Queue[Sandbox] = asyncio.Queue()
                found = False
                while not self._pool.empty():
                    sandbox = await self._pool.get()
                    if sandbox.container_id == container_id:
                        found = True
                        logger.warning(f"Removed OOM-killed sandbox from pool: {container_id}")
                    else:
                        await temp_queue.put(sandbox)
                # Restore remaining
                while not temp_queue.empty():
                    await self._pool.put(await temp_queue.get())

                if found:
                    # Trigger replenishment
                    await self._replenish_one()

        except Exception as event_error:
            logger.debug(f"Error processing Docker event: {event_error}")

    # --- Background Loops ---

    async def _replenish_one(self) -> None:
        """Add one sandbox to pool if below minimum."""
        if self._pool.qsize() < self._min_size and not self._stopping:
            await self._warm_pool()

    async def _warm_pool_loop(self) -> None:
        """Background loop for pool maintenance: warm, evict, reap."""
        while not self._stopping:
            try:
                await sleep(self._warmup_interval)
                if self._stopping:
                    break

                # Evict stale sandboxes first
                await self._evict_stale_sandboxes()

                # Run orphan reaper periodically
                now = time.time()
                if now - self._last_reaper_run >= self._reaper_interval:
                    self._last_reaper_run = now
                    task = create_task(self._reap_orphan_containers())
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)

                # Replenish pool to minimum
                await self._warm_pool()
            except CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in pool maintenance loop: {e}")
                await sleep(5)


# Global singleton instance
_sandbox_pool: SandboxPool | None = None


async def get_sandbox_pool(sandbox_cls: type["Sandbox"] | None = None) -> SandboxPool:
    """Get or create the global sandbox pool instance.

    Args:
        sandbox_cls: Sandbox class to use (required on first call)

    Returns:
        The global SandboxPool instance

    Raises:
        RuntimeError: If sandbox_cls is not provided on first call
    """
    global _sandbox_pool

    if _sandbox_pool is None:
        if sandbox_cls is None:
            raise RuntimeError("sandbox_cls must be provided when creating the sandbox pool")
        _sandbox_pool = SandboxPool(sandbox_cls)

    return _sandbox_pool


async def start_sandbox_pool(sandbox_cls: type["Sandbox"]) -> SandboxPool:
    """Initialize and start the global sandbox pool.

    Call this during application startup.

    Args:
        sandbox_cls: Sandbox class to use (e.g., DockerSandbox)

    Returns:
        The started SandboxPool instance
    """
    pool = await get_sandbox_pool(sandbox_cls)
    if not pool.is_started:
        await pool.start()
    return pool


async def stop_sandbox_pool() -> None:
    """Stop and cleanup the global sandbox pool.

    Call this during application shutdown.
    """
    global _sandbox_pool

    if _sandbox_pool is not None:
        await _sandbox_pool.stop()
        _sandbox_pool = None
