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
        assert result.metadata["pressure_level"] == "CRITICAL"
        assert "90%" in result.message

    @pytest.mark.asyncio
    async def test_critical_sets_metadata_sent_flag(self, mw, ctx):
        ctx.elapsed_seconds = 95.0
        await mw.before_step(ctx)
        assert ctx.metadata.get("wall_clock_critical_sent") is True

    @pytest.mark.asyncio
    async def test_critical_always_returns_force(self, mw, ctx):
        """CRITICAL always returns FORCE even on repeated calls."""
        ctx.elapsed_seconds = 95.0
        ctx.metadata["wall_clock_critical_sent"] = True
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.FORCE

    @pytest.mark.asyncio
    async def test_urgent_returns_inject(self, mw, ctx):
        ctx.elapsed_seconds = 80.0
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.INJECT
        assert result.metadata["pressure_level"] == "URGENT"
        assert "75%" in result.message

    @pytest.mark.asyncio
    async def test_urgent_only_fires_once(self, mw, ctx):
        ctx.elapsed_seconds = 80.0
        await mw.before_step(ctx)
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_advisory_injects_message(self, mw, ctx):
        ctx.elapsed_seconds = 55.0
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE
        assert len(ctx.injected_messages) == 1
        assert "50%" in ctx.injected_messages[0]["content"]

    @pytest.mark.asyncio
    async def test_advisory_only_fires_once(self, mw, ctx):
        ctx.elapsed_seconds = 55.0
        await mw.before_step(ctx)
        ctx.injected_messages.clear()
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE
        assert len(ctx.injected_messages) == 0

    @pytest.mark.asyncio
    async def test_zero_budget_returns_continue(self, mw, ctx):
        ctx.wall_clock_budget = 0.0
        ctx.elapsed_seconds = 999.0
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE


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
