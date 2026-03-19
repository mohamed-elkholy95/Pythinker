"""Tests for UrlFailureGuardMiddleware."""

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareSignal,
    ToolCallInfo,
)
from app.domain.services.agents.middleware_adapters.url_failure_guard import (
    UrlFailureGuardMiddleware,
)
from app.domain.services.agents.url_failure_guard import UrlFailureGuard


@pytest.fixture
def mw_no_guard():
    return UrlFailureGuardMiddleware(guard=None)


@pytest.fixture
def mw_with_guard():
    return UrlFailureGuardMiddleware(guard=UrlFailureGuard())


@pytest.fixture
def ctx():
    return MiddlewareContext(agent_id="test", session_id="test")


class TestUrlFailureGuardName:
    def test_name(self, mw_no_guard):
        assert mw_no_guard.name == "url_failure_guard"


class TestBeforeToolCallNoGuard:
    @pytest.mark.asyncio
    async def test_no_guard_returns_continue(self, mw_no_guard, ctx):
        tool = ToolCallInfo(call_id="1", function_name="browser_navigate", arguments={"url": "https://example.com"})
        result = await mw_no_guard.before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_non_url_args_returns_continue(self, mw_with_guard, ctx):
        tool = ToolCallInfo(call_id="1", function_name="file_read", arguments={"path": "/tmp/file.txt"})
        result = await mw_with_guard.before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.CONTINUE


class TestBeforeToolCallWithGuard:
    @pytest.mark.asyncio
    async def test_fresh_url_is_allowed(self, mw_with_guard, ctx):
        tool = ToolCallInfo(call_id="1", function_name="browser_navigate", arguments={"url": "https://example.com"})
        result = await mw_with_guard.before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_blocked_url_returns_skip_tool(self, mw_with_guard, ctx):
        """After 3 failures, guard blocks the URL."""
        guard = mw_with_guard._guard
        url = "https://example.com/failing-page"
        guard.record_failure(url, "HTTP 404", "browser_navigate")
        guard.record_failure(url, "HTTP 404", "browser_navigate")
        guard.record_failure(url, "HTTP 404", "browser_navigate")

        tool = ToolCallInfo(call_id="1", function_name="browser_navigate", arguments={"url": url})
        result = await mw_with_guard.before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.SKIP_TOOL

    @pytest.mark.asyncio
    async def test_after_tool_call_records_failure_on_error(self, mw_with_guard, ctx):
        tool = ToolCallInfo(
            call_id="1", function_name="browser_navigate", arguments={"url": "https://example.com/page"}
        )
        result_obj = ToolResult(success=False, message="HTTP 404 Not Found")
        result = await mw_with_guard.after_tool_call(ctx, tool, result_obj)
        assert result.signal == MiddlewareSignal.CONTINUE
        # Verify the failure was recorded
        metrics = mw_with_guard._guard.get_metrics()
        assert metrics["total_failures"] == 1
