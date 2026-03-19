"""Tests for StuckDetectionMiddleware."""

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareSignal,
    ToolCallInfo,
)
from app.domain.services.agents.middleware_adapters.stuck_detection import (
    StuckDetectionMiddleware,
)
from app.domain.services.agents.stuck_detector import StuckDetector


@pytest.fixture
def mw():
    return StuckDetectionMiddleware(detector=StuckDetector(window_size=3, threshold=2))


@pytest.fixture
def ctx():
    return MiddlewareContext(agent_id="test", session_id="test")


class TestStuckDetectionName:
    def test_name(self, mw):
        assert mw.name == "stuck_detection"


class TestBeforeToolCall:
    @pytest.mark.asyncio
    async def test_tracks_tool_action(self, mw, ctx):
        tool = ToolCallInfo(call_id="1", function_name="file_read", arguments={"path": "/tmp"})
        result = await mw.before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.CONTINUE
        assert len(mw._detector._tool_action_history) > 0


class TestAfterToolCall:
    @pytest.mark.asyncio
    async def test_records_failure(self, mw, ctx):
        tool = ToolCallInfo(call_id="1", function_name="shell_execute", arguments={"command": "fail"})
        result_obj = ToolResult(success=False, message="command failed")
        result = await mw.after_tool_call(ctx, tool, result_obj)
        assert result.signal == MiddlewareSignal.CONTINUE


class TestAfterStep:
    @pytest.mark.asyncio
    async def test_non_stuck_returns_continue(self, mw, ctx):
        result = await mw.after_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_empty_response_returns_continue(self, mw, ctx):
        ctx.metadata["last_response"] = {}
        result = await mw.after_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_with_response_dict(self, mw, ctx):
        ctx.metadata["last_response"] = {"content": "some response text", "tool_calls": []}
        result = await mw.after_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE  # Not stuck on first response
