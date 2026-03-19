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
        if not level:
            return MiddlewareResult.ok()

        sent_key = f"wall_clock_{level.lower()}_sent"

        if level == "CRITICAL":
            if not ctx.metadata.get(sent_key):
                ctx.metadata[sent_key] = True
            return MiddlewareResult(
                signal=MiddlewareSignal.FORCE,
                message=(
                    f"STEP TIME CRITICAL: 90% of budget used ({ctx.elapsed_seconds:.0f}s of "
                    f"{ctx.wall_clock_budget:.0f}s). ALL tools except file_write and "
                    f"code_save_artifact are BLOCKED. Write your output NOW."
                ),
                metadata={"pressure_level": level},
            )

        if level == "URGENT" and not ctx.metadata.get(sent_key):
            ctx.metadata[sent_key] = True
            return MiddlewareResult(
                signal=MiddlewareSignal.INJECT,
                message=(
                    f"STEP TIME URGENT: 75% of budget used ({ctx.elapsed_seconds:.0f}s of "
                    f"{ctx.wall_clock_budget:.0f}s). Read-only tools are now BLOCKED. "
                    f"You MUST finalize your output immediately."
                ),
                metadata={"pressure_level": level},
            )

        if level == "ADVISORY" and not ctx.metadata.get(sent_key):
            ctx.metadata[sent_key] = True
            ctx.injected_messages.append(
                {
                    "role": "user",
                    "content": (
                        f"STEP TIME ADVISORY: You have used 50% of the step time budget "
                        f"({ctx.elapsed_seconds:.0f}s of {ctx.wall_clock_budget:.0f}s). "
                        f"Begin wrapping up research and focus on writing output."
                    ),
                }
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
