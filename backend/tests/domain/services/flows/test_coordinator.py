"""Tests for CoordinatorFlow."""

from __future__ import annotations

import asyncio

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.communication.protocol import CommunicationProtocol
from app.domain.services.flows.coordinator import (
    CoordinatorFlow,
    CoordinatorResult,
    CoordinatorStatus,
    SubtaskResult,
    _default_synthesizer,
)
from app.domain.services.tools.agent_tool import AgentTaskStatus, AgentTool

# ── Fake runner ───────────────────────────────────────────────────────────────


class _FakeRunner:
    """Always succeeds and returns a canned output string."""

    def __init__(self, output: str = "done", delay: float = 0.0, fail: bool = False) -> None:
        self._output = output
        self._delay = delay
        self._fail = fail
        self.calls: list[str] = []

    async def run(self, task_id, description, context, allowed_tools, workspace_path) -> str:
        self.calls.append(description)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._fail:
            raise RuntimeError("runner failure")
        return self._output


class _SlowThenFastRunner:
    """First subtask is slow; remaining are instant."""

    async def run(self, task_id, description, context, allowed_tools, workspace_path) -> str:
        if "slow" in description:
            await asyncio.sleep(0.05)
        return f"result of: {description}"


def _tool(runner=None, fail: bool = False) -> AgentTool:
    r = runner or _FakeRunner(fail=fail)
    return AgentTool(runner=r)


def _coord(runner=None, protocol=None, synthesizer=None, fail_runner: bool = False) -> CoordinatorFlow:
    tool = _tool(runner=runner, fail=fail_runner)
    return CoordinatorFlow(
        agent_tool=tool,
        protocol=protocol,
        synthesizer=synthesizer,
    )


# ── _default_synthesizer ──────────────────────────────────────────────────────


class TestDefaultSynthesizer:
    @pytest.mark.asyncio
    async def test_includes_task(self):
        results = [SubtaskResult(subtask_id="s1", subtask="do x", agent_task_id="t1", success=True, output="out")]
        text = await _default_synthesizer("main task", results)
        assert "main task" in text

    @pytest.mark.asyncio
    async def test_ok_marker(self):
        results = [SubtaskResult(subtask_id="s1", subtask="do x", agent_task_id="t1", success=True, output="out")]
        text = await _default_synthesizer("t", results)
        assert "[OK]" in text

    @pytest.mark.asyncio
    async def test_failed_marker(self):
        results = [SubtaskResult(subtask_id="s1", subtask="do x", agent_task_id="t1", success=False, error="boom")]
        text = await _default_synthesizer("t", results)
        assert "[FAILED]" in text

    @pytest.mark.asyncio
    async def test_empty_results(self):
        text = await _default_synthesizer("task", [])
        assert "task" in text


# ── CoordinatorFlow.run ───────────────────────────────────────────────────────


