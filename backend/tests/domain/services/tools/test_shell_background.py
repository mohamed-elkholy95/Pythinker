"""Tests for shell_exec_background and shell_poll_background."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.security_critic import RiskLevel
from app.domain.services.tools.shell import ShellTool


class _SafeCritic:
    async def review_code(self, _code: str, _lang: str, context: str | None = None) -> SimpleNamespace:
        return SimpleNamespace(safe=True, risk_level=RiskLevel.LOW, issues=[], patterns_detected=[])


class _BlockingCritic:
    async def review_code(self, _code: str, _lang: str, context: str | None = None) -> SimpleNamespace:
        return SimpleNamespace(
            safe=False, risk_level=RiskLevel.HIGH, issues=["dangerous"], patterns_detected=["rm -rf"]
        )


def _tool(sandbox_exec_return: ToolResult | None = None) -> ShellTool:
    """Build a ShellTool with a mock sandbox."""
    result = sandbox_exec_return or ToolResult(success=True, message="12345")
    sandbox = SimpleNamespace(exec_command=AsyncMock(return_value=result))
    return ShellTool(sandbox=sandbox, security_critic=_SafeCritic())


# ── shell_exec_background ───────────────────────────────────────────────────


class TestShellExecBackground:
    @pytest.mark.asyncio
    async def test_returns_job_id_and_pid(self):
        tool = _tool(ToolResult(success=True, message="42\n"))
        result = await tool.shell_exec_background(id="s1", exec_dir="/workspace", command="sleep 60")

        assert result.success is True
        data = result.data or {}
        assert "job_id" in data
        assert data["pid"] == 42

    @pytest.mark.asyncio
    async def test_job_stored_in_registry(self):
        tool = _tool(ToolResult(success=True, message="99\n"))
        result = await tool.shell_exec_background(id="s1", exec_dir="/workspace", command="sleep 60")

        job_id = result.data["job_id"]
        assert job_id in tool._bg_jobs
        assert tool._bg_jobs[job_id].pid == 99
        assert tool._bg_jobs[job_id].session_id == "s1"

    @pytest.mark.asyncio
    async def test_missing_session_id_rejected(self):
        tool = _tool()
        result = await tool.shell_exec_background(id="", exec_dir="/workspace", command="sleep 60")
        assert result.success is False
        assert "missing required parameter 'id'" in result.message.lower()

    @pytest.mark.asyncio
    async def test_missing_exec_dir_rejected(self):
        tool = _tool()
        result = await tool.shell_exec_background(id="s1", exec_dir="", command="sleep 60")
        assert result.success is False
        assert "exec_dir" in result.message.lower()

    @pytest.mark.asyncio
    async def test_missing_command_rejected(self):
        tool = _tool()
        result = await tool.shell_exec_background(id="s1", exec_dir="/workspace", command="")
        assert result.success is False
        assert "command" in result.message.lower()

    @pytest.mark.asyncio
    async def test_security_block(self):
        sandbox = SimpleNamespace(exec_command=AsyncMock())
        tool = ShellTool(sandbox=sandbox, security_critic=_BlockingCritic())
        result = await tool.shell_exec_background(id="s1", exec_dir="/workspace", command="rm -rf /")
        assert result.success is False
        assert "blocked" in result.message.lower()
        sandbox.exec_command.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sandbox_failure_propagated(self):
        tool = _tool(ToolResult(success=False, message="sandbox error"))
        result = await tool.shell_exec_background(id="s1", exec_dir="/workspace", command="sleep 60")
        assert result.success is False
        assert "sandbox error" in result.message.lower()

    @pytest.mark.asyncio
    async def test_pid_parsed_from_multiline_output(self):
        # Output may have nohup header before PID
        tool = _tool(ToolResult(success=True, message="nohup: appending output\n7777\n"))
        result = await tool.shell_exec_background(id="s1", exec_dir="/workspace", command="sleep 60")
        assert result.data["pid"] == 7777

    @pytest.mark.asyncio
    async def test_pid_none_when_not_parseable(self):
        tool = _tool(ToolResult(success=True, message="some non-pid output\n"))
        result = await tool.shell_exec_background(id="s1", exec_dir="/workspace", command="sleep 60")
        assert result.success is True
        assert result.data["pid"] is None

    @pytest.mark.asyncio
    async def test_output_file_path_includes_job_id(self):
        tool = _tool(ToolResult(success=True, message="1234\n"))
        result = await tool.shell_exec_background(id="s1", exec_dir="/workspace", command="ls")
        job_id = result.data["job_id"]
        assert job_id in result.data["output_file"]

    @pytest.mark.asyncio
    async def test_launch_command_uses_nohup(self):
        sandbox = SimpleNamespace(exec_command=AsyncMock(return_value=ToolResult(success=True, message="1\n")))
        tool = ShellTool(sandbox=sandbox, security_critic=_SafeCritic())
        await tool.shell_exec_background(id="s1", exec_dir="/workspace", command="sleep 60")

        called_cmd = sandbox.exec_command.call_args[0][2]
        assert "nohup" in called_cmd
        assert "sleep 60" in called_cmd


# ── shell_poll_background ───────────────────────────────────────────────────


class TestShellPollBackground:
    async def _start_job(self, tool: ShellTool, command: str = "sleep 60") -> str:
        result = await tool.shell_exec_background(id="s1", exec_dir="/workspace", command=command)
        return result.data["job_id"]

    @pytest.mark.asyncio
    async def test_unknown_job_id_returns_error(self):
        sandbox = SimpleNamespace(exec_command=AsyncMock())
        tool = ShellTool(sandbox=sandbox, security_critic=_SafeCritic())
        result = await tool.shell_poll_background(id="s1", job_id="nonexistent")
        assert result.success is False
        assert "unknown job_id" in result.message.lower()

    @pytest.mark.asyncio
    async def test_running_status_detected(self):
        # First call: start job (returns PID)
        # Subsequent calls: pid check returns "running", output read returns lines
        calls = [
            ToolResult(success=True, message="5555\n"),  # launch
            ToolResult(success=True, message="running\n"),  # kill -0 check
            ToolResult(success=True, message="line1\nline2\n"),  # tail output
        ]
        sandbox = SimpleNamespace(exec_command=AsyncMock(side_effect=calls))
        tool = ShellTool(sandbox=sandbox, security_critic=_SafeCritic())

        job_id = (await tool.shell_exec_background(id="s1", exec_dir="/workspace", command="sleep 60")).data["job_id"]
        result = await tool.shell_poll_background(id="s1", job_id=job_id)

        assert result.success is True
        assert result.data["status"] == "running"
        assert "line1" in result.data["output"]

    @pytest.mark.asyncio
    async def test_completed_status_detected(self):
        calls = [
            ToolResult(success=True, message="6666\n"),  # launch
            ToolResult(success=True, message="stopped\n"),  # kill -0 check
            ToolResult(success=True, message="done\n"),  # tail output
        ]
        sandbox = SimpleNamespace(exec_command=AsyncMock(side_effect=calls))
        tool = ShellTool(sandbox=sandbox, security_critic=_SafeCritic())

        job_id = (await tool.shell_exec_background(id="s1", exec_dir="/workspace", command="ls")).data["job_id"]
        result = await tool.shell_poll_background(id="s1", job_id=job_id)

        assert result.success is True
        assert result.data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_tail_lines_capped_at_200(self):
        calls = [
            ToolResult(success=True, message="1\n"),
            ToolResult(success=True, message="running\n"),
            ToolResult(success=True, message="output\n"),
        ]
        sandbox = SimpleNamespace(exec_command=AsyncMock(side_effect=calls))
        tool = ShellTool(sandbox=sandbox, security_critic=_SafeCritic())

        job_id = (await tool.shell_exec_background(id="s1", exec_dir="/workspace", command="ls")).data["job_id"]
        await tool.shell_poll_background(id="s1", job_id=job_id, tail_lines=999)

        # Find the tail call (third exec_command call)
        tail_call_cmd = sandbox.exec_command.call_args_list[2][0][2]
        assert "tail -n 200" in tail_call_cmd

    @pytest.mark.asyncio
    async def test_missing_session_id_rejected(self):
        tool = _tool()
        result = await tool.shell_poll_background(id="", job_id="some-id")
        assert result.success is False
        assert "missing required parameter 'id'" in result.message.lower()

    @pytest.mark.asyncio
    async def test_result_includes_job_id_and_pid_in_message(self):
        calls = [
            ToolResult(success=True, message="8888\n"),
            ToolResult(success=True, message="stopped\n"),
            ToolResult(success=True, message="finished\n"),
        ]
        sandbox = SimpleNamespace(exec_command=AsyncMock(side_effect=calls))
        tool = ShellTool(sandbox=sandbox, security_critic=_SafeCritic())

        job_id = (await tool.shell_exec_background(id="s1", exec_dir="/workspace", command="ls")).data["job_id"]
        result = await tool.shell_poll_background(id="s1", job_id=job_id)

        assert job_id in result.message
        assert "8888" in result.message
