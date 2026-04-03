"""Tests for AgentTool — subagent lifecycle management."""

from __future__ import annotations

import asyncio

import pytest

from app.domain.services.tools.agent_tool import (
    WORKSPACE_ALLOWED_TOOLS,
    AgentTaskStatus,
    AgentTool,
    IsolationMode,
    _allowed_tools_for,
)

# ── Stub runner ───────────────────────────────────────────────────────────────


class _OkRunner:
    """Returns a fixed output string."""

    def __init__(self, output: str = "task done") -> None:
        self.output = output
        self.calls: list[dict] = []

    async def run(self, task_id, description, context, allowed_tools, workspace_path):
        self.calls.append(
            {
                "task_id": task_id,
                "description": description,
                "context": context,
                "allowed_tools": allowed_tools,
                "workspace_path": workspace_path,
            }
        )
        return self.output


class _FailRunner:
    async def run(self, **_):
        raise RuntimeError("runner exploded")


class _SlowRunner:
    """Sleeps forever (useful for testing cancellation)."""

    async def run(self, **_):
        await asyncio.sleep(9999)
        return "never"


# ── IsolationMode / allowlists ────────────────────────────────────────────────


class TestIsolationMode:
    def test_shared_allows_all(self):
        assert _allowed_tools_for(IsolationMode.SHARED) == frozenset()

    def test_workspace_restricts_to_known_set(self):
        allowed = _allowed_tools_for(IsolationMode.WORKSPACE)
        assert "file_read" in allowed
        assert "shell_exec" in allowed
        assert "web_search" in allowed
        # Should NOT contain browser or spawn tools
        assert "browser_navigate" not in allowed
        assert "agent_run" not in allowed
        assert "spawn_background_task" not in allowed

    def test_workspace_allowed_tools_constant_nonempty(self):
        assert len(WORKSPACE_ALLOWED_TOOLS) > 0


# ── agent_run ─────────────────────────────────────────────────────────────────


class TestAgentRun:
    @pytest.mark.asyncio
    async def test_run_returns_output(self):
        tool = AgentTool(runner=_OkRunner("hello from agent"))
        result = await tool.agent_run(task="do something")
        assert result.success is True
        assert "hello from agent" in result.message

    @pytest.mark.asyncio
    async def test_run_empty_task_rejected(self):
        tool = AgentTool(runner=_OkRunner())
        result = await tool.agent_run(task="")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_run_no_runner_returns_error(self):
        tool = AgentTool(runner=None)
        result = await tool.agent_run(task="do something")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_run_propagates_context(self):
        runner = _OkRunner()
        tool = AgentTool(runner=runner)
        await tool.agent_run(task="do something", context="extra ctx")
        assert runner.calls[0]["context"] == "extra ctx"

    @pytest.mark.asyncio
    async def test_run_shared_isolation_passes_empty_allowlist(self):
        runner = _OkRunner()
        tool = AgentTool(runner=runner)
        await tool.agent_run(task="x", isolation="shared")
        assert runner.calls[0]["allowed_tools"] == frozenset()

    @pytest.mark.asyncio
    async def test_run_workspace_isolation_passes_restricted_allowlist(self):
        runner = _OkRunner()
        tool = AgentTool(runner=runner)
        await tool.agent_run(task="x", isolation="workspace")
        assert "file_read" in runner.calls[0]["allowed_tools"]

    @pytest.mark.asyncio
    async def test_run_workspace_sets_workspace_path(self):
        runner = _OkRunner()
        tool = AgentTool(runner=runner, workspace_root="/ws")
        await tool.agent_run(task="x", isolation="workspace")
        task_id = runner.calls[0]["task_id"]
        assert runner.calls[0]["workspace_path"] == f"/ws/agent_{task_id}"

    @pytest.mark.asyncio
    async def test_run_shared_workspace_path_is_none(self):
        runner = _OkRunner()
        tool = AgentTool(runner=runner)
        await tool.agent_run(task="x", isolation="shared")
        assert runner.calls[0]["workspace_path"] is None

    @pytest.mark.asyncio
    async def test_run_invalid_isolation_falls_back_to_shared(self):
        runner = _OkRunner()
        tool = AgentTool(runner=runner)
        result = await tool.agent_run(task="x", isolation="invalid_mode")
        assert result.success is True
        assert runner.calls[0]["allowed_tools"] == frozenset()

    @pytest.mark.asyncio
    async def test_run_failure_returns_error(self):
        tool = AgentTool(runner=_FailRunner())
        result = await tool.agent_run(task="do something")
        assert result.success is False
        assert "runner exploded" in result.message

    @pytest.mark.asyncio
    async def test_run_task_stored_after_completion(self):
        tool = AgentTool(runner=_OkRunner())
        result = await tool.agent_run(task="do something")
        task_id = result.data["task_id"]
        assert task_id in tool._tasks
        assert tool._tasks[task_id].status == AgentTaskStatus.COMPLETED


