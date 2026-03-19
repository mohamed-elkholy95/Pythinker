"""Middleware adapter for ToolEfficiencyMonitor."""

from __future__ import annotations

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
    ToolCallInfo,
)
from app.domain.services.agents.tool_efficiency_monitor import ToolEfficiencyMonitor


class EfficiencyMonitorMiddleware(BaseMiddleware):
    """Detects analysis paralysis (too many reads without writes)."""

    def __init__(
        self,
        monitor: ToolEfficiencyMonitor | None = None,
        research_mode: str | None = None,
    ) -> None:
        self._monitor = monitor or ToolEfficiencyMonitor(research_mode=research_mode)

    @property
    def name(self) -> str:
        return "efficiency_monitor"

    async def after_tool_call(
        self, ctx: MiddlewareContext, tool_call: ToolCallInfo, result: ToolResult
    ) -> MiddlewareResult:
        """Record tool call for efficiency tracking."""
        self._monitor.record(tool_call.function_name)
        return MiddlewareResult.ok()

    async def before_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        """Check efficiency and inject nudge if imbalanced."""
        signal = self._monitor.check_efficiency()

        if signal.hard_stop:
            return MiddlewareResult(
                signal=MiddlewareSignal.FORCE,
                message=signal.nudge_message or "Analysis paralysis detected — force-advancing.",
            )

        if not signal.is_balanced and signal.nudge_message:
            return MiddlewareResult(
                signal=MiddlewareSignal.INJECT,
                message=signal.nudge_message,
            )

        return MiddlewareResult.ok()
