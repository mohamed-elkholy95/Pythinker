"""Tests for browser connection retry progress events."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.exceptions.browser import BrowserErrorContext
from app.infrastructure.external.browser.connection_pool import BrowserConnectionPool


class TestBrowserRetryProgress:
    """Test browser connection retry progress event emission."""

    @pytest.fixture
    async def pool(self):
        """Create a browser connection pool for testing."""
        pool = BrowserConnectionPool(
            max_connections_per_url=2,
            connection_timeout=10.0,
            max_idle_time=60.0,
            health_check_interval=30.0,
        )
        yield pool
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_retry_progress_callback_called_on_failure(self, pool):
        """Test that progress callback is called on retry attempts."""
        progress_messages = []

        async def progress_callback(message: str) -> None:
            progress_messages.append(message)

        error_context = BrowserErrorContext(
            cdp_url="http://localhost:9222",
            session_id="test-session",
            sandbox_id="test-sandbox",
            operation="test",
        )

        # Mock PlaywrightBrowser to fail initialization
        with patch(
            "app.infrastructure.external.browser.connection_pool.PlaywrightBrowser"
        ) as mock_browser_class:
            mock_browser = AsyncMock()
            mock_browser.initialize = AsyncMock(return_value=False)
            mock_browser_class.return_value = mock_browser

            # Attempt to create connection with retries
            with pytest.raises(Exception):
                await pool._create_connection_with_retry(
                    cdp_url="http://localhost:9222",
                    block_resources=False,
                    randomize_fingerprint=True,
                    error_context=error_context,
                    max_retries=3,
                    progress_callback=progress_callback,
                )

            # Verify progress callback was called for retry attempts
            # First attempt doesn't trigger callback, only retries do
            assert len(progress_messages) == 2  # Attempts 2 and 3
            assert "Retrying browser connection (attempt 2/3)" in progress_messages[0]
            assert "Retrying browser connection (attempt 3/3)" in progress_messages[1]

    @pytest.mark.asyncio
    async def test_retry_progress_callback_not_called_on_success(self, pool):
        """Test that progress callback is not called when connection succeeds on first try."""
        progress_messages = []

        async def progress_callback(message: str) -> None:
            progress_messages.append(message)

        error_context = BrowserErrorContext(
            cdp_url="http://localhost:9222",
            session_id="test-session",
            sandbox_id="test-sandbox",
            operation="test",
        )

        # Mock PlaywrightBrowser to succeed immediately
        with patch(
            "app.infrastructure.external.browser.connection_pool.PlaywrightBrowser"
        ) as mock_browser_class:
            mock_browser = AsyncMock()
            mock_browser.initialize = AsyncMock(return_value=True)
            mock_browser_class.return_value = mock_browser

            # Create connection successfully
            conn = await pool._create_connection_with_retry(
                cdp_url="http://localhost:9222",
                block_resources=False,
                randomize_fingerprint=True,
                error_context=error_context,
                max_retries=3,
                progress_callback=progress_callback,
            )

            # Verify progress callback was never called (no retries needed)
            assert len(progress_messages) == 0
            assert conn is not None

    @pytest.mark.asyncio
    async def test_retry_progress_callback_exception_doesnt_break_retry(self, pool):
        """Test that exceptions in progress callback don't break retry logic."""
        callback_calls = []

        async def failing_callback(message: str) -> None:
            callback_calls.append(message)
            raise RuntimeError("Callback failed")

        error_context = BrowserErrorContext(
            cdp_url="http://localhost:9222",
            session_id="test-session",
            sandbox_id="test-sandbox",
            operation="test",
        )

        # Mock PlaywrightBrowser to fail first attempt, succeed on second
        call_count = 0

        async def init_mock(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count > 1  # Fail first, succeed second

        with patch(
            "app.infrastructure.external.browser.connection_pool.PlaywrightBrowser"
        ) as mock_browser_class:
            mock_browser = AsyncMock()
            mock_browser.initialize = AsyncMock(side_effect=init_mock)
            mock_browser_class.return_value = mock_browser

            # Should succeed despite callback failures
            conn = await pool._create_connection_with_retry(
                cdp_url="http://localhost:9222",
                block_resources=False,
                randomize_fingerprint=True,
                error_context=error_context,
                max_retries=3,
                progress_callback=failing_callback,
            )

            # Verify callback was called (even though it raised)
            assert len(callback_calls) == 1
            assert "Retrying browser connection (attempt 2/3)" in callback_calls[0]
            # Verify connection still succeeded
            assert conn is not None

    @pytest.mark.asyncio
    async def test_retry_progress_callback_with_timeout_errors(self, pool):
        """Test that progress callback is called for timeout errors."""
        progress_messages = []

        async def progress_callback(message: str) -> None:
            progress_messages.append(message)

        error_context = BrowserErrorContext(
            cdp_url="http://localhost:9222",
            session_id="test-session",
            sandbox_id="test-sandbox",
            operation="test",
        )

        # Mock PlaywrightBrowser to raise TimeoutError
        with patch(
            "app.infrastructure.external.browser.connection_pool.PlaywrightBrowser"
        ) as mock_browser_class:
            mock_browser = AsyncMock()
            mock_browser.initialize = AsyncMock(side_effect=TimeoutError("Connection timeout"))
            mock_browser_class.return_value = mock_browser

            # Attempt to create connection with retries
            with pytest.raises(Exception):
                await pool._create_connection_with_retry(
                    cdp_url="http://localhost:9222",
                    block_resources=False,
                    randomize_fingerprint=True,
                    error_context=error_context,
                    max_retries=3,
                    progress_callback=progress_callback,
                )

            # Verify progress callback was called for all retry attempts
            assert len(progress_messages) == 2  # Attempts 2 and 3
            assert all("Retrying browser connection" in msg for msg in progress_messages)


class TestDockerSandboxProgressCallback:
    """Test DockerSandbox browser progress callback integration."""

    @pytest.mark.asyncio
    async def test_set_browser_progress_callback(self):
        """Test setting browser progress callback on DockerSandbox."""
        from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

        sandbox = DockerSandbox(ip="127.0.0.1")
        messages = []

        async def callback(msg: str) -> None:
            messages.append(msg)

        sandbox.set_browser_progress_callback(callback)
        assert sandbox._browser_progress_callback is not None

        # Test callback is actually callable
        await sandbox._browser_progress_callback("Test message")
        assert messages == ["Test message"]

    @pytest.mark.asyncio
    async def test_clear_browser_progress_callback(self):
        """Test clearing browser progress callback."""
        from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

        sandbox = DockerSandbox(ip="127.0.0.1")

        async def callback(msg: str) -> None:
            pass

        sandbox.set_browser_progress_callback(callback)
        assert sandbox._browser_progress_callback is not None

        sandbox.set_browser_progress_callback(None)
        assert sandbox._browser_progress_callback is None
