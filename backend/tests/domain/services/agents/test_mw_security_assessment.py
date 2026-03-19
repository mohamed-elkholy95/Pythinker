"""Tests for SecurityAssessmentMiddleware."""

import pytest

from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareSignal,
    ToolCallInfo,
)
from app.domain.services.agents.middleware_adapters.security_assessment import (
    SecurityAssessmentMiddleware,
)
from app.domain.services.agents.security_assessor import SecurityAssessor


@pytest.fixture
def mw():
    return SecurityAssessmentMiddleware(assessor=SecurityAssessor())


@pytest.fixture
def ctx():
    return MiddlewareContext(agent_id="test", session_id="test")


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
