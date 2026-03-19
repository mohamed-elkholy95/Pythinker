"""Middleware for wall-clock time pressure management."""

from __future__ import annotations

from app.domain.models.tool_name import ToolName
from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
    ToolCallInfo,
)

_WRITE_TOOLS = frozenset({"file_write", "file_str_replace", "code_save_artifact"})


class WallClockPressureMiddleware(BaseMiddleware):
    """Applies graduated pressure based on elapsed/budget ratio."""

    @property
    def name(self) -> str:
        return "wall_clock_pressure"

    def _get_pressure_level(self, ctx: MiddlewareContext) -> str | None:
        """Return pressure level based on elapsed/budget ratio."""
        if ctx.wall_clock_budget <= 0:
            return None
        ratio = ctx.elapsed_seconds / ctx.wall_clock_budget
        if ratio >= 0.90:
            return "CRITICAL"
        if ratio >= 0.75:
            return "URGENT"
        if ratio >= 0.50:
            return "ADVISORY"
        return None

    async def before_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        level = self._get_pressure_level(ctx)
        if level == "CRITICAL":
            return MiddlewareResult(
                signal=MiddlewareSignal.FORCE,
                message="Wall-clock CRITICAL (90%+). Conclude now.",
                metadata={"pressure_level": level},
            )
        return MiddlewareResult.ok()

    async def before_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo) -> MiddlewareResult:
        level = self._get_pressure_level(ctx)
        if not level:
            return MiddlewareResult.ok()

        fn = tool_call.function_name
        if level == "CRITICAL" and fn not in _WRITE_TOOLS:
            return MiddlewareResult(
                signal=MiddlewareSignal.SKIP_TOOL,
                message=f"Wall-clock CRITICAL — only write tools allowed. Blocked: {fn}",
            )

        if level == "URGENT":
            read_tools = frozenset(t.value for t in ToolName.read_only_tools())
            if fn in read_tools:
                return MiddlewareResult(
                    signal=MiddlewareSignal.SKIP_TOOL,
                    message=f"Wall-clock URGENT — read-only tools blocked. Blocked: {fn}",
                )

        return MiddlewareResult.ok()
