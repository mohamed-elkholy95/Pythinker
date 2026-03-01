import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.security_critic import RiskLevel
from app.domain.services.tools.shell import ShellTool


class _SafeSecurityCritic:
    async def review_code(self, _code: str, _language: str) -> SimpleNamespace:
        return SimpleNamespace(
            safe=True,
            risk_level=RiskLevel.LOW,
            issues=[],
            patterns_detected=[],
        )


@pytest.mark.asyncio
async def test_shell_exec_returns_timeout_error_when_execution_exceeds_limit(monkeypatch: pytest.MonkeyPatch):
    sandbox = SimpleNamespace(exec_command=AsyncMock(return_value=ToolResult(success=True, message="done")))
    tool = ShellTool(sandbox=sandbox, security_critic=_SafeSecurityCritic())

    async def _wait_for_timeout(awaitable, timeout_seconds: float | None = None, **kwargs):
        if hasattr(awaitable, "close"):
            awaitable.close()
        effective_timeout = timeout_seconds if timeout_seconds is not None else kwargs.get("timeout")
        raise TimeoutError(f"timed out after {effective_timeout}")

    monkeypatch.setattr(asyncio, "wait_for", _wait_for_timeout)

    result = await tool.shell_exec(id="shell-1", exec_dir="/workspace", command="sleep 999")

    assert result.success is False
    assert result.message is not None
    assert "timed out" in result.message.lower()


@pytest.mark.asyncio
async def test_shell_exec_returns_tool_result_when_command_succeeds():
    expected = ToolResult(success=True, message="ok")
    sandbox = SimpleNamespace(exec_command=AsyncMock(return_value=expected))
    tool = ShellTool(sandbox=sandbox, security_critic=_SafeSecurityCritic())

    result = await tool.shell_exec(id="shell-2", exec_dir="/workspace", command="echo hello")

    assert result.success is True
    assert result.message == "ok"
    sandbox.exec_command.assert_awaited_once_with("shell-2", "/workspace", "echo hello")


@pytest.mark.asyncio
async def test_shell_exec_marks_failure_when_returncode_non_zero():
    sandbox_result = ToolResult(
        success=True,
        message="command failed",
        data={"returncode": 2, "output": "syntax error"},
    )
    sandbox = SimpleNamespace(exec_command=AsyncMock(return_value=sandbox_result))
    tool = ShellTool(sandbox=sandbox, security_critic=_SafeSecurityCritic())

    result = await tool.shell_exec(id="shell-3", exec_dir="/workspace", command="printf 'unterminated")

    assert result.success is False
    assert result.message is not None
    assert "return code: 2" in result.message.lower()


@pytest.mark.asyncio
async def test_shell_exec_rejects_missing_session_id_without_sandbox_call():
    sandbox = SimpleNamespace(exec_command=AsyncMock())
    tool = ShellTool(sandbox=sandbox, security_critic=_SafeSecurityCritic())

    result = await tool.shell_exec(id="", exec_dir="/workspace", command="ls")

    assert result.success is False
    assert result.message is not None
    assert "missing required parameter 'id'" in result.message.lower()
    sandbox.exec_command.assert_not_awaited()
