"""Tests for HallucinationGuardMiddleware."""

import pytest

from app.domain.services.agents.hallucination_detector import ToolHallucinationDetector
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareSignal,
    ToolCallInfo,
)
from app.domain.services.agents.middleware_adapters.hallucination_guard import (
    HallucinationGuardMiddleware,
)


@pytest.fixture
def detector():
    return ToolHallucinationDetector(["file_read", "file_write", "shell_execute"])


@pytest.fixture
def mw(detector):
    return HallucinationGuardMiddleware(detector=detector)


@pytest.fixture
def ctx():
    return MiddlewareContext(agent_id="test", session_id="test")


class TestHallucinationGuardName:
    def test_name(self, mw):
        assert mw.name == "hallucination_guard"


class TestBeforeToolCall:
    @pytest.mark.asyncio
    async def test_valid_tool_returns_continue(self, mw, ctx):
        tool = ToolCallInfo(call_id="1", function_name="file_read", arguments={"path": "/tmp"})
        result = await mw.before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_hallucinated_tool_returns_skip(self, mw, ctx):
        tool = ToolCallInfo(call_id="1", function_name="nonexistent_tool", arguments={})
        result = await mw.before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.SKIP_TOOL
        assert result.message is not None


class TestBeforeStepHallucinationLoop:
    @pytest.mark.asyncio
    async def test_no_loop_returns_continue(self, mw, ctx):
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_force_after_max_hallucinations(self, mw, ctx, detector):
        # Simulate hallucination loop
        for _ in range(5):
            detector.detect("fake_tool_xyz")
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.INJECT

        for _ in range(5):
            detector.detect("fake_tool_abc")
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.INJECT

        for _ in range(5):
            detector.detect("fake_tool_def")
        result = await mw.before_step(ctx)
        assert result.signal == MiddlewareSignal.FORCE


class TestBeforeExecutionReset:
    @pytest.mark.asyncio
    async def test_resets_counter(self, mw, ctx):
        mw._count_this_step = 5
        await mw.before_execution(ctx)
        assert mw._count_this_step == 0
