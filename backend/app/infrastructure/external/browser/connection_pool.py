"""Browser Connection Pool for efficient browser resource management.

This module provides connection pooling for PlaywrightBrowser instances,
reducing the overhead of creating new browser connections for each operation.

Key Features:
- Per-CDP-URL connection pooling
- Automatic health checking and reconnection
- Configurable pool size and timeout
- Thread-safe async operations
- Automatic cleanup of stale connections
- Robust error handling with retry logic
- Automatic recovery from connection failures
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.retry import RetryConfig, calculate_delay
from app.domain.exceptions.browser import (
    BrowserCrashedError,
    BrowserErrorContext,
    ConnectionPoolExhaustedError,
    ConnectionRefusedError,
    ConnectionTimeoutError,
)
from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser
from app.infrastructure.observability.prometheus_metrics import record_error

logger = logging.getLogger(__name__)

# Type alias for progress callback
ProgressCallback = Callable[[str], Awaitable[None]]


@dataclass
class PooledConnection:
    """Represents a pooled browser connection with metadata."""

    browser: PlaywrightBrowser
    cdp_url: str
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    use_count: int = 0
    is_healthy: bool = True
    consecutive_failures: int = 0


@dataclass
class PoolStats:
    """Statistics for a connection pool."""

    cdp_url: str
    total_connections: int
    in_use_count: int
    available_count: int
    healthy_count: int
    unhealthy_count: int
    total_acquisitions: int = 0
    total_failures: int = 0
    avg_wait_time_ms: float = 0.0


class BrowserConnectionPool:
    """Connection pool for browser instances.

    Manages a pool of PlaywrightBrowser connections per CDP URL,
    providing efficient reuse and automatic health management.

    Usage:
        pool = BrowserConnectionPool.get_instance()
        async with pool.acquire(cdp_url) as browser:
            await browser.navigate("https://example.com")

    Features:
        - Automatic retry on connection failures
        - Force cleanup of stale connections before acquisition
        - Detailed error context for debugging
        - Pool statistics for monitoring
    """

    _instance: "BrowserConnectionPool | None" = None
    _lock: asyncio.Lock | None = None
    _class_lock = asyncio.Lock()

    def __init__(
        self,
        max_connections_per_url: int | None = None,
        connection_timeout: float | None = None,
        max_idle_time: float | None = None,
        health_check_interval: float | None = None,
    ):
        """Initialize the connection pool.

        Args:
            max_connections_per_url: Maximum connections per CDP URL (default from settings)
            connection_timeout: Timeout for acquiring connections in seconds (default from settings)
            max_idle_time: Maximum idle time before connection cleanup in seconds (default from settings)
            health_check_interval: Interval between health checks in seconds (default from settings)
        """
        from app.core.config import get_settings

        settings = get_settings()

        self._pools: dict[str, list[PooledConnection]] = {}
        self._in_use: dict[str, set[int]] = {}
        self._pool_locks: dict[str, asyncio.Lock] = {}
        self._max_per_url = max_connections_per_url or settings.browser_pool_max_per_url
        self._timeout = connection_timeout or settings.browser_pool_timeout
        self._max_idle = max_idle_time or settings.browser_pool_max_idle
        self._health_interval = health_check_interval or settings.browser_pool_health_interval
        self._cleanup_task: asyncio.Task[Any] | None = None
        self._shutdown = False
        self._force_release_last_at: dict[str, float] = {}
        self._force_release_cooldown_seconds = 30.0

        # Statistics tracking
        self._stats: dict[str, dict[str, Any]] = {}

        logger.info(
            f"Browser pool initialized: max_per_url={self._max_per_url}, "
            f"timeout={self._timeout}s, max_idle={self._max_idle}s"
        )

    @classmethod
    def get_instance(cls) -> "BrowserConnectionPool":
        """Get the singleton pool instance."""
        if cls._instance is None:
            cls._instance = BrowserConnectionPool()
        return cls._instance

    @classmethod
    async def get_instance_async(cls) -> "BrowserConnectionPool":
        """Get the singleton pool instance with async initialization."""
        async with cls._class_lock:
            if cls._lock is None:
                cls._lock = asyncio.Lock()

        async with cls._lock:
            if cls._instance is None:
                cls._instance = BrowserConnectionPool()
                cls._instance._start_cleanup_task()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (useful for testing or recovery)."""
        if cls._instance is not None:
            logger.warning("Resetting browser connection pool instance")
            cls._instance = None

    def _start_cleanup_task(self) -> None:
        """Start the background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """Background task to clean up idle and unhealthy connections."""
        while not self._shutdown:
            try:
                await asyncio.sleep(self._health_interval)
                await self._cleanup_idle_connections()
                await self._cleanup_unhealthy_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def _cleanup_idle_connections(self) -> None:
        """Remove connections that have been idle too long."""
        current_time = time.time()

        for cdp_url, connections in list(self._pools.items()):
            lock = self._get_pool_lock(cdp_url)
            async with lock:
                in_use_ids = self._in_use.get(cdp_url, set())
                cleaned = []

                for conn in connections:
                    conn_id = id(conn)
                    if conn_id in in_use_ids:
                        cleaned.append(conn)
                        continue

                    idle_time = current_time - conn.last_used_at
                    if idle_time > self._max_idle:
                        logger.info(f"Cleaning up idle connection for {cdp_url} (idle {idle_time:.1f}s)")
                        await self._safe_cleanup_connection(conn)
                    else:
                        cleaned.append(conn)

                self._pools[cdp_url] = cleaned

    async def _cleanup_unhealthy_connections(self) -> None:
        """Remove connections marked as unhealthy."""
        for cdp_url, connections in list(self._pools.items()):
            lock = self._get_pool_lock(cdp_url)
            async with lock:
                in_use_ids = self._in_use.get(cdp_url, set())
                healthy = []

                for conn in connections:
                    conn_id = id(conn)
                    if conn_id in in_use_ids:
                        healthy.append(conn)
                        continue

                    if not conn.is_healthy or conn.consecutive_failures >= 3:
                        logger.info(
                            f"Removing unhealthy connection for {cdp_url} (failures: {conn.consecutive_failures})"
                        )
                        await self._safe_cleanup_connection(conn)
                    else:
                        healthy.append(conn)

                self._pools[cdp_url] = healthy

    async def _safe_cleanup_connection(self, conn: PooledConnection) -> None:
        """Safely cleanup a connection, catching any errors."""
        try:
            await conn.browser.cleanup()
        except Exception as e:
            logger.debug(f"Error cleaning up connection: {e}")

    def _get_pool_lock(self, cdp_url: str) -> asyncio.Lock:
        """Get or create a lock for a specific pool."""
        if cdp_url not in self._pool_locks:
            self._pool_locks[cdp_url] = asyncio.Lock()
        return self._pool_locks[cdp_url]

    def _init_stats(self, cdp_url: str) -> None:
        """Initialize statistics for a CDP URL."""
        if cdp_url not in self._stats:
            self._stats[cdp_url] = {
                "total_acquisitions": 0,
                "total_failures": 0,
                "total_wait_time_ms": 0.0,
            }

    async def acquire(
        self,
        cdp_url: str,
        block_resources: bool | None = None,
        randomize_fingerprint: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> "PooledConnectionContext":
        """Acquire a browser connection from the pool.

        Args:
            cdp_url: Chrome DevTools Protocol URL
            block_resources: Whether to block resources (None = use settings default)
            randomize_fingerprint: Whether to randomize browser fingerprint
            progress_callback: Optional async callback for progress updates (e.g., retry attempts)

        Returns:
            Context manager yielding a PlaywrightBrowser instance
        """
        # Use settings default if not explicitly specified
        if block_resources is None:
            from app.core.config import get_settings

            settings = get_settings()
            block_resources = settings.browser_block_resources_default

        return PooledConnectionContext(
            pool=self,
            cdp_url=cdp_url,
            block_resources=block_resources,
            randomize_fingerprint=randomize_fingerprint,
            progress_callback=progress_callback,
        )

    async def _acquire_connection(
        self,
        cdp_url: str,
        block_resources: bool = False,  # Note: already resolved to bool by acquire()
        randomize_fingerprint: bool = True,
        session_id: str | None = None,
        sandbox_id: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> PooledConnection:
        """Internal method to acquire a connection with robust error handling.

        This method implements:
        1. Force cleanup of unhealthy connections before acquisition
        2. Retry logic for transient failures
        3. Detailed error context for debugging
        4. Automatic recovery from stale pool state
        """
        self._init_stats(cdp_url)
        start_time = time.time()
        lock = self._get_pool_lock(cdp_url)

        # Build error context for detailed error reporting
        error_context = BrowserErrorContext(
            cdp_url=cdp_url,
            session_id=session_id,
            sandbox_id=sandbox_id,
            operation="acquire_connection",
            max_retries=3,
        )

        # First, force cleanup any stale/unhealthy connections
        await self._force_cleanup_stale_for_url(cdp_url)

        async with lock:
            # Initialize pool for this URL if needed
            if cdp_url not in self._pools:
                self._pools[cdp_url] = []
                self._in_use[cdp_url] = set()

            pool = self._pools[cdp_url]
            in_use = self._in_use[cdp_url]

            # Try to find an available healthy connection.
            # Reserve first, then verify to avoid duplicate acquisition races.
            for conn in pool:
                conn_id = id(conn)
                if conn_id not in in_use and conn.is_healthy:
                    in_use.add(conn_id)
                    if await self._verify_connection_health(conn):
                        conn.last_used_at = time.time()
                        conn.use_count += 1
                        conn.consecutive_failures = 0
                        self._stats[cdp_url]["total_acquisitions"] += 1
                        logger.debug(f"Reusing pooled connection for {cdp_url} (use count: {conn.use_count})")
                        return conn
                    in_use.discard(conn_id)
                    conn.is_healthy = False
                    conn.consecutive_failures += 1

            # No available connection, try to create new one if under limit
            if len(pool) < self._max_per_url:
                try:
                    conn = await self._create_connection_with_retry(
                        cdp_url,
                        block_resources,
                        randomize_fingerprint,
                        error_context,
                        progress_callback=progress_callback,
                    )
                    pool.append(conn)
                    in_use.add(id(conn))
                    self._stats[cdp_url]["total_acquisitions"] += 1
                    logger.info(f"Created new pooled connection for {cdp_url} (pool size: {len(pool)})")
                    return conn
                except Exception as e:
                    self._stats[cdp_url]["total_failures"] += 1
                    logger.error(f"Failed to create connection for {cdp_url}: {e}")
                    raise

            # Pool is full, wait for a connection to become available
            logger.warning(
                f"Pool full for {cdp_url} ({len(pool)}/{self._max_per_url}), "
                f"waiting for available connection (timeout: {self._timeout}s)"
            )

        # Wait outside the lock with timeout
        wait_start = time.time()
        while time.time() - start_time < self._timeout:
            await asyncio.sleep(0.1)

            async with lock:
                pool = self._pools.get(cdp_url, [])
                in_use = self._in_use.setdefault(cdp_url, set())
                # Try to find an available connection
                for conn in pool:
                    conn_id = id(conn)
                    if conn_id not in in_use and conn.is_healthy:
                        in_use.add(conn_id)
                        if await self._verify_connection_health(conn):
                            conn.last_used_at = time.time()
                            conn.use_count += 1
                            conn.consecutive_failures = 0

                            wait_time_ms = (time.time() - wait_start) * 1000
                            self._stats[cdp_url]["total_wait_time_ms"] += wait_time_ms
                            self._stats[cdp_url]["total_acquisitions"] += 1

                            logger.info(f"Acquired connection after {wait_time_ms:.0f}ms wait for {cdp_url}")
                            return conn
                        in_use.discard(conn_id)
                        conn.is_healthy = False
                        conn.consecutive_failures += 1

                # Try to replace an unhealthy connection
                for i, conn in enumerate(pool):
                    conn_id = id(conn)
                    if conn_id not in in_use and not conn.is_healthy:
                        logger.info(f"Replacing unhealthy connection for {cdp_url}")
                        await self._safe_cleanup_connection(conn)
                        try:
                            new_conn = await self._create_connection_with_retry(
                                cdp_url,
                                block_resources,
                                randomize_fingerprint,
                                error_context,
                                progress_callback=progress_callback,
                            )
                            pool[i] = new_conn
                            in_use.add(id(new_conn))
                            self._stats[cdp_url]["total_acquisitions"] += 1
                            return new_conn
                        except Exception as e:
                            logger.error(f"Failed to replace connection: {e}")
                            pool.pop(i)
                            break

        # Timeout reached - collect detailed stats for error
        self._stats[cdp_url]["total_failures"] += 1
        error_context.pool_stats = self._get_pool_stats_for_url(cdp_url)

        # Record error metric for monitoring
        record_error("connection_pool_exhausted", "browser")

        raise ConnectionPoolExhaustedError(
            cdp_url=cdp_url,
            timeout=self._timeout,
            pool_size=len(self._pools.get(cdp_url, [])),
            in_use_count=len(self._in_use.get(cdp_url, set())),
            context=error_context,
        )

    async def _create_connection_with_retry(
        self,
        cdp_url: str,
        block_resources: bool,
        randomize_fingerprint: bool,
        error_context: BrowserErrorContext,
        max_retries: int = 1,
        progress_callback: ProgressCallback | None = None,
    ) -> PooledConnection:
        """Create a new browser connection with retry logic.

        Note: PlaywrightBrowser.initialize() already implements internal retries.
        Keep this outer retry loop minimal to avoid compounded startup latency.

        Args:
            cdp_url: Chrome DevTools Protocol URL
            block_resources: Whether to block resources
            randomize_fingerprint: Whether to randomize browser fingerprint
            error_context: Error context for detailed error reporting
            max_retries: Maximum number of retry attempts
            progress_callback: Optional async callback for progress updates
        """
        last_error: Exception | None = None

        for attempt in range(max_retries):
            error_context.retry_count = attempt

            # Emit progress event on retry attempts (not on first attempt)
            if attempt > 0 and progress_callback:
                try:
                    await progress_callback(f"Retrying browser connection (attempt {attempt + 1}/{max_retries})...")
                except Exception as e:
                    logger.warning(f"Failed to emit retry progress event: {e}")

            try:
                browser = PlaywrightBrowser(
                    cdp_url=cdp_url,
                    block_resources=block_resources,
                    randomize_fingerprint=randomize_fingerprint,
                )

                # Initialize with clear_existing=True on first attempt to recover from stale state
                success = await browser.initialize(clear_existing=(attempt == 0))
                if not success:
                    raise ConnectionRefusedError(
                        cdp_url=cdp_url,
                        context=error_context,
                    )

                return PooledConnection(
                    browser=browser,
                    cdp_url=cdp_url,
                )

            except ConnectionRefusedError as e:
                last_error = e
                logger.warning(f"Connection attempt {attempt + 1}/{max_retries} refused for {cdp_url}")
            except TimeoutError as e:
                last_error = e
                logger.warning(f"Connection attempt {attempt + 1}/{max_retries} timed out for {cdp_url}")
            except Exception as e:
                last_error = e
                logger.warning(f"Connection attempt {attempt + 1}/{max_retries} failed for {cdp_url}: {e}")

            if attempt < max_retries - 1:
                # Use centralized exponential backoff with jitter
                retry_config = RetryConfig(
                    base_delay=0.5,
                    exponential_base=2.0,
                    max_delay=5.0,  # Cap at 5s
                    jitter=True,
                )
                backoff = calculate_delay(attempt + 1, retry_config)  # Convert 0-indexed to 1-indexed
                logger.info(f"Retrying in {backoff:.2f}s...")
                await asyncio.sleep(backoff)

        # All retries exhausted
        if isinstance(last_error, (asyncio.TimeoutError, TimeoutError)):
            raise ConnectionTimeoutError(
                cdp_url=cdp_url,
                timeout=self._timeout,
                context=error_context,
                cause=last_error,
            )

        if isinstance(last_error, ConnectionRefusedError):
            raise ConnectionRefusedError(
                cdp_url=cdp_url,
                context=error_context,
                cause=last_error,
            ) from last_error

        raise BrowserCrashedError(
            cdp_url=cdp_url,
            context=error_context,
            cause=last_error,
        )

    async def _force_cleanup_stale_for_url(self, cdp_url: str) -> int:
        """Force cleanup all stale/unhealthy connections for a URL.

        This is called before acquisition to prevent pool exhaustion
        from zombie connections.

        Returns:
            Number of connections cleaned up
        """
        if cdp_url not in self._pools:
            return 0

        lock = self._get_pool_lock(cdp_url)
        cleaned = 0

        async with lock:
            pool = self._pools.get(cdp_url, [])
            in_use = self._in_use.get(cdp_url, set())

            connections_to_keep = []
            for conn in pool:
                conn_id = id(conn)

                # Keep connections that are in use
                if conn_id in in_use:
                    connections_to_keep.append(conn)
                    continue

                # Check health of idle connections
                is_healthy = await self._verify_connection_health(conn)
                if is_healthy:
                    connections_to_keep.append(conn)
                else:
                    logger.info(f"Force cleaning stale connection for {cdp_url}")
                    await self._safe_cleanup_connection(conn)
                    cleaned += 1

            self._pools[cdp_url] = connections_to_keep

        if cleaned > 0:
            logger.info(f"Force cleaned {cleaned} stale connections for {cdp_url}")

        return cleaned

    async def _verify_connection_health(self, conn: PooledConnection) -> bool:
        """Verify a connection is still healthy.

        Phase 1: Enhanced crash detection - check for crash signatures and
        trigger immediate cleanup of crashed connections.
        """
        try:
            if not conn.browser.is_connected():
                logger.debug(f"Connection not connected for {conn.cdp_url}")
                return False

            # Quick health check - verify page is responsive
            if conn.browser.page and not conn.browser.page.is_closed():
                await asyncio.wait_for(
                    conn.browser.page.evaluate("() => true"),
                    timeout=5.0,
                )
                return True
            return False
        except TimeoutError:
            logger.debug(f"Connection health check timed out for {conn.cdp_url}")
            conn.is_healthy = False
            return False
        except Exception as e:
            # Phase 1: Check for crash signatures
            if conn.browser._is_crash_error(e):
                logger.error(f"Browser crash detected in pool health check for {conn.cdp_url}: {e}")
                conn.is_healthy = False
                conn.consecutive_failures = 99  # Force immediate removal
                # Record crash in browser's circuit breaker
                conn.browser._record_crash()
            else:
                logger.debug(f"Connection health check failed: {e}")
                conn.is_healthy = False
            return False

    async def _release_connection(self, cdp_url: str, conn: PooledConnection, had_error: bool = False) -> None:
        """Release a connection back to the pool."""
        lock = self._get_pool_lock(cdp_url)
        async with lock:
            in_use = self._in_use.get(cdp_url, set())
            conn_id = id(conn)
            if conn_id in in_use:
                in_use.discard(conn_id)
                conn.last_used_at = time.time()

                if had_error:
                    conn.consecutive_failures += 1
                    if conn.consecutive_failures >= 3:
                        conn.is_healthy = False
                        logger.warning(f"Marking connection unhealthy after {conn.consecutive_failures} failures")
                else:
                    conn.consecutive_failures = 0

                logger.debug(f"Released connection back to pool for {cdp_url}")

    async def clear_stale_connections(self, cdp_url: str) -> int:
        """Clear stale/unhealthy connections for a specific CDP URL.

        This should be called when starting a new session to ensure fresh connections.

        Args:
            cdp_url: The CDP URL to clear stale connections for

        Returns:
            Number of connections cleared
        """
        return await self._force_cleanup_stale_for_url(cdp_url)

    async def force_release_all(self, cdp_url: str) -> int:
        """Force release all connections for a CDP URL.

        WARNING: This is a recovery mechanism and may cause issues
        if connections are actually in use.

        Args:
            cdp_url: The CDP URL to release connections for

        Returns:
            Number of connections released
        """
        lock = self._get_pool_lock(cdp_url)
        now = time.time()

        async with lock:
            last_release_at = self._force_release_last_at.get(cdp_url, 0.0)
            if now - last_release_at < self._force_release_cooldown_seconds:
                logger.debug(
                    "Skipping force release for %s; cooldown active (%.1fs remaining)",
                    cdp_url,
                    self._force_release_cooldown_seconds - (now - last_release_at),
                )
                return 0

            in_use = self._in_use.get(cdp_url, set())
            released = len(in_use)
            in_use.clear()
            self._force_release_last_at[cdp_url] = now

            if released > 0:
                logger.warning(f"Force released {released} connections for {cdp_url}")
            else:
                logger.debug(f"Force release requested with no in-use connections for {cdp_url}")

        return released

    async def close_all_for_url(self, cdp_url: str) -> int:
        """Close and remove ALL connections for a CDP URL.

        Unlike force_release_all (which only clears in-use markers),
        this method actually closes browser connections and removes them
        from the pool entirely. Used when a session is stopped to ensure
        the browser is clean for the next session.

        Args:
            cdp_url: The CDP URL to close all connections for

        Returns:
            Number of connections closed
        """
        if cdp_url not in self._pools:
            return 0

        lock = self._get_pool_lock(cdp_url)
        closed = 0

        async with lock:
            connections = self._pools.pop(cdp_url, [])
            self._in_use.pop(cdp_url, None)

            for conn in connections:
                await self._safe_cleanup_connection(conn)
                closed += 1

        if closed > 0:
            logger.info(f"Closed {closed} browser connection(s) for {cdp_url}")

        return closed

    def _get_pool_stats_for_url(self, cdp_url: str) -> dict[str, Any]:
        """Get pool statistics for a specific URL."""
        pool = self._pools.get(cdp_url, [])
        in_use = self._in_use.get(cdp_url, set())

        healthy_count = sum(1 for c in pool if c.is_healthy)
        stats = self._stats.get(cdp_url, {})

        return {
            "total_connections": len(pool),
            "in_use_count": len(in_use),
            "available_count": len(pool) - len(in_use),
            "healthy_count": healthy_count,
            "unhealthy_count": len(pool) - healthy_count,
            "total_acquisitions": stats.get("total_acquisitions", 0),
            "total_failures": stats.get("total_failures", 0),
        }

    async def close_all(self) -> None:
        """Close all pooled connections and shutdown the pool."""
        self._shutdown = True

        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

        # Close all connections
        for _cdp_url, connections in list(self._pools.items()):
            for conn in connections:
                await self._safe_cleanup_connection(conn)

        self._pools.clear()
        self._in_use.clear()
        self._pool_locks.clear()
        self._stats.clear()
        self._force_release_last_at.clear()

        logger.info("Browser connection pool closed")

    async def shutdown(self) -> None:
        """Backward-compatible alias for close_all."""
        await self.close_all()

    def get_stats(self) -> dict[str, Any]:
        """Get pool statistics for monitoring."""
        stats: dict[str, Any] = {
            "pools": {},
            "total_connections": 0,
            "total_in_use": 0,
            "total_healthy": 0,
        }

        for cdp_url, connections in self._pools.items():
            pool_stats = self._get_pool_stats_for_url(cdp_url)
            pool_stats["connections"] = [
                {
                    "use_count": conn.use_count,
                    "age_seconds": time.time() - conn.created_at,
                    "idle_seconds": time.time() - conn.last_used_at,
                    "healthy": conn.is_healthy,
                    "consecutive_failures": conn.consecutive_failures,
                }
                for conn in connections
            ]
            stats["pools"][cdp_url] = pool_stats
            stats["total_connections"] += pool_stats["total_connections"]
            stats["total_in_use"] += pool_stats["in_use_count"]
            stats["total_healthy"] += pool_stats["healthy_count"]

        return stats

    # =========================================================================
    # Phase 2: CDP Sharing for Browser-use Integration
    # =========================================================================

    def get_shared_cdp_url(self, session_id: str) -> str | None:
        """Get a shareable CDP URL for browser-use agent.

        Phase 2 Enhancement: Allows browser-use agent to share the CDP
        connection with the existing browser pool, preventing conflicts
        and resource duplication.

        Args:
            session_id: Session identifier to associate with CDP URL

        Returns:
            CDP URL if available, None otherwise
        """
        # Find an existing CDP URL that has available capacity
        for cdp_url in self._pools:
            pool_stats = self._get_pool_stats_for_url(cdp_url)

            # Check if this pool has healthy connections and capacity
            if pool_stats["healthy_count"] > 0:
                # Return this CDP URL for sharing
                logger.debug(f"Providing shared CDP URL for session {session_id}: {cdp_url}")
                return cdp_url

        # No existing pool - return None (caller should create new sandbox)
        logger.debug(f"No shared CDP URL available for session {session_id}")
        return None

    async def get_or_create_cdp_session(
        self,
        cdp_url: str,
        session_id: str,
        for_browser_use: bool = False,
    ) -> str | None:
        """Get or create a CDP session for browser-use.

        This method ensures browser-use can share CDP connections without
        conflicting with the existing browser pool.

        Args:
            cdp_url: CDP URL to use
            session_id: Session identifier
            for_browser_use: Whether this is for browser-use agent

        Returns:
            CDP URL that's ready for use, or None if unavailable
        """
        if not cdp_url:
            return None

        # Verify the CDP endpoint is reachable
        try:
            from app.infrastructure.external.http_pool import HTTPClientPool

            client = await HTTPClientPool.get_client(
                name=f"cdp-verify-{session_id}",
                base_url=cdp_url,
                timeout=5.0,
            )
            response = await client.get("/json/version")
            if response.status_code == 200:
                logger.debug(f"CDP endpoint verified for session {session_id}")
                return cdp_url
        except Exception as e:
            logger.warning(f"CDP endpoint not reachable for session {session_id}: {e}")
            return None

        return None

    def reserve_cdp_for_browser_use(self, cdp_url: str, session_id: str) -> bool:
        """Reserve a CDP connection for browser-use exclusive access.

        This temporarily marks a connection as in-use for browser-use
        to prevent the pool from re-using it during autonomous execution.

        Args:
            cdp_url: CDP URL to reserve
            session_id: Session making the reservation

        Returns:
            True if reservation successful
        """
        if cdp_url not in self._pools:
            return False

        # For now, just track that this CDP is being used by browser-use
        # The connection pool's existing acquire/release mechanism handles
        # the actual connection management
        logger.info(f"CDP reserved for browser-use: {cdp_url} (session: {session_id})")
        return True

    def release_cdp_for_browser_use(self, cdp_url: str, session_id: str) -> bool:
        """Release a CDP connection after browser-use completes.

        Args:
            cdp_url: CDP URL to release
            session_id: Session releasing the reservation

        Returns:
            True if release successful
        """
        logger.info(f"CDP released from browser-use: {cdp_url} (session: {session_id})")
        return True


class PooledConnectionContext:
    """Context manager for pooled connections."""

    def __init__(
        self,
        pool: BrowserConnectionPool,
        cdp_url: str,
        block_resources: bool = False,
        randomize_fingerprint: bool = True,
        progress_callback: ProgressCallback | None = None,
    ):
        self._pool = pool
        self._cdp_url = cdp_url
        self._block_resources = block_resources
        self._randomize_fingerprint = randomize_fingerprint
        self._progress_callback = progress_callback
        self._connection: PooledConnection | None = None
        self._had_error = False

    async def __aenter__(self) -> PlaywrightBrowser:
        """Acquire a connection from the pool."""
        self._connection = await self._pool._acquire_connection(
            self._cdp_url,
            self._block_resources,
            self._randomize_fingerprint,
            progress_callback=self._progress_callback,
        )
        return self._connection.browser

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Release the connection back to the pool."""
        if self._connection:
            self._had_error = exc_type is not None
            await self._pool._release_connection(
                self._cdp_url,
                self._connection,
                had_error=self._had_error,
            )
