"""Browser Connection Pool for efficient browser resource management.

This module provides connection pooling for PlaywrightBrowser instances,
reducing the overhead of creating new browser connections for each operation.

Key Features:
- Per-CDP-URL connection pooling
- Automatic health checking and reconnection
- Configurable pool size and timeout
- Thread-safe async operations
- Automatic cleanup of stale connections
"""

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser

logger = logging.getLogger(__name__)


@dataclass
class PooledConnection:
    """Represents a pooled browser connection with metadata."""

    browser: PlaywrightBrowser
    cdp_url: str
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    use_count: int = 0
    is_healthy: bool = True


class BrowserConnectionPool:
    """Connection pool for browser instances.

    Manages a pool of PlaywrightBrowser connections per CDP URL,
    providing efficient reuse and automatic health management.

    Usage:
        pool = BrowserConnectionPool.get_instance()
        async with pool.acquire(cdp_url) as browser:
            await browser.navigate("https://example.com")
    """

    _instance: "BrowserConnectionPool | None" = None
    _lock: asyncio.Lock | None = None

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
        # Load settings for defaults
        from app.core.config import get_settings

        settings = get_settings()

        self._pools: dict[str, list[PooledConnection]] = {}
        self._in_use: dict[str, set[int]] = {}  # Track connections in use by id
        self._pool_locks: dict[str, asyncio.Lock] = {}
        self._max_per_url = max_connections_per_url or settings.browser_pool_max_per_url
        self._timeout = connection_timeout or settings.browser_pool_timeout
        self._max_idle = max_idle_time or settings.browser_pool_max_idle
        self._health_interval = health_check_interval or settings.browser_pool_health_interval
        self._cleanup_task: asyncio.Task[Any] | None = None
        self._shutdown = False

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
        if cls._lock is None:
            cls._lock = asyncio.Lock()

        async with cls._lock:
            if cls._instance is None:
                cls._instance = BrowserConnectionPool()
                cls._instance._start_cleanup_task()
            return cls._instance

    def _start_cleanup_task(self) -> None:
        """Start the background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """Background task to clean up idle connections."""
        while not self._shutdown:
            try:
                await asyncio.sleep(self._health_interval)
                await self._cleanup_idle_connections()
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
                        try:
                            await conn.browser.cleanup()
                        except Exception as e:
                            logger.debug(f"Error cleaning up connection: {e}")
                    else:
                        cleaned.append(conn)

                self._pools[cdp_url] = cleaned

    def _get_pool_lock(self, cdp_url: str) -> asyncio.Lock:
        """Get or create a lock for a specific pool."""
        if cdp_url not in self._pool_locks:
            self._pool_locks[cdp_url] = asyncio.Lock()
        return self._pool_locks[cdp_url]

    async def acquire(
        self,
        cdp_url: str,
        block_resources: bool = False,
        randomize_fingerprint: bool = True,
    ) -> "PooledConnectionContext":
        """Acquire a browser connection from the pool.

        Args:
            cdp_url: Chrome DevTools Protocol URL
            block_resources: Whether to block resources
            randomize_fingerprint: Whether to randomize browser fingerprint

        Returns:
            Context manager yielding a PlaywrightBrowser instance
        """
        return PooledConnectionContext(
            pool=self,
            cdp_url=cdp_url,
            block_resources=block_resources,
            randomize_fingerprint=randomize_fingerprint,
        )

    async def _acquire_connection(
        self,
        cdp_url: str,
        block_resources: bool = False,
        randomize_fingerprint: bool = True,
    ) -> PooledConnection:
        """Internal method to acquire a connection."""
        lock = self._get_pool_lock(cdp_url)

        async with lock:
            # Initialize pool for this URL if needed
            if cdp_url not in self._pools:
                self._pools[cdp_url] = []
                self._in_use[cdp_url] = set()

            pool = self._pools[cdp_url]
            in_use = self._in_use[cdp_url]

            # Try to find an available healthy connection
            for conn in pool:
                conn_id = id(conn)
                if conn_id not in in_use and conn.is_healthy:
                    # Verify health before returning
                    if await self._verify_connection_health(conn):
                        in_use.add(conn_id)
                        conn.last_used_at = time.time()
                        conn.use_count += 1
                        logger.debug(f"Reusing pooled connection for {cdp_url} (use count: {conn.use_count})")
                        return conn
                    conn.is_healthy = False

            # No available connection, create new one if under limit
            if len(pool) < self._max_per_url:
                conn = await self._create_connection(cdp_url, block_resources, randomize_fingerprint)
                pool.append(conn)
                in_use.add(id(conn))
                logger.info(f"Created new pooled connection for {cdp_url} (pool size: {len(pool)})")
                return conn

            # Pool is full, wait for a connection to become available
            logger.warning(f"Pool full for {cdp_url}, waiting for available connection")

        # Wait outside the lock
        start_time = time.time()
        while time.time() - start_time < self._timeout:
            await asyncio.sleep(0.1)

            async with lock:
                for conn in pool:
                    conn_id = id(conn)
                    if conn_id not in in_use and conn.is_healthy and await self._verify_connection_health(conn):
                        in_use.add(conn_id)
                        conn.last_used_at = time.time()
                        conn.use_count += 1
                        return conn

        raise TimeoutError(f"Timeout waiting for available connection to {cdp_url}")

    async def _create_connection(
        self,
        cdp_url: str,
        block_resources: bool = False,
        randomize_fingerprint: bool = True,
    ) -> PooledConnection:
        """Create a new browser connection."""
        browser = PlaywrightBrowser(
            cdp_url=cdp_url,
            block_resources=block_resources,
            randomize_fingerprint=randomize_fingerprint,
        )

        # Initialize the browser connection
        success = await browser.initialize(clear_existing=False)
        if not success:
            raise ConnectionError(f"Failed to initialize browser for {cdp_url}")

        return PooledConnection(
            browser=browser,
            cdp_url=cdp_url,
        )

    async def _verify_connection_health(self, conn: PooledConnection) -> bool:
        """Verify a connection is still healthy."""
        try:
            if not conn.browser.is_connected():
                return False

            # Quick health check - verify page is responsive
            if conn.browser.page and not conn.browser.page.is_closed():
                await conn.browser.page.evaluate("() => true")
                return True
            return False
        except Exception as e:
            logger.debug(f"Connection health check failed: {e}")
            return False

    async def _release_connection(self, cdp_url: str, conn: PooledConnection) -> None:
        """Release a connection back to the pool."""
        lock = self._get_pool_lock(cdp_url)
        async with lock:
            in_use = self._in_use.get(cdp_url, set())
            conn_id = id(conn)
            if conn_id in in_use:
                in_use.discard(conn_id)
                conn.last_used_at = time.time()
                logger.debug(f"Released connection back to pool for {cdp_url}")

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
                try:
                    await conn.browser.cleanup()
                except Exception as e:
                    logger.debug(f"Error closing pooled connection: {e}")

        self._pools.clear()
        self._in_use.clear()
        self._pool_locks.clear()

        logger.info("Browser connection pool closed")

    def get_stats(self) -> dict[str, Any]:
        """Get pool statistics for monitoring."""
        stats: dict[str, Any] = {
            "pools": {},
            "total_connections": 0,
            "total_in_use": 0,
        }

        for cdp_url, connections in self._pools.items():
            in_use_count = len(self._in_use.get(cdp_url, set()))
            pool_stats = {
                "total": len(connections),
                "in_use": in_use_count,
                "available": len(connections) - in_use_count,
                "connections": [
                    {
                        "use_count": conn.use_count,
                        "age_seconds": time.time() - conn.created_at,
                        "idle_seconds": time.time() - conn.last_used_at,
                        "healthy": conn.is_healthy,
                    }
                    for conn in connections
                ],
            }
            stats["pools"][cdp_url] = pool_stats
            stats["total_connections"] += len(connections)
            stats["total_in_use"] += in_use_count

        return stats


class PooledConnectionContext:
    """Context manager for pooled connections."""

    def __init__(
        self,
        pool: BrowserConnectionPool,
        cdp_url: str,
        block_resources: bool = False,
        randomize_fingerprint: bool = True,
    ):
        self._pool = pool
        self._cdp_url = cdp_url
        self._block_resources = block_resources
        self._randomize_fingerprint = randomize_fingerprint
        self._connection: PooledConnection | None = None

    async def __aenter__(self) -> PlaywrightBrowser:
        """Acquire a connection from the pool."""
        self._connection = await self._pool._acquire_connection(
            self._cdp_url,
            self._block_resources,
            self._randomize_fingerprint,
        )
        return self._connection.browser

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Release the connection back to the pool."""
        if self._connection:
            # Mark as unhealthy if there was an exception
            if exc_type is not None:
                self._connection.is_healthy = False

            await self._pool._release_connection(self._cdp_url, self._connection)
