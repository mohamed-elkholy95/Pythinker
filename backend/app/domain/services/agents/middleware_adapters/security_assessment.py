"""Middleware adapter for SecurityAssessor."""

from __future__ import annotations

from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
    ToolCallInfo,
)
from app.domain.services.agents.security_assessor import SecurityAssessor


class SecurityAssessmentMiddleware(BaseMiddleware):
    """Evaluates security risk of tool calls before execution."""

    def __init__(self, assessor: SecurityAssessor | None = None) -> None:
        self._assessor = assessor or SecurityAssessor()

    @property
    def name(self) -> str:
        return "security_assessment"

    async def before_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo) -> MiddlewareResult:
        assessment = self._assessor.assess_action(tool_call.function_name, tool_call.arguments)
        if assessment.blocked:
            return MiddlewareResult(
                signal=MiddlewareSignal.SKIP_TOOL,
                message=assessment.reason,
                metadata={"risk_level": assessment.risk_level.value},
            )
        return MiddlewareResult.ok()
