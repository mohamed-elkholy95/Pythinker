"""
Sandbox Pool Manager - Phase 3: Sandbox Pre-warming

Maintains a pool of pre-warmed sandboxes for instant allocation,
reducing session initialization time from 15-20s to 2-5s.
"""

from asyncio import Queue, create_task, sleep, CancelledError
from typing import Optional, Type, TYPE_CHECKING
import asyncio
import logging

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
        sandbox_cls: Type["Sandbox"],
        min_pool_size: Optional[int] = None,
        max_pool_size: Optional[int] = None,
        warmup_interval: Optional[int] = None,
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
        self._pool: Queue["Sandbox"] = Queue(maxsize=self._max_size)
        self._warming_task: Optional[asyncio.Task] = None
        self._started = False
        self._stopping = False

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
            f"Starting sandbox pool (min={self._min_size}, max={self._max_size}, "
            f"interval={self._warmup_interval}s)"
        )

        # Start background maintenance loop
        self._warming_task = create_task(self._warm_pool_loop())

        # Initial warmup (don't await full completion, let it run in background)
        create_task(self._warm_pool())

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
            try:
                await self._warming_task
            except CancelledError:
                pass
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
                create_task(self._replenish_one())

            return sandbox

        except asyncio.TimeoutError:
            # Pool exhausted, create on-demand
            logger.warning(
                f"Sandbox pool exhausted (size={self._pool.qsize()}), creating on-demand"
            )
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
                            f"Sandbox pool: added sandbox {sandbox.id}, "
                            f"size={self._pool.qsize()}/{self._max_size}"
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

        Returns:
            A verified sandbox, or None if creation/verification failed
        """
        try:
            sandbox = await self._sandbox_cls.create()

            # Run full health check to ensure sandbox is ready
            if hasattr(sandbox, "ensure_sandbox"):
                await sandbox.ensure_sandbox()

            return sandbox

        except Exception as e:
            logger.error(f"Failed to create/verify sandbox for pool: {e}")
            return None

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
_sandbox_pool: Optional[SandboxPool] = None


async def get_sandbox_pool(sandbox_cls: Optional[Type["Sandbox"]] = None) -> SandboxPool:
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
            raise RuntimeError(
                "sandbox_cls must be provided when creating the sandbox pool"
            )
        _sandbox_pool = SandboxPool(sandbox_cls)

    return _sandbox_pool


async def start_sandbox_pool(sandbox_cls: Type["Sandbox"]) -> SandboxPool:
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
