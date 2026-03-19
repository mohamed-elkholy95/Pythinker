"""Middleware adapter for UrlFailureGuard."""

from __future__ import annotations

from typing import Any

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
    ToolCallInfo,
)


def _extract_url_from_args(arguments: dict[str, Any]) -> str | None:
    """Extract URL from tool call arguments."""
    for key in ("url", "target_url", "page_url", "query"):
        val = arguments.get(key)
        if val and isinstance(val, str) and val.startswith(("http://", "https://")):
            return val
    return None


class UrlFailureGuardMiddleware(BaseMiddleware):
    """Skips tool calls targeting known-failed URLs."""

    def __init__(self, guard: Any = None) -> None:
        self._guard = guard  # UrlFailureGuard or None

    @property
    def name(self) -> str:
        return "url_failure_guard"

    async def before_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo) -> MiddlewareResult:
        if self._guard is None:
            return MiddlewareResult.ok()

        url = _extract_url_from_args(tool_call.arguments)
        if not url:
            return MiddlewareResult.ok()

        decision = self._guard.check_url(url)
        if decision and decision.action == "block":
            return MiddlewareResult(
                signal=MiddlewareSignal.SKIP_TOOL,
                message=decision.message or f"URL previously failed: {url}",
                metadata={"blocked_url": url},
            )
        return MiddlewareResult.ok()

    async def after_tool_call(
        self, ctx: MiddlewareContext, tool_call: ToolCallInfo, result: ToolResult
    ) -> MiddlewareResult:
        if self._guard is None:
            return MiddlewareResult.ok()

        url = _extract_url_from_args(tool_call.arguments)
        if url and not result.success:
            self._guard.record_failure(
                url,
                result.message[:200] if result.message else "unknown error",
                tool_call.function_name,
            )
        return MiddlewareResult.ok()
