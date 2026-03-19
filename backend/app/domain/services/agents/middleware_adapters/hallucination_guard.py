"""Middleware adapter for ToolHallucinationDetector."""

from __future__ import annotations

from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.hallucination_detector import (
    ToolHallucinationDetector,
)
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
    ToolCallInfo,
)


class HallucinationGuardMiddleware(BaseMiddleware):
    """Detects hallucinated tool names/params and injects corrections."""

    MAX_HALLUCINATIONS_PER_STEP: int = 3

    def __init__(self, detector: ToolHallucinationDetector) -> None:
        self._detector = detector
        self._count_this_step: int = 0

    @property
    def name(self) -> str:
        return "hallucination_guard"

    async def before_execution(self, ctx: MiddlewareContext) -> MiddlewareResult:
        """Reset per-step counter at the start of each execution."""
        self._count_this_step = 0
        return MiddlewareResult.ok()

    async def before_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        """Check if hallucination loop correction is needed."""
        if not self._detector.should_inject_correction_prompt():
            return MiddlewareResult.ok()

        self._count_this_step += 1
        if self._count_this_step >= self.MAX_HALLUCINATIONS_PER_STEP:
            return MiddlewareResult(
                signal=MiddlewareSignal.FORCE,
                message="Hallucination cap reached — force-advancing.",
            )

        correction = self._detector.get_correction_prompt()
        self._detector.reset()
        return MiddlewareResult(
            signal=MiddlewareSignal.INJECT,
            message=correction,
        )

    async def before_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo) -> MiddlewareResult:
        """Validate tool name exists and parameters are valid."""
        correction = self._detector.detect(tool_call.function_name)
        if correction:
            return MiddlewareResult(
                signal=MiddlewareSignal.SKIP_TOOL,
                message=correction,
                metadata={"hallucinated_tool": tool_call.function_name},
            )

        validation = self._detector.validate_tool_call(tool_call.function_name, tool_call.arguments)
        if not validation.is_valid:
            return MiddlewareResult(
                signal=MiddlewareSignal.SKIP_TOOL,
                message=validation.error_message or "Invalid tool call parameters.",
                metadata={
                    "error_type": validation.error_type,
                    "suggestions": validation.suggestions,
                },
            )

        return MiddlewareResult.ok()
