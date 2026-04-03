"""Base middleware with no-op defaults for all hooks."""

from __future__ import annotations

from typing import Any

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    ToolCallInfo,
)


class BaseMiddleware:
    """Concrete base with no-op defaults. Subclass to implement specific hooks."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

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
