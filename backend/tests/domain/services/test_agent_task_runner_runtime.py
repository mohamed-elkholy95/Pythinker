"""Tests for AgentTaskRunner integration with LeadAgentRuntime."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.event import MessageEvent, ToolEvent, ToolStatus, WaitEvent
from app.domain.models.message import Message
from app.domain.models.session import AgentMode, ResearchMode
from app.domain.models.tool_result import ToolResult
from app.domain.services.agent_task_runner import AgentTaskRunner


class _FlowWithExecutor:
    def __init__(self, *events) -> None:
        self._events = list(events)
        self.executor = MagicMock()
        self.executor._build_source_context.return_value = ["Grounding context"]
        self._task_state_manager = MagicMock()
        self._task_state_manager._file_path = "/home/ubuntu/task_state.md"

    async def run(self, _message: Message) -> AsyncGenerator[object, None]:
        for event in self._events:
            yield event


def _build_runner(monkeypatch: pytest.MonkeyPatch, flow: _FlowWithExecutor) -> AgentTaskRunner:
    monkeypatch.setattr(
        AgentTaskRunner,
        "_init_plan_act_flow",
        lambda self: setattr(self, "_plan_act_flow", flow),
    )
    monkeypatch.setattr(
        AgentTaskRunner,
        "_init_coordinator_flow",
        lambda self: setattr(self, "_coordinator_flow", MagicMock()),
    )
    monkeypatch.setattr(
        AgentTaskRunner,
        "_init_discuss_flow",
        lambda self: setattr(self, "_discuss_flow", MagicMock()),
    )
    monkeypatch.setattr(
        AgentTaskRunner,
        "_init_fast_search_flow",
        lambda self: setattr(self, "_fast_search_flow", MagicMock()),
    )

    sandbox = AsyncMock()
    sandbox.cdp_url = "http://localhost:9222"

    return AgentTaskRunner(
        session_id="session-rt",
        agent_id="agent-rt",
        user_id="user-rt",
        llm=MagicMock(),
        sandbox=sandbox,
        browser=AsyncMock(),
        agent_repository=AsyncMock(),
        session_repository=AsyncMock(),
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(get_mcp_config=AsyncMock(return_value={})),
        search_engine=AsyncMock(),
        mode=AgentMode.AGENT,
        research_mode=ResearchMode.DEEP_RESEARCH,
    )


@pytest.mark.asyncio
async def test_initialize_runs_runtime_and_rebinds_task_state_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = _FlowWithExecutor()
    runner = _build_runner(monkeypatch, flow)
    runtime = AsyncMock()
    runtime.context = None
    runtime.initialize.return_value = MagicMock(
        metadata={
            "workspace_contract": MagicMock(task_state_path="/home/ubuntu/session-rt/task_state.md"),
        }
    )
    runner._lead_agent_runtime = runtime

    await runner.initialize()

    runtime.initialize.assert_awaited_once()
    assert flow._task_state_manager._file_path == "/home/ubuntu/session-rt/task_state.md"


@pytest.mark.asyncio
async def test_run_flow_calls_runtime_step_hooks_with_output_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = _FlowWithExecutor(MessageEvent(message="Final answer"))
    runner = _build_runner(monkeypatch, flow)
    runtime_context = MagicMock()
    runtime_context.metadata = {"new_insights": []}
    runtime_context.events = []
    runtime = AsyncMock()
    runtime.context = runtime_context
    runtime.before_step.return_value = runtime_context
    runtime.after_step.return_value = runtime_context
    runner._lead_agent_runtime = runtime

    events = [event async for event in runner._run_flow(Message(message="Explain the fix"))]

    assert len(events) == 1
    runtime.before_step.assert_awaited_once()
    runtime.after_step.assert_awaited_once()
    assert runtime_context.metadata["user_request"] == "Explain the fix"
    assert runtime_context.metadata["step_output"] == "Final answer"
    assert runtime_context.metadata["source_context"] == ["Grounding context"]


@pytest.mark.asyncio
async def test_handle_tool_event_dispatches_runtime_tool_hooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _build_runner(monkeypatch, _FlowWithExecutor())
    runtime_context = MagicMock()
    runtime_context.metadata = {}
    runtime_context.events = []
    runtime = AsyncMock()
    runtime.context = runtime_context
    runtime.before_tool.return_value = runtime_context
    runtime.after_tool.return_value = runtime_context
    runner._lead_agent_runtime = runtime

    calling = ToolEvent(
        tool_call_id="call-1",
        tool_name="search",
        function_name="search",
        function_args={"query": "python"},
        status=ToolStatus.CALLING,
    )
    called = ToolEvent(
        tool_call_id="call-1",
        tool_name="search",
        function_name="search",
        function_args={"query": "python"},
        status=ToolStatus.CALLED,
        function_result=ToolResult(success=True, message="done"),
    )

    await runner._handle_tool_event(calling)
    await runner._handle_tool_event(called)

    runtime.before_tool.assert_awaited_once()
    runtime.after_tool.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_flow_surfaces_runtime_clarification_without_entering_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = _FlowWithExecutor(MessageEvent(message="should not run"))
    flow.run = AsyncMock()
    runner = _build_runner(monkeypatch, flow)
    runtime_context = MagicMock()
    runtime_context.metadata = {}
    runtime_context.events = []
    runtime = AsyncMock()
    runtime.context = runtime_context

    async def _before_step(ctx):
        ctx.metadata["awaiting_clarification"] = True
        ctx.events.append(
            {
                "type": "clarification",
                "formatted": "[?] Which option should I use?",
            }
        )
        return ctx

    runtime.before_step.side_effect = _before_step
    runner._lead_agent_runtime = runtime

    events = [event async for event in runner._run_flow(Message(message="Ambiguous task"))]

    assert isinstance(events[0], MessageEvent)
    assert events[0].message == "[?] Which option should I use?"
    assert isinstance(events[1], WaitEvent)
    flow.run.assert_not_called()
