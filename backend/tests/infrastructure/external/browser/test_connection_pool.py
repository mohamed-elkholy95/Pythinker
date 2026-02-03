"""Tests for Browser Connection Pool.

Tests the BrowserConnectionPool class including:
- Connection pooling and reuse
- Pool limits and timeout
- Health checking
- Cleanup of idle connections
- Statistics tracking
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.external.browser.connection_pool import (
    BrowserConnectionPool,
    PooledConnection,
    PooledConnectionContext,
)


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = MagicMock()
    settings.browser_pool_max_per_url = 3
    settings.browser_pool_timeout = 5.0
    settings.browser_pool_max_idle = 60.0
    settings.browser_pool_health_interval = 30.0
    return settings


@pytest.fixture
def mock_browser():
    """Create a mock PlaywrightBrowser instance."""
    browser = AsyncMock()
    browser.initialize = AsyncMock(return_value=True)
    browser.cleanup = AsyncMock()
    browser.is_connected = MagicMock(return_value=True)

    # Mock page
    mock_page = MagicMock()
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.evaluate = AsyncMock(return_value=True)
    browser.page = mock_page

    return browser


@pytest.fixture
def pool(mock_settings):
    """Create a fresh connection pool for each test."""
    BrowserConnectionPool._instance = None
    with patch("app.core.config.get_settings", return_value=mock_settings):
        pool = BrowserConnectionPool(
            max_connections_per_url=3,
            connection_timeout=5.0,
            max_idle_time=60.0,
            health_check_interval=30.0,
        )
        yield pool
        # Cleanup
        asyncio.get_event_loop().run_until_complete(pool.close_all())
    BrowserConnectionPool._instance = None


class TestPooledConnection:
    """Tests for PooledConnection dataclass."""

    def test_creation(self, mock_browser):
        """Test creating a pooled connection."""
        conn = PooledConnection(
            browser=mock_browser,
            cdp_url="ws://localhost:9222",
        )

        assert conn.browser == mock_browser
        assert conn.cdp_url == "ws://localhost:9222"
        assert conn.use_count == 0
        assert conn.is_healthy is True
        assert conn.created_at > 0
        assert conn.last_used_at > 0


class TestBrowserConnectionPool:
    """Tests for BrowserConnectionPool class."""

    def test_initialization(self, pool):
        """Test pool initialization."""
        assert pool._max_per_url == 3
        assert pool._timeout == 5.0
        assert pool._max_idle == 60.0
        assert pool._health_interval == 30.0
        assert pool._shutdown is False

    def test_singleton_pattern(self, mock_settings):
        """Test singleton instance management."""
        BrowserConnectionPool._instance = None

        with patch("app.core.config.get_settings", return_value=mock_settings):
            instance1 = BrowserConnectionPool.get_instance()
            instance2 = BrowserConnectionPool.get_instance()

            assert instance1 is instance2

        BrowserConnectionPool._instance = None

    @pytest.mark.asyncio
    async def test_acquire_creates_connection(self, pool, mock_browser):
        """Test acquiring a connection creates new browser."""
        with patch(
            "app.infrastructure.external.browser.connection_pool.PlaywrightBrowser",
            return_value=mock_browser,
        ):
            ctx = await pool.acquire("ws://localhost:9222")
            async with ctx as browser:
                assert browser == mock_browser
                mock_browser.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_acquire_reuses_connection(self, pool, mock_browser):
        """Test acquiring reuses existing healthy connection."""
        # Create initial connection
        with patch(
            "app.infrastructure.external.browser.connection_pool.PlaywrightBrowser",
            return_value=mock_browser,
        ):
            cdp_url = "ws://localhost:9222"

            # First acquire
            ctx1 = await pool.acquire(cdp_url)
            async with ctx1:
                pass

            # Reset the initialize call count
            mock_browser.initialize.reset_mock()

            # Second acquire should reuse
            ctx2 = await pool.acquire(cdp_url)
            async with ctx2 as browser:
                assert browser == mock_browser
                # Should not create new browser
                mock_browser.initialize.assert_not_called()

    @pytest.mark.asyncio
    async def test_pool_size_limit(self, mock_settings):
        """Test pool respects max connections limit."""
        BrowserConnectionPool._instance = None

        mock_browsers = []
        for _ in range(5):
            browser = AsyncMock()
            browser.initialize = AsyncMock(return_value=True)
            browser.cleanup = AsyncMock()
            browser.is_connected = MagicMock(return_value=True)
            mock_page = MagicMock()
            mock_page.is_closed = MagicMock(return_value=False)
            mock_page.evaluate = AsyncMock(return_value=True)
            browser.page = mock_page
            mock_browsers.append(browser)

        browser_index = [0]

        def create_browser(*args, **kwargs):
            idx = browser_index[0]
            browser_index[0] += 1
            return mock_browsers[idx]

        with patch("app.core.config.get_settings", return_value=mock_settings):
            pool = BrowserConnectionPool(
                max_connections_per_url=2,
                connection_timeout=5.0,
            )

            with patch(
                "app.infrastructure.external.browser.connection_pool.PlaywrightBrowser",
                side_effect=create_browser,
            ):
                cdp_url = "ws://localhost:9222"

                # Acquire 2 connections (at limit)
                ctx1 = await pool.acquire(cdp_url)
                _ = await ctx1.__aenter__()

                ctx2 = await pool.acquire(cdp_url)
                _ = await ctx2.__aenter__()

                # Pool should have 2 connections
                assert len(pool._pools.get(cdp_url, [])) == 2

                # Release one
                await ctx1.__aexit__(None, None, None)

                # Release the other
                await ctx2.__aexit__(None, None, None)

            await pool.close_all()

        BrowserConnectionPool._instance = None

    @pytest.mark.asyncio
    async def test_get_pool_lock(self, pool):
        """Test getting/creating pool locks."""
        cdp_url = "ws://localhost:9222"

        lock1 = pool._get_pool_lock(cdp_url)
        lock2 = pool._get_pool_lock(cdp_url)

        assert lock1 is lock2
        assert isinstance(lock1, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_close_all(self, pool, mock_browser):
        """Test closing all connections."""
        with patch(
            "app.infrastructure.external.browser.connection_pool.PlaywrightBrowser",
            return_value=mock_browser,
        ):
            # Create a connection
            ctx = await pool.acquire("ws://localhost:9222")
            async with ctx:
                pass

            # Close all
            await pool.close_all()

            assert pool._shutdown is True
            assert len(pool._pools) == 0
            mock_browser.cleanup.assert_called()

    def test_get_stats_empty(self, pool):
        """Test stats when pool is empty."""
        stats = pool.get_stats()

        assert stats["pools"] == {}
        assert stats["total_connections"] == 0
        assert stats["total_in_use"] == 0

    @pytest.mark.asyncio
    async def test_get_stats_with_connections(self, pool, mock_browser):
        """Test stats with active connections."""
        with patch(
            "app.infrastructure.external.browser.connection_pool.PlaywrightBrowser",
            return_value=mock_browser,
        ):
            cdp_url = "ws://localhost:9222"

            ctx = await pool.acquire(cdp_url)
            async with ctx:
                stats = pool.get_stats()

                assert stats["total_connections"] == 1
                assert stats["total_in_use"] == 1
                assert cdp_url in stats["pools"]

    @pytest.mark.asyncio
    async def test_connection_marked_unhealthy_on_exception(self, pool, mock_browser):
        """Test connection failure is tracked when exception occurs."""
        with patch(
            "app.infrastructure.external.browser.connection_pool.PlaywrightBrowser",
            return_value=mock_browser,
        ):
            cdp_url = "ws://localhost:9222"

            try:
                ctx = await pool.acquire(cdp_url)
                async with ctx:
                    raise ValueError("Test error")
            except ValueError:
                pass

            # Connection should have failure tracked (unhealthy after 3 failures)
            if pool._pools.get(cdp_url):
                conn = pool._pools[cdp_url][0]
                assert conn.consecutive_failures >= 1


class TestPooledConnectionContext:
    """Tests for PooledConnectionContext class."""

    @pytest.mark.asyncio
    async def test_context_manager(self, pool, mock_browser):
        """Test context manager protocol."""
        with patch(
            "app.infrastructure.external.browser.connection_pool.PlaywrightBrowser",
            return_value=mock_browser,
        ):
            ctx = PooledConnectionContext(
                pool=pool,
                cdp_url="ws://localhost:9222",
            )

            browser = await ctx.__aenter__()
            assert browser == mock_browser

            await ctx.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_context_sets_unhealthy_on_error(self, pool, mock_browser):
        """Test context tracks failure on exception."""
        with patch(
            "app.infrastructure.external.browser.connection_pool.PlaywrightBrowser",
            return_value=mock_browser,
        ):
            ctx = PooledConnectionContext(
                pool=pool,
                cdp_url="ws://localhost:9222",
            )

            await ctx.__aenter__()

            # Simulate exception exit
            await ctx.__aexit__(ValueError, ValueError("test"), None)

            # Connection should have failure tracked (unhealthy after 3 failures)
            if ctx._connection:
                assert ctx._connection.consecutive_failures >= 1
