"""Tests for MiddlewarePipeline."""

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
    ToolCallInfo,
)
from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline


class AlwaysForceMiddleware(BaseMiddleware):
    @property
    def name(self) -> str:
        return "always_force"

    async def before_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult(signal=MiddlewareSignal.FORCE, message="forced")

    async def before_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo) -> MiddlewareResult:
        return MiddlewareResult(signal=MiddlewareSignal.SKIP_TOOL, message="blocked")


class AlwaysInjectMiddleware(BaseMiddleware):
    @property
    def name(self) -> str:
        return "always_inject"

    async def before_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult(signal=MiddlewareSignal.INJECT, message="injected")


class TrackingMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return "tracking"

    async def before_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        self.calls.append("before_step")
        return MiddlewareResult.ok()

    async def after_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        self.calls.append("after_step")
        return MiddlewareResult.ok()

    async def before_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo) -> MiddlewareResult:
        self.calls.append(f"before_tool:{tool_call.function_name}")
        return MiddlewareResult.ok()

    async def after_tool_call(
        self, ctx: MiddlewareContext, tool_call: ToolCallInfo, result: ToolResult
    ) -> MiddlewareResult:
        self.calls.append(f"after_tool:{tool_call.function_name}")
        return MiddlewareResult.ok()

    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> MiddlewareResult:
        self.calls.append(f"on_error:{type(error).__name__}")
        return MiddlewareResult.ok()


class TestPipelineOrdering:
    @pytest.mark.asyncio
    async def test_empty_pipeline_returns_continue(self) -> None:
        pipeline = MiddlewarePipeline()
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        result = await pipeline.run_before_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_first_non_continue_wins_for_before_hooks(self) -> None:
        tracker = TrackingMiddleware()
        pipeline = MiddlewarePipeline([tracker, AlwaysForceMiddleware(), AlwaysInjectMiddleware()])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        result = await pipeline.run_before_step(ctx)
        assert result.signal == MiddlewareSignal.FORCE
        assert "before_step" in tracker.calls

    @pytest.mark.asyncio
    async def test_all_run_for_after_hooks_last_wins(self) -> None:
        t1 = TrackingMiddleware()
        t2 = TrackingMiddleware()
        pipeline = MiddlewarePipeline([t1, t2])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        await pipeline.run_after_step(ctx)
        assert "after_step" in t1.calls
        assert "after_step" in t2.calls


class TestPipelineFluentApi:
    def test_use_returns_self_for_chaining(self) -> None:
        pipeline = MiddlewarePipeline()
        result = pipeline.use(TrackingMiddleware()).use(AlwaysForceMiddleware())
        assert result is pipeline
        assert len(pipeline.middleware) == 2


class TestPipelineErrorHandling:
    @pytest.mark.asyncio
    async def test_middleware_exception_is_swallowed(self) -> None:
        class BrokenMiddleware(BaseMiddleware):
            @property
            def name(self) -> str:
                return "broken"

            async def before_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
                raise RuntimeError("boom")

        pipeline = MiddlewarePipeline([BrokenMiddleware(), TrackingMiddleware()])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        result = await pipeline.run_before_step(ctx)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_on_error_hook_receives_exception(self) -> None:
        tracker = TrackingMiddleware()
        pipeline = MiddlewarePipeline([tracker])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        await pipeline.run_on_error(ctx, ValueError("test error"))
        assert "on_error:ValueError" in tracker.calls


class TestPipelineToolCallHooks:
    @pytest.mark.asyncio
    async def test_skip_tool_signal(self) -> None:
        pipeline = MiddlewarePipeline([AlwaysForceMiddleware()])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        tool = ToolCallInfo(call_id="c1", function_name="file_read", arguments={})
        result = await pipeline.run_before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.SKIP_TOOL

    @pytest.mark.asyncio
    async def test_after_tool_call_all_run(self) -> None:
        t1 = TrackingMiddleware()
        t2 = TrackingMiddleware()
        pipeline = MiddlewarePipeline([t1, t2])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        tool = ToolCallInfo(call_id="c1", function_name="shell_execute", arguments={})
        result_obj = ToolResult(success=True, message="ok")
        await pipeline.run_after_tool_call(ctx, tool, result_obj)
        assert "after_tool:shell_execute" in t1.calls
        assert "after_tool:shell_execute" in t2.calls
