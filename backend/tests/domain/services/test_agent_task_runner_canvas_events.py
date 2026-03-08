"""Tests for canvas update event emission from AgentTaskRunner."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.event import CanvasUpdateEvent, ToolEvent, ToolStatus
from app.domain.models.message import Message
from app.domain.models.session import AgentMode, ResearchMode
from app.domain.models.tool_result import ToolResult
from app.domain.services.agent_task_runner import AgentTaskRunner


class _CanvasFlow:
    def __init__(self, *events: ToolEvent) -> None:
        self._events = events

    async def run(self, _message: Message) -> AsyncGenerator[ToolEvent, None]:
        for event in self._events:
            yield event


def _build_runner(monkeypatch: pytest.MonkeyPatch, flow: _CanvasFlow) -> AgentTaskRunner:
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
        session_id="session-123",
        agent_id="agent-123",
        user_id="user-123",
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


def _canvas_called_event(
    *,
    function_name: str,
    function_args: dict[str, object],
    data: dict[str, object],
    success: bool = True,
) -> ToolEvent:
    return ToolEvent(
        tool_call_id="tool-call-1",
        tool_name="canvas",
        function_name=function_name,
        function_args=function_args,
        status=ToolStatus.CALLED,
        function_result=ToolResult(success=success, data=data),
    )


@pytest.mark.asyncio
async def test_run_flow_emits_canvas_update_for_successful_canvas_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_event = _canvas_called_event(
        function_name="canvas_add_element",
        function_args={"project_id": "project-123"},
        data={
            "project_id": "project-123",
            "project_name": "Launch Poster",
            "version": 7,
            "element_count": 3,
            "changed_element_ids": ["element-1"],
        },
    )
    runner = _build_runner(monkeypatch, _CanvasFlow(tool_event))

    events = [event async for event in runner._run_flow(Message(message="Add a title block"))]

    assert len(events) == 2
    assert events[0] is tool_event
    assert isinstance(events[1], CanvasUpdateEvent)
    assert events[1].project_id == "project-123"
    assert events[1].session_id == "session-123"
    assert events[1].operation == "add_element"
    assert events[1].project_name == "Launch Poster"
    assert events[1].element_count == 3
    assert events[1].version == 7
    assert events[1].changed_element_ids == ["element-1"]
    assert events[1].source == "agent"


@pytest.mark.asyncio
async def test_run_flow_does_not_emit_canvas_update_for_non_mutating_canvas_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_event = _canvas_called_event(
        function_name="canvas_get_state",
        function_args={"project_id": "project-123"},
        data={
            "project_id": "project-123",
            "project_name": "Launch Poster",
            "version": 7,
            "elements": [{"id": "element-1"}],
        },
    )
    runner = _build_runner(monkeypatch, _CanvasFlow(tool_event))

    events = [event async for event in runner._run_flow(Message(message="Inspect the current canvas"))]

    assert events == [tool_event]
