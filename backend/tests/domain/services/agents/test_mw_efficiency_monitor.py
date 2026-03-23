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

    @pytest.mark.asyncio
    async def test_duplicate_search_query_is_skipped(self, mw, ctx):
        first = ToolCallInfo(call_id="1", function_name="search", arguments={"query": "python agents"})
        result_obj = ToolResult(success=True, message="ok")

        first_result = await mw.before_tool_call(ctx, first)
        assert first_result.signal == MiddlewareSignal.CONTINUE
        await mw.after_tool_call(ctx, first, result_obj)

        duplicate_result = await mw.before_tool_call(ctx, first)
        assert duplicate_result.signal == MiddlewareSignal.SKIP_TOOL
        assert "Already used this search" in (duplicate_result.message or "")


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

    @pytest.mark.asyncio
    async def test_repeated_duplicate_searches_force_progress(self, mw, ctx):
        """FORCE fires after 3 consecutive duplicate skips and step_iteration_count > 0."""
        tool = ToolCallInfo(call_id="1", function_name="search", arguments={"query": "python agents"})
        result_obj = ToolResult(success=True, message="ok")

        assert (await mw.before_tool_call(ctx, tool)).signal == MiddlewareSignal.CONTINUE
        await mw.after_tool_call(ctx, tool, result_obj)

        # 3 consecutive skips needed (threshold raised from 2 to 3)
        assert (await mw.before_tool_call(ctx, tool)).signal == MiddlewareSignal.SKIP_TOOL
        assert (await mw.before_tool_call(ctx, tool)).signal == MiddlewareSignal.SKIP_TOOL
        assert (await mw.before_tool_call(ctx, tool)).signal == MiddlewareSignal.SKIP_TOOL

        # FORCE only fires when step_iteration_count > 0 (not on first iteration)
        ctx.step_iteration_count = 0
        result = await mw.before_step(ctx)
        # On first iteration: duplicate FORCE suppressed; may get INJECT from
        # efficiency monitor (soft nudge) or CONTINUE — but never FORCE.
        assert result.signal != MiddlewareSignal.FORCE

        ctx.step_iteration_count = 1
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.FORCE
        assert "duplicate" in (result.message or "").lower()
