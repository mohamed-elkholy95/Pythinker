"""
Sandbox Pool Manager - Phase 3: Sandbox Pre-warming

Maintains a pool of pre-warmed sandboxes for instant allocation,
reducing session initialization time from 15-20s to 2-5s.
"""

import asyncio
import contextlib
import logging
import time
from asyncio import CancelledError, Queue, create_task, sleep
from typing import TYPE_CHECKING, Optional

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.domain.external.sandbox import Sandbox

logger = logging.getLogger(__name__)


class SandboxPool:
    """Manages a pool of pre-warmed sandboxes for instant allocation.

    The pool maintains a minimum number of ready-to-use sandboxes and
    automatically replenishes when sandboxes are acquired.

    Usage:
        pool = SandboxPool(DockerSandbox)
        await pool.start()

        # Get a pre-warmed sandbox (instant if pool has available)
        sandbox = await pool.acquire(timeout=5.0)

        # When done with the pool
        await pool.stop()
    """

    def __init__(
        self,
        sandbox_cls: type["Sandbox"],
        min_pool_size: int | None = None,
        max_pool_size: int | None = None,
        warmup_interval: int | None = None,
    ):
        """Initialize the sandbox pool.

        Args:
            sandbox_cls: The sandbox class to instantiate (e.g., DockerSandbox)
            min_pool_size: Minimum sandboxes to maintain (default from config)
            max_pool_size: Maximum sandboxes in pool (default from config)
            warmup_interval: Seconds between maintenance checks (default from config)
        """
        settings = get_settings()
        self._sandbox_cls = sandbox_cls
        self._min_size = min_pool_size or settings.sandbox_pool_min_size
        self._max_size = max_pool_size or settings.sandbox_pool_max_size
        self._warmup_interval = warmup_interval or settings.sandbox_pool_warmup_interval
        self._pool: Queue[Sandbox] = Queue(maxsize=self._max_size)
        self._warming_task: asyncio.Task | None = None
        self._background_tasks: set[asyncio.Task] = set()
        self._started = False
        self._stopping = False
        # Circuit breaker for sandbox creation failures
        self._consecutive_failures = 0
        self._max_consecutive_failures = 5
        self._circuit_open = False
        self._circuit_reset_time: float = 0

    @property
    def size(self) -> int:
        """Current number of sandboxes in the pool."""
        return self._pool.qsize()

    @property
    def is_started(self) -> bool:
        """Whether the pool has been started."""
        return self._started

    async def start(self) -> None:
        """Start the pool warmer.

        This performs initial warm-up and starts the background maintenance loop.
        """
        if self._started:
            logger.warning("Sandbox pool already started")
            return

        self._started = True
        self._stopping = False
        logger.info(
            f"Starting sandbox pool (min={self._min_size}, max={self._max_size}, interval={self._warmup_interval}s)"
        )

        # Start background maintenance loop
        self._warming_task = create_task(self._warm_pool_loop())

        # Initial warmup (don't await full completion, let it run in background)
        task = create_task(self._warm_pool())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

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

        # Cleanup all pooled sandboxes
        cleanup_count = 0
        while not self._pool.empty():
            try:
                sandbox = self._pool.get_nowait()
                try:
                    await sandbox.destroy()
                    cleanup_count += 1
                except Exception as e:
                    logger.warning(f"Error destroying pooled sandbox: {e}")
            except asyncio.QueueEmpty:
                break

        self._started = False
        logger.info(f"Sandbox pool stopped, cleaned up {cleanup_count} sandboxes")

    async def acquire(self, timeout: float = 30.0) -> "Sandbox":
        """Get a pre-warmed sandbox from the pool.

        If the pool has available sandboxes, returns immediately.
        If the pool is empty, waits up to timeout seconds for one to become available,
        then falls back to creating on-demand.

        Args:
            timeout: Maximum seconds to wait for a pooled sandbox

        Returns:
            A ready-to-use Sandbox instance
        """
        try:
            # Try to get from pool with short timeout
            sandbox = await asyncio.wait_for(self._pool.get(), timeout=min(timeout, 5.0))
            logger.info(f"Acquired sandbox from pool (remaining: {self._pool.qsize()})")

            # Trigger background replenishment
            if not self._stopping:
                task = create_task(self._replenish_one())
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

            return sandbox

        except TimeoutError:
            # Pool exhausted, create on-demand
            logger.warning(f"Sandbox pool exhausted (size={self._pool.qsize()}), creating on-demand")
            return await self._sandbox_cls.create()

    async def _warm_pool(self) -> None:
        """Fill pool to minimum size."""
        while self._pool.qsize() < self._min_size and not self._stopping:
            try:
                sandbox = await self._create_and_verify_sandbox()
                if sandbox:
                    try:
                        self._pool.put_nowait(sandbox)
                        logger.info(
                            f"Sandbox pool: added sandbox {sandbox.id}, size={self._pool.qsize()}/{self._max_size}"
                        )
                    except asyncio.QueueFull:
                        # Pool is full, destroy the extra sandbox
                        await sandbox.destroy()
                        break
            except Exception as e:
                logger.error(f"Failed to warm sandbox: {e}")
                # Wait before retrying to avoid rapid failure loops
                await sleep(5)

    async def _create_and_verify_sandbox(self) -> Optional["Sandbox"]:
        """Create a sandbox and verify it's ready.

        Phase 1 enhancement: Also pre-warms browser for instant availability.
        Includes circuit breaker to prevent rapid failure loops.

        Returns:
            A verified sandbox, or None if creation/verification failed
        """
        # Circuit breaker check
        if self._circuit_open:
            if time.time() < self._circuit_reset_time:
                logger.warning("Circuit breaker open - skipping sandbox creation")
                return None
            # Try to reset circuit
            logger.info("Circuit breaker reset - attempting sandbox creation")
            self._circuit_open = False
            self._consecutive_failures = 0

        try:
            sandbox = await self._sandbox_cls.create()

            # Run full health check to ensure sandbox is ready
            if hasattr(sandbox, "ensure_sandbox"):
                await sandbox.ensure_sandbox()

            # Phase 1: Pre-warm browser context for instant use
            await self._prewarm_browser(sandbox)

            # Success - reset failure counter
            self._consecutive_failures = 0
            return sandbox

        except Exception as e:
            logger.error(f"Failed to create/verify sandbox for pool: {e}")
            self._consecutive_failures += 1

            # Open circuit breaker after too many failures
            if self._consecutive_failures >= self._max_consecutive_failures:
                self._circuit_open = True
                self._circuit_reset_time = time.time() + 60  # Reset after 60 seconds
                logger.error(
                    f"Circuit breaker opened after {self._consecutive_failures} consecutive failures. "
                    "Will retry in 60 seconds."
                )

            return None

    async def _prewarm_browser(self, sandbox: "Sandbox") -> None:
        """Pre-warm browser context in sandbox for instant availability.

        Phase 1 enhancement: Browser is ready immediately when sandbox is acquired.

        Note: This warms the Chrome browser via CDP. We disconnect Playwright
        but DO NOT close the browser context - it stays ready for later use.
        """
        browser = None
        try:
            # Get sandbox IP for CDP connection
            if not hasattr(sandbox, "ip_address") or not sandbox.ip_address:
                logger.debug(f"Sandbox {sandbox.id} has no IP address, skipping browser pre-warm")
                return

            # Import here to avoid circular dependency
            from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser

            # Create browser instance with CDP URL
            cdp_url = f"ws://{sandbox.ip_address}:9222"
            browser = PlaywrightBrowser(cdp_url=cdp_url)

            # Initialize browser (this connects to Chrome via CDP)
            if not await browser.initialize():
                logger.warning(f"Browser pre-warm initialization failed for sandbox {sandbox.id}")
                return

            # Navigate to blank page to fully initialize rendering pipeline
            result = await browser.navigate("about:blank", timeout=10000, auto_extract=False)

            if result.success:
                logger.info(f"Browser pre-warmed for pooled sandbox {sandbox.id}")
            else:
                logger.warning(f"Browser pre-warm navigation failed for sandbox {sandbox.id}: {result.message}")

        except Exception as e:
            # Non-fatal - browser will be initialized on first use
            logger.warning(f"Browser pre-warm failed (non-fatal) for sandbox {sandbox.id}: {e}")
        finally:
            # Disconnect Playwright but DO NOT close the browser context
            # The context needs to stay open for later use by the agent
            if browser:
                try:
                    # Only disconnect, don't close context/pages
                    if browser.playwright:
                        await browser.playwright.stop()
                    browser.page = None
                    browser.context = None
                    browser.browser = None
                    browser.playwright = None
                except Exception as cleanup_error:
                    logger.debug(f"Browser pre-warm disconnect error (non-fatal): {cleanup_error}")

    async def _replenish_one(self) -> None:
        """Add one sandbox to pool if below minimum."""
        if self._pool.qsize() < self._min_size and not self._stopping:
            await self._warm_pool()

    async def _warm_pool_loop(self) -> None:
        """Background loop to maintain pool at minimum size."""
        while not self._stopping:
            try:
                await sleep(self._warmup_interval)
                if not self._stopping:
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
