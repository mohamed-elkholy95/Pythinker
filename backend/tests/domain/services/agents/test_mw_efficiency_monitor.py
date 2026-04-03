"""Tests for EfficiencyMonitorMiddleware."""

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareSignal,
    ToolCallInfo,
)
from app.domain.services.agents.middleware_adapters.efficiency_monitor import (
    EfficiencyMonitorMiddleware,
)


@pytest.fixture
def mw():
    return EfficiencyMonitorMiddleware()


@pytest.fixture
def ctx():
    return MiddlewareContext(agent_id="test", session_id="test")


class TestEfficiencyMonitorName:
    def test_name(self, mw):
        assert mw.name == "efficiency_monitor"


class TestAfterToolCall:
    @pytest.mark.asyncio
    async def test_records_tool(self, mw, ctx):
        tool = ToolCallInfo(call_id="1", function_name="file_read", arguments={})
        result_obj = ToolResult(success=True, message="ok")
        result = await mw.after_tool_call(ctx, tool, result_obj)
        assert result.signal == MiddlewareSignal.CONTINUE


class TestBeforeStep:
    @pytest.mark.asyncio
    async def test_balanced_returns_continue(self, mw, ctx):
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_nudge_after_consecutive_reads(self, mw, ctx):
        """After 5+ consecutive reads, should nudge."""
        tool = ToolCallInfo(call_id="1", function_name="file_read", arguments={})
        result_obj = ToolResult(success=True, message="ok")
        for _ in range(6):
            await mw.after_tool_call(ctx, tool, result_obj)

        result = await mw.before_step(ctx)
        # Should be either INJECT (nudge) or FORCE (hard stop) depending on threshold
        assert result.signal in (MiddlewareSignal.INJECT, MiddlewareSignal.FORCE)
