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
from app.domain.services.tools.metadata_index import ToolMetadataIndex


class SecurityAssessmentMiddleware(BaseMiddleware):
    """Evaluates security risk of tool calls before execution."""

    def __init__(
        self,
        assessor: SecurityAssessor | None = None,
        tool_metadata_index: ToolMetadataIndex | None = None,
    ) -> None:
        self._assessor = assessor or SecurityAssessor()
        self._tool_metadata_index = tool_metadata_index

    @property
    def name(self) -> str:
        return "security_assessment"

    async def before_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo) -> MiddlewareResult:
        required_tier = None
        if self._tool_metadata_index is not None:
            required_tier = self._tool_metadata_index.get_required_tier(tool_call.function_name)
        if isinstance(self._assessor, SecurityAssessor):
            assessment = self._assessor.assess_action(
                tool_call.function_name,
                tool_call.arguments,
                active_tier=ctx.active_tier,
                required_tier=required_tier,
            )
        else:
            assessment = self._assessor.assess_action(tool_call.function_name, tool_call.arguments)
        if assessment.blocked:
            return MiddlewareResult(
                signal=MiddlewareSignal.SKIP_TOOL,
                message=assessment.reason,
                metadata={"risk_level": assessment.risk_level.value},
            )
        return MiddlewareResult.ok()
