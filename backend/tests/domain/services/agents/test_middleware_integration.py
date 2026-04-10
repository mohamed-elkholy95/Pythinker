"""Integration tests for middleware pipeline end-to-end."""

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


class OrderTracker(BaseMiddleware):
    """Tracks hook call order across the full lifecycle."""

    def __init__(self, name_str: str) -> None:
        self._name = name_str
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    async def before_execution(self, ctx):
        self.calls.append(f"{self._name}:before_execution")
        return MiddlewareResult.ok()

    async def before_step(self, ctx):
        self.calls.append(f"{self._name}:before_step")
        return MiddlewareResult.ok()

    async def before_model(self, ctx):
        self.calls.append(f"{self._name}:before_model")
        return MiddlewareResult.ok()

    async def after_model(self, ctx, response):
        self.calls.append(f"{self._name}:after_model")
        return MiddlewareResult.ok()

    async def before_tool_call(self, ctx, tool_call):
        self.calls.append(f"{self._name}:before_tool:{tool_call.function_name}")
        return MiddlewareResult.ok()

    async def after_tool_call(self, ctx, tool_call, result):
        self.calls.append(f"{self._name}:after_tool:{tool_call.function_name}")
        return MiddlewareResult.ok()

    async def after_step(self, ctx):
        self.calls.append(f"{self._name}:after_step")
        return MiddlewareResult.ok()

    async def after_execution(self, ctx):
        self.calls.append(f"{self._name}:after_execution")
        return MiddlewareResult.ok()

    async def on_error(self, ctx, error):
        self.calls.append(f"{self._name}:on_error:{type(error).__name__}")
        return MiddlewareResult.ok()


class TestFullLifecycleSequence:
    """Verify correct hook ordering through a realistic agent iteration."""

    @pytest.mark.asyncio
    async def test_multi_hook_sequence(self):
        security = OrderTracker("security")
        hallucination = OrderTracker("hallucination")
        pipeline = MiddlewarePipeline([security, hallucination])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")
        tool = ToolCallInfo(call_id="c1", function_name="file_read", arguments={})
        tool_result = ToolResult(success=True, message="ok")

        # Simulate full iteration lifecycle
        await pipeline.run_before_execution(ctx)
        await pipeline.run_before_step(ctx)
        await pipeline.run_before_model(ctx)
        await pipeline.run_after_model(ctx, {"content": "response"})
        await pipeline.run_before_tool_call(ctx, tool)
        await pipeline.run_after_tool_call(ctx, tool, tool_result)
        await pipeline.run_after_step(ctx)
        await pipeline.run_after_execution(ctx)

        # Both middleware should have been called for all hooks
        expected_security = [
            "security:before_execution",
            "security:before_step",
            "security:before_model",
            "security:after_model",
            "security:before_tool:file_read",
            "security:after_tool:file_read",
            "security:after_step",
            "security:after_execution",
        ]
        assert security.calls == expected_security

        expected_hallucination = [
            "hallucination:before_execution",
            "hallucination:before_step",
            "hallucination:before_model",
            "hallucination:after_model",
            "hallucination:before_tool:file_read",
            "hallucination:after_tool:file_read",
            "hallucination:after_step",
            "hallucination:after_execution",
        ]
        assert hallucination.calls == expected_hallucination

    @pytest.mark.asyncio
    async def test_short_circuit_prevents_later_middleware(self):
        """First middleware FORCE should prevent later middleware from running on before_step."""

        class ForceMiddleware(BaseMiddleware):
            @property
            def name(self):
                return "forcer"

            async def before_step(self, ctx):
                return MiddlewareResult(signal=MiddlewareSignal.FORCE, message="stop")

        tracker = OrderTracker("should_not_run")
        pipeline = MiddlewarePipeline([ForceMiddleware(), tracker])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")

        result = await pipeline.run_before_step(ctx)
        assert result.signal == MiddlewareSignal.FORCE
        # tracker's before_step should NOT have been called
        assert "should_not_run:before_step" not in tracker.calls

    @pytest.mark.asyncio
    async def test_on_error_with_pipeline(self):
        tracker = OrderTracker("error_tracker")
        pipeline = MiddlewarePipeline([tracker])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")

        await pipeline.run_on_error(ctx, ValueError("test"))
        assert "error_tracker:on_error:ValueError" in tracker.calls

    @pytest.mark.asyncio
    async def test_context_shared_across_middleware(self):
        """Verify middleware can communicate via ctx.metadata."""

        class WriterMiddleware(BaseMiddleware):
            @property
            def name(self):
                return "writer"

            async def before_step(self, ctx):
                ctx.metadata["written_by"] = "writer"
                return MiddlewareResult.ok()

        class ReaderMiddleware(BaseMiddleware):
            def __init__(self):
                self.read_value = None

            @property
            def name(self):
                return "reader"

            async def before_step(self, ctx):
                self.read_value = ctx.metadata.get("written_by")
                return MiddlewareResult.ok()

        reader = ReaderMiddleware()
        pipeline = MiddlewarePipeline([WriterMiddleware(), reader])
        ctx = MiddlewareContext(agent_id="a1", session_id="s1")

        await pipeline.run_before_step(ctx)
        assert reader.read_value == "writer"


class TestFactoryProducesWorkingPipeline:
    """Verify AgentContextFactory creates a pipeline that runs correctly."""

    @pytest.mark.asyncio
    async def test_factory_pipeline_runs_all_hooks(self):
        from app.domain.services.agents.agent_context_factory import AgentContextFactory

        factory = AgentContextFactory()
        ctx_service = factory.create(
            agent_id="test",
            session_id="test",
            tools=[],
            feature_flags={},
        )

        mw_ctx = MiddlewareContext(agent_id="test", session_id="test")
        tool = ToolCallInfo(call_id="c1", function_name="file_read", arguments={})
        tool_result = ToolResult(success=True, message="ok")

        # All hooks should run without error
        await ctx_service.middleware_pipeline.run_before_execution(mw_ctx)
        await ctx_service.middleware_pipeline.run_before_step(mw_ctx)
        await ctx_service.middleware_pipeline.run_before_model(mw_ctx)
        await ctx_service.middleware_pipeline.run_after_model(mw_ctx, {})
        await ctx_service.middleware_pipeline.run_before_tool_call(mw_ctx, tool)
        await ctx_service.middleware_pipeline.run_after_tool_call(mw_ctx, tool, tool_result)
        await ctx_service.middleware_pipeline.run_after_step(mw_ctx)
        await ctx_service.middleware_pipeline.run_after_execution(mw_ctx)
        await ctx_service.middleware_pipeline.run_on_error(mw_ctx, RuntimeError("test"))

    def test_factory_middleware_count(self):
        from app.domain.services.agents.agent_context_factory import AgentContextFactory

        factory = AgentContextFactory()
        ctx_service = factory.create(
            agent_id="test",
            session_id="test",
            tools=[],
            feature_flags={},
        )
        assert len(ctx_service.middleware_pipeline.middleware) == 9
