"""Permission gate middleware.

Evaluates a PermissionPolicy before every tool call. When a tool is denied,
emits SKIP_TOOL so the pipeline never reaches the actual tool executor.

Runs after SecurityAssessmentMiddleware so security blocks are reported first.
"""

from __future__ import annotations

import logging

from app.domain.models.tool_permission import PermissionPolicy
from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
    ToolCallInfo,
)

logger = logging.getLogger(__name__)


class PermissionGateMiddleware(BaseMiddleware):
    """Enforces a PermissionPolicy before tool execution.

    Usage:
        policy = PermissionPolicy(rules=[
            ToolPermissionRule("rm", PermissionAction.DENY, "destructive"),
        ])
        pipeline.use(PermissionGateMiddleware(policy=policy))

    When no policy is provided, all tools are allowed (fail-open default).
    """

    def __init__(self, policy: PermissionPolicy | None = None) -> None:
        self._policy = policy or PermissionPolicy()

    @property
    def name(self) -> str:
        return "permission_gate"

    async def before_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo) -> MiddlewareResult:
        denied, reason = self._policy.is_denied(tool_call.function_name)
        if denied:
            msg = reason or f"Tool '{tool_call.function_name}' is not permitted by policy."
            logger.info(
                "PermissionGate blocked tool=%s session=%s reason=%r",
                tool_call.function_name,
                ctx.session_id,
                msg,
            )
            return MiddlewareResult(
                signal=MiddlewareSignal.SKIP_TOOL,
                message=msg,
                metadata={"blocked_by": "permission_gate", "tool": tool_call.function_name},
            )
        return MiddlewareResult.ok()