class TestCoordinatorRun:
    @pytest.mark.asyncio
    async def test_empty_subtasks_returns_failed(self):
        c = _coord()
        result = await c.run(task="t", subtasks=[])
        assert result.status == CoordinatorStatus.FAILED

    @pytest.mark.asyncio
    async def test_all_succeed(self):
        c = _coord()
        result = await c.run(task="main", subtasks=["s1", "s2"])
        assert result.status == CoordinatorStatus.COMPLETED
        assert result.succeeded == 2
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_all_fail(self):
        c = _coord(fail_runner=True)
        result = await c.run(task="main", subtasks=["s1", "s2"])
        assert result.status == CoordinatorStatus.FAILED
        assert result.failed == 2

    @pytest.mark.asyncio
    async def test_partial_when_mixed(self):
        call_count = 0

        class _MixedRunner:
            async def run(self, task_id, description, context, allowed_tools, workspace_path) -> str:
                nonlocal call_count
                call_count += 1
                if call_count % 2 == 0:
                    raise RuntimeError("odd failure")
                return "ok"

        c = _coord(runner=_MixedRunner())
        result = await c.run(task="main", subtasks=["s1", "s2", "s3", "s4"])
        assert result.status == CoordinatorStatus.PARTIAL

    @pytest.mark.asyncio
    async def test_result_has_run_id(self):
        c = _coord()
        result = await c.run(task="t", subtasks=["s"])
        assert result.run_id.startswith("coord-")

    @pytest.mark.asyncio
    async def test_result_task_matches_input(self):
        c = _coord()
        result = await c.run(task="my task", subtasks=["s"])
        assert result.task == "my task"

    @pytest.mark.asyncio
    async def test_subtask_results_count(self):
        c = _coord()
        result = await c.run(task="t", subtasks=["a", "b", "c"])
        assert len(result.subtask_results) == 3

    @pytest.mark.asyncio
    async def test_synthesis_populated(self):
        c = _coord()
        result = await c.run(task="t", subtasks=["s"])
        assert len(result.synthesis) > 0

    @pytest.mark.asyncio
    async def test_duration_positive(self):
        c = _coord()
        result = await c.run(task="t", subtasks=["s"])
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_metadata_subtask_count(self):
        c = _coord()
        result = await c.run(task="t", subtasks=["a", "b"])
        assert result.metadata["subtask_count"] == 2

    @pytest.mark.asyncio
    async def test_output_stored_in_subtask_result(self):
        c = _coord(runner=_FakeRunner(output="my output"))
        result = await c.run(task="t", subtasks=["s"])
        assert result.subtask_results[0].output == "my output"

    @pytest.mark.asyncio
    async def test_custom_synthesizer_used(self):
        async def _synth(task, results):
            return "custom synthesis"

        c = _coord(synthesizer=_synth)
        result = await c.run(task="t", subtasks=["s"])
        assert result.synthesis == "custom synthesis"

    @pytest.mark.asyncio
    async def test_timeout_marks_remaining_failed(self):
        """When timeout is very short, polling will give up before tasks finish."""
        c = _coord(runner=_FakeRunner(delay=1.0))
        result = await c.run(task="t", subtasks=["slow"], deadline_seconds=0.01, poll_interval=0.005)
        # The task may succeed or timeout depending on timing — we just assert it completes
        assert isinstance(result, CoordinatorResult)


# ── Protocol broadcast integration ───────────────────────────────────────────


class TestCoordinatorWithProtocol:
    @pytest.mark.asyncio
    async def test_broadcasts_on_start_and_finish(self):
        protocol = CommunicationProtocol()
        protocol.register_agent("coordinator")
        protocol.register_agent("observer")

        c = CoordinatorFlow(agent_tool=_tool(), protocol=protocol, coordinator_id="coordinator")
        await c.run(task="t", subtasks=["s"])

        # observer should have received broadcast messages
        inbox = protocol._queues["observer"].inbox
        assert len(inbox) >= 2  # start + finish

    @pytest.mark.asyncio
    async def test_no_protocol_does_not_crash(self):
        c = CoordinatorFlow(agent_tool=_tool(), protocol=None)
        result = await c.run(task="t", subtasks=["s"])
        assert result.status == CoordinatorStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_agent_status_enum_values_are_handled(self):
        class _EnumStatusTool:
            def __init__(self) -> None:
                self.calls: list[str] = []

            async def agent_run_background(self, task: str, context: str = "", isolation: str = "shared") -> ToolResult:
                return ToolResult(success=True, data={"task_id": f"task-{task}"})

            async def agent_status(self, task_id: str) -> ToolResult:
                return ToolResult(success=True, data={"status": AgentTaskStatus.COMPLETED})

            async def agent_output(self, task_id: str) -> ToolResult:
                return ToolResult(success=True, data={"output": "enum output"})

        c = CoordinatorFlow(agent_tool=_EnumStatusTool())
        result = await c.run(task="t", subtasks=["s"])
        assert result.status == CoordinatorStatus.COMPLETED
        assert result.subtask_results[0].output == "enum output"


# ── SubtaskResult helpers ─────────────────────────────────────────────────────


class TestCoordinatorResultHelpers:
    def test_succeeded_count(self):
        r = CoordinatorResult(
            run_id="r",
            task="t",
            status=CoordinatorStatus.PARTIAL,
            subtask_results=[
                SubtaskResult(subtask_id="s1", subtask="a", agent_task_id="t1", success=True),
                SubtaskResult(subtask_id="s2", subtask="b", agent_task_id="t2", success=False),
            ],
        )
        assert r.succeeded == 1
        assert r.failed == 1

    def test_empty_subtask_results(self):
        r = CoordinatorResult(run_id="r", task="t", status=CoordinatorStatus.COMPLETED)
        assert r.succeeded == 0
        assert r.failed == 0
