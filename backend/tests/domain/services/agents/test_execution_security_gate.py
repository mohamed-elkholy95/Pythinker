"""Tests for mandatory security gate before code/shell execution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.prometheus_metrics import security_gate_blocks_total
from app.domain.services.agents.security_critic import SecurityCritic
from app.domain.services.tools.code_executor import CodeExecutorTool
from app.domain.services.tools.shell import ShellTool


@pytest.mark.asyncio
async def test_critical_code_blocked_before_execution() -> None:
    """CRITICAL risk code must be blocked before sandbox execution."""
    sandbox = AsyncMock()
    sandbox.exec_command = AsyncMock()
    sandbox.file_write = AsyncMock(return_value=MagicMock(success=True))
    sandbox.file_delete = AsyncMock()

    critic = SecurityCritic()
    tool = CodeExecutorTool(sandbox=sandbox, security_critic=critic)

    with patch("app.domain.services.tools.code_executor.get_settings") as mock_settings:
        mock_settings.return_value.security_critic_allow_medium_risk = False

        result = await tool.code_execute(code="import os; os.system('rm -rf /')", language="python")

    assert result.success is False
    assert "blocked" in result.message.lower() or "security" in result.message.lower()
    sandbox.exec_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_critical_shell_command_blocked() -> None:
    """CRITICAL risk shell commands must be blocked."""
    sandbox = AsyncMock()
    sandbox.exec_command = AsyncMock()

    critic = SecurityCritic()
    tool = ShellTool(sandbox=sandbox, security_critic=critic)

    with patch("app.domain.services.tools.shell.get_settings") as mock_settings:
        mock_settings.return_value.security_critic_allow_medium_risk = False

        result = await tool.shell_exec(id="s1", exec_dir="/tmp", command="rm -rf /")

    assert result.success is False
    assert "blocked" in result.message.lower() or "security" in result.message.lower()
    sandbox.exec_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_medium_risk_blocked_when_allow_disabled() -> None:
    """MEDIUM risk blocked when SECURITY_CRITIC_ALLOW_MEDIUM_RISK is False."""
    sandbox = AsyncMock()
    sandbox.exec_command = AsyncMock()

    critic = SecurityCritic()
    tool = CodeExecutorTool(sandbox=sandbox, security_critic=critic)

    with patch("app.domain.services.tools.code_executor.get_settings") as mock_settings:
        mock_settings.return_value.security_critic_allow_medium_risk = False

        result = await tool.code_execute(code="os.system('ls')", language="python")

    assert result.success is False
    sandbox.exec_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_metrics_recorded_on_block() -> None:
    """Blocking must record security_gate_blocks_total."""
    before = security_gate_blocks_total.get({"risk_level": "critical", "pattern_type": "static"})

    sandbox = AsyncMock()
    tool = CodeExecutorTool(sandbox=sandbox, security_critic=SecurityCritic())

    with patch("app.domain.services.tools.code_executor.get_settings") as mock_settings:
        mock_settings.return_value.security_critic_allow_medium_risk = False
        await tool.code_execute(code="os.system('rm -rf /')", language="python")

    after = security_gate_blocks_total.get({"risk_level": "critical", "pattern_type": "static"})
    assert after >= before + 1
