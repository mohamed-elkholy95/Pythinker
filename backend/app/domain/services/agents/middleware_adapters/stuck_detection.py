"""Middleware adapter for StuckDetector."""

from __future__ import annotations

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
    ToolCallInfo,
)
from app.domain.services.agents.stuck_detector import StuckDetector


class StuckDetectionMiddleware(BaseMiddleware):
    """Tracks responses and tool actions for stuck loop detection."""

    def __init__(self, detector: StuckDetector | None = None) -> None:
        self._detector = detector or StuckDetector(window_size=5, threshold=3)

    @property
    def name(self) -> str:
        return "stuck_detection"

    async def before_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo) -> MiddlewareResult:
        # track_tool_action requires success param — optimistic True before execution
        self._detector.track_tool_action(tool_call.function_name, tool_call.arguments, success=True)
        return MiddlewareResult.ok()

    async def after_tool_call(
        self, ctx: MiddlewareContext, tool_call: ToolCallInfo, result: ToolResult
    ) -> MiddlewareResult:
        # Update with actual success/failure after execution
        if not result.success:
            self._detector.track_tool_action(
                tool_call.function_name,
                tool_call.arguments,
                success=False,
                error=result.message[:200] if result.message else None,
            )
        return MiddlewareResult.ok()

    async def after_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        # track_response expects a dict with "content" and optionally "tool_calls"
        last_response = ctx.metadata.get("last_response", {})
        if not last_response:
            return MiddlewareResult.ok()

        is_stuck, _confidence = self._detector.track_response(last_response)

        if is_stuck and not self._detector.can_attempt_recovery():
            return MiddlewareResult(
                signal=MiddlewareSignal.FORCE,
                message="Stuck recovery exhausted — force-advancing to next step.",
            )

        if is_stuck:
            self._detector.record_recovery_attempt()
            recovery = self._detector.get_recovery_prompt()
            return MiddlewareResult(
                signal=MiddlewareSignal.INJECT,
                message=recovery,
            )

        return MiddlewareResult.ok()
