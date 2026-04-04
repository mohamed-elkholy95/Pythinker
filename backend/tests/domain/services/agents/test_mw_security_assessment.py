"""Tests for SecurityAssessmentMiddleware."""

import pytest

from app.domain.models.tool_permission import PermissionTier
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareSignal,
    ToolCallInfo,
)
from app.domain.services.agents.middleware_adapters.security_assessment import (
    SecurityAssessmentMiddleware,
)
from app.domain.services.agents.security_assessor import SecurityAssessor
from app.domain.services.tools.base import BaseTool, tool
from app.domain.services.tools.metadata_index import ToolMetadataIndex


@pytest.fixture
def mw():
    return SecurityAssessmentMiddleware(assessor=SecurityAssessor())


@pytest.fixture
def ctx():
    return MiddlewareContext(agent_id="test", session_id="test")


def _tool_index() -> ToolMetadataIndex:
    class PermissionTestTool(BaseTool):
        name = "permission_test"

        @tool(
            name="shell_exec",
            description="Run shell command",
            parameters={},
            required=[],
            required_tier=PermissionTier.DANGER,
        )
        async def shell_exec(self):
            pass

    return ToolMetadataIndex([PermissionTestTool()])


class TestSecurityAssessmentName:
    def test_name(self, mw):
        assert mw.name == "security_assessment"


class TestBeforeToolCall:
    @pytest.mark.asyncio
    async def test_allowed_action_returns_continue(self, mw, ctx):
        tool = ToolCallInfo(call_id="1", function_name="file_read", arguments={})
        result = await mw.before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_default_assessor_allows_all(self, ctx):
        """Default SecurityAssessor allows all actions (sandbox isolation)."""
        mw = SecurityAssessmentMiddleware()
        tool = ToolCallInfo(
            call_id="1",
            function_name="shell_execute",
            arguments={"command": "rm -rf /"},
        )
        result = await mw.before_tool_call(ctx, tool)
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_blocks_when_tier_check_fails(self):
        mw = SecurityAssessmentMiddleware(
            assessor=SecurityAssessor(),
            tool_metadata_index=_tool_index(),
        )
        tool = ToolCallInfo(
            call_id="1",
            function_name="shell_exec",
            arguments={"command": "rm -rf /"},
        )
        result = await mw.before_tool_call(
            MiddlewareContext(agent_id="test", session_id="test", active_tier=PermissionTier.READ_ONLY),
            tool,
        )
        assert result.signal == MiddlewareSignal.SKIP_TOOL
        assert result.metadata.get("risk_level") == "high"
