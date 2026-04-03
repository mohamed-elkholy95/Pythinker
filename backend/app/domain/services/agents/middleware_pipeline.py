"""Pipeline that chains middleware in registration order.

Before hooks: first non-CONTINUE signal wins (short-circuit).
After hooks: all middleware run, last non-CONTINUE signal wins.
"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.middleware import (
    AgentMiddleware,
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
    ToolCallInfo,
)

logger = logging.getLogger(__name__)


class MiddlewarePipeline:
    """Executes middleware hooks in registration order."""

    def __init__(self, middleware: list[AgentMiddleware] | None = None) -> None:
        self._middleware: list[AgentMiddleware] = list(middleware or [])

    def use(self, mw: AgentMiddleware) -> MiddlewarePipeline:
        """Register middleware (fluent API). Returns self for chaining."""
        self._middleware.append(mw)
        return self

    @property
    def middleware(self) -> list[AgentMiddleware]:
        """Read-only copy of registered middleware."""
        return list(self._middleware)

    async def _run_first_wins(self, hook_name: str, *args: Any) -> MiddlewareResult:
        """Run hook on all middleware. First non-CONTINUE signal wins."""
        for mw in self._middleware:
            hook = getattr(mw, hook_name, None)
            if hook is None:
                continue
            try:
                result: MiddlewareResult = await hook(*args)
                if result.signal != MiddlewareSignal.CONTINUE:
                    logger.debug("Middleware %s.%s returned %s", mw.name, hook_name, result.signal)
                    return result
            except Exception:
                logger.exception("Middleware %s.%s raised exception (swallowed)", mw.name, hook_name)
        return MiddlewareResult.ok()

    async def _run_all_last_wins(self, hook_name: str, *args: Any) -> MiddlewareResult:
        """Run hook on all middleware. Last non-CONTINUE signal wins."""
        final = MiddlewareResult.ok()
        for mw in self._middleware:
            hook = getattr(mw, hook_name, None)
            if hook is None:
                continue
            try:
                result: MiddlewareResult = await hook(*args)
                if result.signal != MiddlewareSignal.CONTINUE:
                    final = result
            except Exception:
                logger.exception("Middleware %s.%s raised exception (swallowed)", mw.name, hook_name)
        return final

    async def run_before_execution(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return await self._run_first_wins("before_execution", ctx)

    async def run_before_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return await self._run_first_wins("before_step", ctx)

    async def run_before_model(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return await self._run_first_wins("before_model", ctx)

    async def run_before_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo) -> MiddlewareResult:
        return await self._run_first_wins("before_tool_call", ctx, tool_call)

    async def run_after_model(self, ctx: MiddlewareContext, response: dict[str, Any]) -> MiddlewareResult:
        return await self._run_all_last_wins("after_model", ctx, response)

    async def run_after_tool_call(
        self, ctx: MiddlewareContext, tool_call: ToolCallInfo, result: ToolResult
    ) -> MiddlewareResult:
        return await self._run_all_last_wins("after_tool_call", ctx, tool_call, result)

    async def run_after_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return await self._run_all_last_wins("after_step", ctx)

    async def run_after_execution(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return await self._run_all_last_wins("after_execution", ctx)

    async def run_on_error(self, ctx: MiddlewareContext, error: Exception) -> MiddlewareResult:
        return await self._run_first_wins("on_error", ctx, error)
