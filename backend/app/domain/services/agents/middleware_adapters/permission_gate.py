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
from app.domain.services.tools.metadata_index import ToolMetadataIndex

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

    def __init__(
        self,
        policy: PermissionPolicy | None = None,
        tool_metadata_index: ToolMetadataIndex | None = None,
    ) -> None:
        self._policy = policy or PermissionPolicy()
        self._tool_metadata_index = tool_metadata_index

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

        if self._tool_metadata_index is None:
            return MiddlewareResult.ok()

        required_tier = self._tool_metadata_index.get_required_tier(tool_call.function_name)
        if required_tier > ctx.active_tier:
            message = (
                f"tool '{tool_call.function_name}' requires {required_tier.as_str()} permission; "
                f"current mode is {ctx.active_tier.as_str()}"
            )
            logger.info(
                "PermissionGate blocked tool=%s session=%s active_tier=%s required_tier=%s",
                tool_call.function_name,
                ctx.session_id,
                ctx.active_tier.as_str(),
                required_tier.as_str(),
            )
            return MiddlewareResult(
                signal=MiddlewareSignal.SKIP_TOOL,
                message=message,
                metadata={
                    "blocked_by": "permission_gate",
                    "tool": tool_call.function_name,
                    "required_tier": required_tier.as_str(),
                    "active_tier": ctx.active_tier.as_str(),
                },
            )

        return MiddlewareResult.ok()