# ── agent_run_background ──────────────────────────────────────────────────────


class TestAgentRunBackground:
    @pytest.mark.asyncio
    async def test_returns_task_id_immediately(self):
        tool = AgentTool(runner=_SlowRunner())
        result = await tool.agent_run_background(task="long task")
        assert result.success is True
        assert result.data["task_id"].startswith("agt-")

    @pytest.mark.asyncio
    async def test_empty_task_rejected(self):
        tool = AgentTool(runner=_OkRunner())
        result = await tool.agent_run_background(task="  ")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_no_runner_returns_error(self):
        tool = AgentTool(runner=None)
        result = await tool.agent_run_background(task="x")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_task_registered_as_pending(self):
        tool = AgentTool(runner=_SlowRunner())
        result = await tool.agent_run_background(task="long task")
        task_id = result.data["task_id"]
        assert task_id in tool._tasks

    @pytest.mark.asyncio
    async def test_task_completes_eventually(self):
        tool = AgentTool(runner=_OkRunner("done"))
        result = await tool.agent_run_background(task="quick task")
        task_id = result.data["task_id"]
        # Let the event loop drive the background task to completion
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert tool._tasks[task_id].status == AgentTaskStatus.COMPLETED


# ── agent_status ──────────────────────────────────────────────────────────────


class TestAgentStatus:
    @pytest.mark.asyncio
    async def test_unknown_task_id(self):
        tool = AgentTool()
        result = await tool.agent_status(task_id="nonexistent")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_status_of_known_task(self):
        tool = AgentTool(runner=_SlowRunner())
        bg = await tool.agent_run_background(task="x")
        task_id = bg.data["task_id"]

        status_result = await tool.agent_status(task_id=task_id)
        assert status_result.success is True
        assert task_id in status_result.message

    @pytest.mark.asyncio
    async def test_completed_task_status(self):
        tool = AgentTool(runner=_OkRunner())
        run_result = await tool.agent_run(task="x")
        task_id = run_result.data["task_id"]

        status = await tool.agent_status(task_id=task_id)
        assert status.data["status"] == AgentTaskStatus.COMPLETED


# ── agent_stop ────────────────────────────────────────────────────────────────


class TestAgentStop:
    @pytest.mark.asyncio
    async def test_stop_unknown_task(self):
        tool = AgentTool()
        result = await tool.agent_stop(task_id="nonexistent")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_stop_running_task(self):
        tool = AgentTool(runner=_SlowRunner())
        bg = await tool.agent_run_background(task="slow task")
        task_id = bg.data["task_id"]
        await asyncio.sleep(0)  # let it start

        stop_result = await tool.agent_stop(task_id=task_id)
        assert stop_result.success is True
        assert tool._tasks[task_id].status == AgentTaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_stop_already_completed_task(self):
        tool = AgentTool(runner=_OkRunner())
        run = await tool.agent_run(task="x")
        task_id = run.data["task_id"]

        stop = await tool.agent_stop(task_id=task_id)
        assert stop.success is True
        assert "terminal state" in stop.message


# ── agent_output ──────────────────────────────────────────────────────────────


class TestAgentOutput:
    @pytest.mark.asyncio
    async def test_output_unknown_task(self):
        tool = AgentTool()
        result = await tool.agent_output(task_id="nonexistent")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_output_completed_task(self):
        tool = AgentTool(runner=_OkRunner("the answer"))
        run = await tool.agent_run(task="x")
        task_id = run.data["task_id"]

        out = await tool.agent_output(task_id=task_id)
        assert out.success is True
        assert "the answer" in out.message
        assert out.data["output"] == "the answer"

    @pytest.mark.asyncio
    async def test_output_failed_task(self):
        tool = AgentTool(runner=_FailRunner())
        run = await tool.agent_run(task="x")
        task_id = run.data["task_id"]
        # Force failed status for retrieval test
        tool._tasks[task_id].status = AgentTaskStatus.FAILED
        tool._tasks[task_id].error = "something went wrong"

        out = await tool.agent_output(task_id=task_id)
        assert out.success is False
        assert "something went wrong" in out.message

    @pytest.mark.asyncio
    async def test_output_still_running(self):
        tool = AgentTool(runner=_SlowRunner())
        bg = await tool.agent_run_background(task="slow")
        task_id = bg.data["task_id"]
        await asyncio.sleep(0)

        # Manually set to running state for clarity
        if tool._tasks[task_id].status == AgentTaskStatus.PENDING:
            tool._tasks[task_id].status = AgentTaskStatus.RUNNING

        out = await tool.agent_output(task_id=task_id)
        # Should indicate still running (success=True but output=None)
        assert out.data.get("output") is None

        # Cleanup
        await tool.agent_stop(task_id=task_id)
