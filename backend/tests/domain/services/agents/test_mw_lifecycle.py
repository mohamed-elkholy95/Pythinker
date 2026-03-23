"""Tests for middleware lifecycle hooks."""

from __future__ import annotations

from typing import Any

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    ToolCallInfo,
)
from app.domain.services.agents.middleware_pipeline import MiddlewarePipeline


class TrackingMiddleware(BaseMiddleware):
    """Test middleware that tracks lifecycle calls."""

    def __init__(self):
        self.boundary_count = 0

    @property
    def name(self) -> str:
        return "tracking"

    def on_step_boundary(self) -> None:
        self.boundary_count += 1


class LegacyMiddleware:
    """Middleware without on_step_boundary but with reset_browser_budget.

    Does NOT extend BaseMiddleware so it lacks the inherited no-op
    on_step_boundary — simulating a pre-lifecycle-hook middleware.
    """

    def __init__(self):
        self.reset_count = 0

    @property
    def name(self) -> str:
        return "legacy"

    def reset_browser_budget(self) -> None:
        self.reset_count += 1

    # Minimal AgentMiddleware protocol stubs so the pipeline accepts it.
    async def before_execution(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def before_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def before_model(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def after_model(self, ctx: MiddlewareContext, response: dict[str, Any]) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def before_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def after_tool_call(
        self, ctx: MiddlewareContext, tool_call: ToolCallInfo, result: ToolResult
    ) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def after_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def after_execution(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult.ok()

    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> MiddlewareResult:
        return MiddlewareResult.ok()


class TestMiddlewareLifecycle:
    def test_run_step_boundary_calls_on_step_boundary(self):
        mw = TrackingMiddleware()
        pipeline = MiddlewarePipeline()
        pipeline.use(mw)

        pipeline.run_step_boundary()

        assert mw.boundary_count == 1

    def test_run_step_boundary_calls_multiple_middleware(self):
        mw1 = TrackingMiddleware()
        mw2 = TrackingMiddleware()
        pipeline = MiddlewarePipeline()
        pipeline.use(mw1).use(mw2)

        pipeline.run_step_boundary()

        assert mw1.boundary_count == 1
        assert mw2.boundary_count == 1

    def test_run_step_boundary_increments_on_repeated_calls(self):
        mw = TrackingMiddleware()
        pipeline = MiddlewarePipeline()
        pipeline.use(mw)

        pipeline.run_step_boundary()
        pipeline.run_step_boundary()
        pipeline.run_step_boundary()

        assert mw.boundary_count == 3

    def test_reset_for_new_step_delegates_to_run_step_boundary(self):
        mw = TrackingMiddleware()
        pipeline = MiddlewarePipeline()
        pipeline.use(mw)

        pipeline.reset_for_new_step()

        assert mw.boundary_count == 1

    def test_legacy_middleware_uses_reset_browser_budget_fallback(self):
        mw = LegacyMiddleware()
        pipeline = MiddlewarePipeline()
        pipeline.use(mw)

        pipeline.run_step_boundary()

        assert mw.reset_count == 1

    def test_mixed_middleware_types(self):
        modern = TrackingMiddleware()
        legacy = LegacyMiddleware()
        pipeline = MiddlewarePipeline()
        pipeline.use(modern).use(legacy)

        pipeline.run_step_boundary()

        assert modern.boundary_count == 1
        assert legacy.reset_count == 1

    def test_error_in_one_middleware_doesnt_block_others(self):
        class BrokenMiddleware(BaseMiddleware):
            def on_step_boundary(self) -> None:
                raise RuntimeError("boom")

        broken = BrokenMiddleware()
        healthy = TrackingMiddleware()
        pipeline = MiddlewarePipeline()
        pipeline.use(broken).use(healthy)

        pipeline.run_step_boundary()  # Should not raise

        assert healthy.boundary_count == 1  # Still called despite broken mw
