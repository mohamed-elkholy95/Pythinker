"""Tests for browser crash detection and recovery hardening (Phase 1).

Tests circuit breaker, quick health checks, crash recording, and pool cleanup.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import Error as PlaywrightError

from app.core.config import Settings
from app.domain.exceptions.browser import BrowserCrashedError
from app.infrastructure.external.browser.connection_pool import (
    BrowserConnectionPool,
    PooledConnection,
)
from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    @pytest.fixture
    def browser(self):
        """Create a browser instance for testing."""
        return PlaywrightBrowser()

    def test_circuit_breaker_initial_state(self, browser):
        """Circuit breaker should be closed initially."""
        assert browser._check_circuit_breaker() is True
        assert len(browser._crash_history) == 0

    def test_record_crash(self, browser):
        """Recording a crash should add to history."""
        browser._record_crash()
        assert len(browser._crash_history) == 1

    def test_circuit_breaker_opens_after_threshold(self, browser):
        """Circuit breaker should open after crash threshold."""
        # Record crashes up to threshold
        for _ in range(browser._crash_threshold):
            browser._record_crash()

        # Circuit should be open
        assert browser._check_circuit_breaker() is False

    def test_circuit_breaker_cleans_old_crashes(self, browser):
        """Old crashes outside window should be removed."""
        # Record old crash (simulate by modifying timestamp)
        old_time = time.time() - browser._crash_window_seconds - 10
        browser._crash_history = [old_time]

        # Check circuit - should clean old crash
        assert browser._check_circuit_breaker() is True
        assert len(browser._crash_history) == 0

    def test_circuit_breaker_cooldown(self, browser):
        """Circuit breaker should respect cooldown period."""
        # Open circuit
        for _ in range(browser._crash_threshold):
            browser._record_crash()

        # Verify circuit is open
        assert browser._check_circuit_breaker() is False

        # Verify circuit_open_until is set
        assert browser._circuit_open_until > time.time()

    def test_circuit_breaker_disabled(self):
        """Circuit breaker can be disabled via settings."""
        with patch("app.infrastructure.external.browser.playwright_browser.get_settings") as mock_settings:
            settings = Settings()
            settings.browser_crash_circuit_breaker_enabled = False
            mock_settings.return_value = settings

            browser = PlaywrightBrowser()
            assert browser._circuit_breaker_enabled is False

            # Record many crashes
            for _ in range(10):
                browser._record_crash()

            # Circuit should still be closed (disabled)
            assert browser._check_circuit_breaker() is True


class TestQuickHealthCheck:
    """Test quick health check functionality."""

    @pytest.fixture
    def browser(self):
        """Create a browser with mocked page."""
        browser = PlaywrightBrowser()
        browser.page = MagicMock()
        browser.page.is_closed = MagicMock(return_value=False)
        browser._connection_healthy = True
        return browser

    @pytest.mark.asyncio
    async def test_quick_health_check_healthy(self, browser):
        """Health check should pass for healthy browser."""
        browser.page.evaluate = AsyncMock(return_value=True)

        result = await browser._quick_health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_quick_health_check_no_page(self, browser):
        """Health check should fail when page is None."""
        browser.page = None

        result = await browser._quick_health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_quick_health_check_closed_page(self, browser):
        """Health check should fail when page is closed."""
        browser.page.is_closed = MagicMock(return_value=True)

        result = await browser._quick_health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_quick_health_check_timeout(self, browser):
        """Health check should fail on timeout."""

        async def slow_evaluate(*args, **kwargs):
            await asyncio.sleep(10)  # Longer than timeout
            return True

        browser.page.evaluate = slow_evaluate

        result = await browser._quick_health_check()
        assert result is False
        assert browser._connection_healthy is False

    @pytest.mark.asyncio
    async def test_quick_health_check_crash_detected(self, browser):
        """Health check should detect and record crashes."""
        browser.page.evaluate = AsyncMock(side_effect=PlaywrightError("Target crashed"))

        result = await browser._quick_health_check()
        assert result is False
        assert browser._connection_healthy is False
        assert len(browser._crash_history) == 1

    @pytest.mark.asyncio
    async def test_quick_health_check_disabled(self):
        """Health check can be disabled via settings."""
        with patch("app.infrastructure.external.browser.playwright_browser.get_settings") as mock_settings:
            settings = Settings()
            settings.browser_quick_health_check_enabled = False
            mock_settings.return_value = settings

            browser = PlaywrightBrowser()
            browser._connection_healthy = True

            # Should return connection_healthy without checking
            result = await browser._quick_health_check()
            assert result is True


class TestNavigateWithCircuitBreaker:
    """Test navigation with circuit breaker protection."""

    @pytest.fixture
    def browser(self):
        """Create a browser for navigation testing."""
        browser = PlaywrightBrowser()
        browser.page = MagicMock()
        browser.context = MagicMock()
        browser.browser = MagicMock()
        browser._connection_healthy = True
        return browser

    @pytest.mark.asyncio
    async def test_navigate_fails_when_circuit_open(self, browser):
        """Navigate should fail immediately when circuit is open."""
        # Open circuit
        for _ in range(browser._crash_threshold):
            browser._record_crash()

        # Attempt navigation
        with pytest.raises(BrowserCrashedError) as exc_info:
            await browser._navigate_impl("https://example.com")

        assert "circuit_breaker_open" in str(exc_info.value.context.additional_info)

    @pytest.mark.asyncio
    async def test_navigate_checks_health_before_operation(self, browser):
        """Navigate should check health before attempting navigation."""
        browser.page.evaluate = AsyncMock(return_value=True)  # Healthy
        browser.page.goto = AsyncMock(return_value=MagicMock(status=200))
        browser.page.url = "https://example.com"
        browser.page.title = AsyncMock(return_value="Example")
        browser._extract_interactive_elements = AsyncMock(return_value=[])
        browser._extract_page_content = AsyncMock(return_value="content")

        result = await browser._navigate_impl("https://example.com", auto_extract=False)

        # Health check should have been called
        assert browser.page.evaluate.called


class TestConnectionPoolCrashCleanup:
    """Test connection pool cleanup on crash detection."""

    @pytest.fixture
    def pool(self):
        """Create a connection pool for testing."""
        return BrowserConnectionPool(max_connections_per_url=2)

    @pytest.fixture
    def mock_connection(self):
        """Create a mock pooled connection."""
        browser = MagicMock()
        browser.is_connected = MagicMock(return_value=True)
        browser.page = MagicMock()
        browser.page.is_closed = MagicMock(return_value=False)
        browser.page.evaluate = AsyncMock(return_value=True)
        browser._is_crash_error = MagicMock(return_value=False)
        browser._record_crash = MagicMock()

        conn = PooledConnection(
            browser=browser,
            cdp_url="ws://localhost:9222",
        )
        return conn

    @pytest.mark.asyncio
    async def test_health_check_detects_crash(self, pool, mock_connection):
        """Pool health check should detect crashes."""
        # Simulate crash error
        crash_error = PlaywrightError("Browser crashed")
        mock_connection.browser.page.evaluate = AsyncMock(side_effect=crash_error)
        mock_connection.browser._is_crash_error = MagicMock(return_value=True)

        result = await pool._verify_connection_health(mock_connection)

        assert result is False
        assert mock_connection.is_healthy is False
        assert mock_connection.consecutive_failures == 99  # Force removal
        mock_connection.browser._record_crash.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_handles_non_crash_errors(self, pool, mock_connection):
        """Pool health check should handle non-crash errors gracefully."""
        # Simulate non-crash error
        error = Exception("Connection timeout")
        mock_connection.browser.page.evaluate = AsyncMock(side_effect=error)
        mock_connection.browser._is_crash_error = MagicMock(return_value=False)

        result = await pool._verify_connection_health(mock_connection)

        assert result is False
        assert mock_connection.is_healthy is False
        # Should NOT record crash or force removal for non-crash errors
        mock_connection.browser._record_crash.assert_not_called()


class TestCrashRecoveryLogging:
    """Test that crash recovery emits proper log messages."""

    @pytest.mark.asyncio
    async def test_recovery_logs_progress(self, caplog):
        """Initialize should log recovery progress during retries."""
        browser = PlaywrightBrowser()

        # Mock to fail first 2 attempts, succeed on 3rd
        attempt_count = [0]

        async def mock_connect_over_cdp(*args, **kwargs):
            attempt_count[0] += 1
            if attempt_count[0] < 3:
                raise PlaywrightError("Target crashed")
            # Third attempt succeeds
            mock_browser = MagicMock()
            mock_browser.contexts = []
            mock_browser.on = MagicMock()
            return mock_browser

        with patch("app.infrastructure.external.browser.playwright_browser.async_playwright") as mock_pw:
            mock_pw_instance = AsyncMock()
            mock_pw_instance.start = AsyncMock(return_value=mock_pw_instance)
            mock_pw_instance.chromium.connect_over_cdp = mock_connect_over_cdp
            mock_pw.return_value = mock_pw_instance

            # This will fail because contexts is empty, but we're testing logging
            await browser.initialize()

        # Check for recovery log messages
        recovery_logs = [r for r in caplog.records if "Browser crashed, recovering" in r.message]
        assert len(recovery_logs) >= 1  # Should have logged recovery attempts
