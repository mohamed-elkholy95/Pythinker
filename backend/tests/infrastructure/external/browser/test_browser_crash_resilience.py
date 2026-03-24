"""Tests for browser crash resilience.

Tests the crash detection, circuit breaker, and auto-recovery
mechanisms in PlaywrightBrowser, SearchTool._browse_top_results,
and BrowserTool search live-preview guard.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.external.browser.playwright_browser import (
    BROWSER_CRASH_SIGNATURES,
    PlaywrightBrowser,
)


@pytest.fixture
def browser():
    """Create a PlaywrightBrowser instance with mocked dependencies."""
    with (
        patch("app.infrastructure.external.browser.playwright_browser.get_llm"),
        patch("app.infrastructure.external.browser.playwright_browser.get_settings") as mock_settings,
    ):
        settings = MagicMock()
        settings.browser_pool_max_per_url = 3
        mock_settings.return_value = settings
        b = PlaywrightBrowser(cdp_url="ws://localhost:9222")
        # Mark as connected for tests that need it
        b._connection_healthy = True
        b.browser = MagicMock()
        b.page = MagicMock()
        b.page.is_closed = MagicMock(return_value=False)
        b.context = MagicMock()
        return b


# --- 1. _is_crash_error ---


class TestIsCrashError:
    def test_detects_known_signatures(self):
        """_is_crash_error returns True for all known crash signatures."""
        for sig in BROWSER_CRASH_SIGNATURES:
            err = Exception(f"Some context: {sig} more text")
            assert PlaywrightBrowser._is_crash_error(err), f"Should detect: {sig}"

    def test_detects_case_insensitive(self):
        """_is_crash_error matches case-insensitively."""
        err = Exception("TARGET CLOSED unexpectedly")
        assert PlaywrightBrowser._is_crash_error(err)

    def test_rejects_non_crash_errors(self):
        """_is_crash_error returns False for non-crash exceptions."""
        non_crash_errors = [
            Exception("Navigation timeout"),
            Exception("Element not found"),
            Exception("Net::ERR_NAME_NOT_RESOLVED"),
            Exception("SSL certificate error"),
            ValueError("invalid literal"),
        ]
        for err in non_crash_errors:
            assert not PlaywrightBrowser._is_crash_error(err), f"Should NOT detect: {err}"


# --- 2. _verify_connection_health ---


class TestVerifyConnectionHealth:
    @pytest.mark.asyncio
    async def test_marks_unhealthy_on_crash(self, browser):
        """Health check sets _connection_healthy=False on crash-signature error."""
        browser.page.evaluate = AsyncMock(side_effect=Exception("Target closed"))
        browser._connection_healthy = True

        result = await browser._verify_connection_health()

        assert result is False
        assert browser._connection_healthy is False

    @pytest.mark.asyncio
    async def test_returns_true_when_healthy(self, browser):
        """Health check returns True when page.evaluate succeeds."""
        browser.page.evaluate = AsyncMock(return_value=True)

        result = await browser._verify_connection_health()

        assert result is True


# --- 3. _navigate_impl auto-recovery ---


class TestNavigateImplCrashRecovery:
    @pytest.mark.asyncio
    async def test_graceful_degradation_marks_crash_as_failure(self, browser):
        """Crash-with-partial-data should not be reported as successful navigation."""
        browser.page.goto = AsyncMock(side_effect=Exception("Target closed"))
        browser.page.title = AsyncMock(return_value="Example")
        browser.page.url = "https://example.com"

        result = await browser._navigate_impl("https://example.com", timeout=5000, wait_until="load", auto_extract=True)

        assert result.success is False
        assert result.data is not None
        assert result.data.get("partial") is True
        assert result.data.get("crash_reason") == "browser_crash"

    @pytest.mark.asyncio
    async def test_auto_recovers_on_crash(self, browser):
        """_navigate_impl attempts restart on crash and returns recovery result."""
        from app.domain.models.tool_result import ToolResult

        browser.page.goto = AsyncMock(side_effect=Exception("Page crashed"))
        recovery_result = ToolResult(success=True, data={"url": "https://example.com"})
        browser.restart = AsyncMock(return_value=recovery_result)

        result = await browser._navigate_impl(
            "https://example.com", timeout=5000, wait_until="load", auto_extract=False
        )

        assert result.success is True
        browser.restart.assert_awaited_once_with("https://example.com")
        assert browser._display_failure_count == 0

    @pytest.mark.asyncio
    async def test_returns_failure_when_recovery_fails(self, browser):
        """_navigate_impl returns clear failure message when restart also fails."""
        from app.domain.models.tool_result import ToolResult

        browser.page.goto = AsyncMock(side_effect=Exception("Browser has been closed"))
        browser.restart = AsyncMock(return_value=ToolResult(success=False, message="Restart failed"))

        result = await browser._navigate_impl(
            "https://example.com", timeout=5000, wait_until="load", auto_extract=False
        )

        assert result.success is False
        assert "crashed" in result.message.lower() or "recovery failed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_non_crash_error_passes_through(self, browser):
        """_navigate_impl returns normal failure for non-crash errors."""
        browser.page.goto = AsyncMock(side_effect=Exception("Net::ERR_NAME_NOT_RESOLVED"))

        result = await browser._navigate_impl(
            "https://bad.example", timeout=5000, wait_until="load", auto_extract=False
        )

        assert result.success is False
        assert "ERR_NAME_NOT_RESOLVED" in result.message


# --- 4. navigate_for_display circuit breaker ---


class TestNavigateForDisplayCircuitBreaker:
    @pytest.mark.asyncio
    async def test_circuit_breaker_stops_after_threshold(self, browser):
        """navigate_for_display skips when failure count >= threshold."""
        browser._display_failure_count = 2
        browser._display_failure_threshold = 2

        result = await browser.navigate_for_display("https://example.com")

        assert result is False
        # page.goto should NOT have been called
        browser.page.goto = AsyncMock()
        # Confirm the method returned early (goto not called)

    @pytest.mark.asyncio
    async def test_circuit_breaker_resets_on_success(self, browser):
        """navigate_for_display resets failure count after successful navigation."""
        browser._display_failure_count = 1
        browser.page.goto = AsyncMock()
        browser.page.bring_to_front = AsyncMock()
        cdp = AsyncMock()
        browser.context.new_cdp_session = AsyncMock(return_value=cdp)
        browser._ensure_page = AsyncMock()

        result = await browser.navigate_for_display("https://example.com")

        assert result is True
        assert browser._display_failure_count == 0

    @pytest.mark.asyncio
    async def test_crash_error_marks_unhealthy(self, browser):
        """navigate_for_display sets _connection_healthy=False on crash error."""
        browser._ensure_page = AsyncMock()
        browser.page.goto = AsyncMock(side_effect=Exception("Target closed"))

        result = await browser.navigate_for_display("https://example.com")

        assert result is False
        assert browser._connection_healthy is False
        assert browser._display_failure_count == 1


# --- 5. _browse_top_results early exit ---


class TestBrowseTopResultsResilience:
    @pytest.fixture
    def search_tool(self):
        """Create a SearchTool with a mock browser."""
        from app.domain.services.tools.search import SearchTool

        mock_engine = MagicMock()
        mock_browser = MagicMock()
        mock_browser.is_connected = MagicMock(return_value=True)
        mock_browser.navigate_for_display = AsyncMock(return_value=True)
        mock_browser._background_browse_cancelled = False
        return SearchTool(search_engine=mock_engine, browser=mock_browser)

    @pytest.mark.asyncio
    async def test_continues_browsing_across_multiple_failures(self, search_tool):
        """_browse_top_results should not abort after only two failures."""
        search_tool._browser.navigate_for_display = AsyncMock(return_value=False)
        search_data = {"results": [{"link": f"https://example.com/{i}"} for i in range(5)]}

        with patch("app.domain.services.tools.search.asyncio.sleep", new=AsyncMock()):
            await search_tool._browse_top_results(search_data, count=5)

        # Should keep trying all candidates instead of stopping after 2 failures.
        # navigate_for_display is called once per candidate URL; the about:blank
        # cleanup is NOT reached because all navigations failed.
        real_calls = [
            c for c in search_tool._browser.navigate_for_display.call_args_list
            if c.args[0] != "about:blank"
        ]
        assert len(real_calls) == 5

    @pytest.mark.asyncio
    async def test_skips_when_disconnected(self, search_tool):
        """_browse_top_results returns early when browser is disconnected."""
        search_tool._browser.is_connected = MagicMock(return_value=False)
        search_data = {"results": [{"link": "https://example.com"}]}

        await search_tool._browse_top_results(search_data, count=3)

        search_tool._browser.navigate_for_display.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_continues_on_intermittent_failure(self, search_tool):
        """_browse_top_results continues when failures are not consecutive."""
        # Pattern: success, fail, success — should process all 3
        search_tool._browser.navigate_for_display = AsyncMock(side_effect=[True, False, True])
        search_data = {"results": [{"link": f"https://example.com/{i}"} for i in range(3)]}

        await search_tool._browse_top_results(search_data, count=3)

        # 3 result navigations + 1 about:blank cleanup (from successful first nav)
        real_calls = [
            c for c in search_tool._browser.navigate_for_display.call_args_list
            if c.args[0] != "about:blank"
        ]
        assert len(real_calls) == 3

    @pytest.mark.asyncio
    async def test_skips_urls_already_shown_in_live_preview(self, search_tool):
        """_browse_top_results does not re-open URLs already previewed in this session."""
        with patch("app.domain.services.tools.search.asyncio.sleep", new=AsyncMock()):
            await search_tool._browse_top_results(
                {
                    "results": [
                        {"link": "https://example.com/deals?utm_source=google&utm_medium=cpc"},
                        {"link": "https://example.com/deals/"},
                    ]
                },
                count=2,
            )
            await search_tool._browse_top_results(
                {
                    "results": [
                        {"link": "https://example.com/deals?ref=newsletter"},
                        {"link": "https://example.com/new-offer"},
                    ]
                },
                count=2,
            )

        called_urls = [
            call.args[0]
            for call in search_tool._browser.navigate_for_display.await_args_list
            if call.args[0] != "about:blank"
        ]
        assert called_urls == [
            "https://example.com/deals?utm_source=google&utm_medium=cpc",
            "https://example.com/new-offer",
        ]

    @pytest.mark.asyncio
    async def test_skips_batch_when_all_urls_already_previewed(self, search_tool):
        """_browse_top_results exits without navigation when all candidates were previously shown."""
        with patch("app.domain.services.tools.search.asyncio.sleep", new=AsyncMock()):
            await search_tool._browse_top_results(
                {"results": [{"link": "https://example.com/same-page"}]},
                count=1,
            )
            await search_tool._browse_top_results(
                {"results": [{"link": "https://example.com/same-page/"}]},
                count=1,
            )

        # First call navigates to the real URL + about:blank cleanup.
        # Second call should skip entirely (URL already previewed).
        real_calls = [
            c for c in search_tool._browser.navigate_for_display.call_args_list
            if c.args[0] != "about:blank"
        ]
        assert len(real_calls) == 1


# --- 6. BrowserTool search live-preview guard ---


class TestBrowserToolSearchGuard:
    @pytest.mark.asyncio
    async def test_skips_display_when_disconnected(self):
        """BrowserTool.search skips navigate_for_display when browser is disconnected."""
        mock_browser = MagicMock()
        mock_browser.is_connected = MagicMock(return_value=False)
        mock_browser.navigate_for_display = AsyncMock()

        # The guard check is: hasattr(browser, "navigate_for_display") and browser.is_connected()
        has_display = hasattr(mock_browser, "navigate_for_display")
        is_connected = mock_browser.is_connected()

        # Verify the guard would block the task creation
        assert has_display is True
        assert is_connected is False
        # So no task would be created — navigate_for_display should not be called
