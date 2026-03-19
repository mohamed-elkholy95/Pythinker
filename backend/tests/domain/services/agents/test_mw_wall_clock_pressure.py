"""Tests for WallClockPressureMiddleware."""

import pytest

from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareSignal,
    ToolCallInfo,
)
from app.domain.services.agents.middleware_adapters.wall_clock_pressure import (
    WallClockPressureMiddleware,
)


@pytest.fixture
def mw():
    return WallClockPressureMiddleware()


@pytest.fixture
def ctx():
    return MiddlewareContext(agent_id="test", session_id="test", wall_clock_budget=100.0)


class TestWallClockName:
    def test_name(self, mw):
        assert mw.name == "wall_clock_pressure"


class TestBeforeStep:
    @pytest.mark.asyncio
    async def test_no_pressure_returns_continue(self, mw, ctx):
        ctx.elapsed_seconds = 10.0
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_critical_returns_force(self, mw, ctx):
        ctx.elapsed_seconds = 95.0
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.FORCE


class TestBeforeToolCall:
    @pytest.mark.asyncio
    async def test_critical_blocks_non_write_tools(self, mw, ctx):
        ctx.elapsed_seconds = 95.0
        tool = ToolCallInfo(call_id="1", function_name="file_read", arguments={})
        result = await mw.before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.SKIP_TOOL

    @pytest.mark.asyncio
    async def test_critical_allows_write_tools(self, mw, ctx):
        ctx.elapsed_seconds = 95.0
        tool = ToolCallInfo(call_id="1", function_name="file_write", arguments={})
        result = await mw.before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_no_pressure_allows_all(self, mw, ctx):
        ctx.elapsed_seconds = 10.0
        tool = ToolCallInfo(call_id="1", function_name="file_read", arguments={})
        result = await mw.before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.CONTINUE
