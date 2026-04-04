"""Tests for SecurityAssessmentMiddleware."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareSignal,
    ToolCallInfo,
)
from app.domain.services.agents.middleware_adapters.security_assessment import (
    SecurityAssessmentMiddleware,
)
from app.domain.services.agents.security_assessor import (
    ActionSecurityRisk,
    SecurityAssessment,
)


def _make_ctx() -> MiddlewareContext:
    return MiddlewareContext(agent_id="agent-1", session_id="session-1")


def _make_tool_call(
    function_name: str = "shell_exec",
    arguments: dict | None = None,
) -> ToolCallInfo:
    return ToolCallInfo(
        call_id="call-1",
        function_name=function_name,
        arguments=arguments or {},
    )


def _allowed_assessment() -> SecurityAssessment:
    return SecurityAssessment(
        blocked=False,
        reason="Action allowed in sandboxed environment",
        risk_level=ActionSecurityRisk.LOW,
    )


def _blocked_assessment(reason: str = "dangerous operation") -> SecurityAssessment:
    return SecurityAssessment(
        blocked=True,
        reason=reason,
        risk_level=ActionSecurityRisk.HIGH,
    )


class TestSecurityAssessmentMiddlewareName:
    def test_name_property(self) -> None:
        mw = SecurityAssessmentMiddleware()
        assert mw.name == "security_assessment"


class TestSecurityAssessmentMiddlewareAllowedAction:
    @pytest.mark.asyncio
    async def test_allowed_action_returns_continue_signal(self) -> None:
        class LegacyAssessor:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict]] = []

            def assess_action(self, function_name: str, arguments: dict) -> SecurityAssessment:
                self.calls.append((function_name, arguments))
                return _allowed_assessment()

        assessor = LegacyAssessor()
        mw = SecurityAssessmentMiddleware(assessor=assessor)

        result = await mw.before_tool_call(_make_ctx(), _make_tool_call())

        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_allowed_action_calls_assessor_with_correct_args(self) -> None:
        class LegacyAssessor:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict]] = []

            def assess_action(self, function_name: str, arguments: dict) -> SecurityAssessment:
                self.calls.append((function_name, arguments))
                return _allowed_assessment()

        assessor = LegacyAssessor()
        mw = SecurityAssessmentMiddleware(assessor=assessor)

        tool_call = _make_tool_call(function_name="file_read", arguments={"path": "/tmp/x"})
        await mw.before_tool_call(_make_ctx(), tool_call)

        assert assessor.calls == [("file_read", {"path": "/tmp/x"})]


class TestSecurityAssessmentMiddlewareBlockedAction:
    @pytest.mark.asyncio
    async def test_blocked_action_returns_skip_tool_signal(self) -> None:
        assessor = MagicMock()
        assessor.assess_action.return_value = _blocked_assessment("credential access denied")
        mw = SecurityAssessmentMiddleware(assessor=assessor)

        result = await mw.before_tool_call(_make_ctx(), _make_tool_call())

        assert result.signal == MiddlewareSignal.SKIP_TOOL

    @pytest.mark.asyncio
    async def test_blocked_action_includes_reason_in_message(self) -> None:
        assessor = MagicMock()
        assessor.assess_action.return_value = _blocked_assessment("rm -rf forbidden")
        mw = SecurityAssessmentMiddleware(assessor=assessor)

        result = await mw.before_tool_call(_make_ctx(), _make_tool_call())

        assert result.message == "rm -rf forbidden"

    @pytest.mark.asyncio
    async def test_blocked_action_includes_risk_level_in_metadata(self) -> None:
        assessor = MagicMock()
        assessor.assess_action.return_value = _blocked_assessment()
        mw = SecurityAssessmentMiddleware(assessor=assessor)

        result = await mw.before_tool_call(_make_ctx(), _make_tool_call())

        assert result.metadata["risk_level"] == ActionSecurityRisk.HIGH.value


class TestSecurityAssessmentMiddlewareDefaultAssessor:
    @pytest.mark.asyncio
    async def test_default_assessor_allows_all_actions(self) -> None:
        mw = SecurityAssessmentMiddleware()
        result = await mw.before_tool_call(_make_ctx(), _make_tool_call("shell_exec", {"cmd": "ls"}))
        assert result.signal == MiddlewareSignal.CONTINUE
