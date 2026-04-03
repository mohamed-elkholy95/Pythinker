"""Tests for AgentTaskRunner integration with LeadAgentRuntime."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.domain.utils.markdown_to_pdf as markdown_to_pdf
from app.domain.models.event import MessageEvent, ReportEvent, ToolEvent, ToolStatus, WaitEvent
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
async def test_handle_tool_event_treats_result_retrieval_as_known_utility(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    runner = _build_runner(monkeypatch, _FlowWithExecutor())
    event = ToolEvent(
        tool_call_id="call-1",
        tool_name="result_retrieval",
        function_name="retrieve_result",
        function_args={"result_id": "trs-123"},
        status=ToolStatus.CALLED,
    )

    with caplog.at_level(logging.WARNING):
        await runner._handle_tool_event(event)

    assert "received unknown tool event: result_retrieval" not in caplog.text


@pytest.mark.asyncio
async def test_ensure_report_file_uses_full_pre_trim_report_for_canonical_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = _FlowWithExecutor()
    flow.executor._pre_trim_report_cache = (
        "# Full report\n\n## Introduction\nThis is the complete report body that should survive summarization.\n"
    )
    runner = _build_runner(monkeypatch, flow)
    runner._sandbox.file_write = AsyncMock(return_value=SimpleNamespace(success=True))
    runner._file_storage.upload_file = AsyncMock(return_value=SimpleNamespace(file_id="pdf-1"))
    runner._session_repository.add_file = AsyncMock(return_value=None)
    runner._resolve_chart_generation_mode = lambda: "skip"

    event = ReportEvent(
        id="abc123",
        title="Comprehensive Report",
        content="# Short report\n\nThis version was trimmed.",
    )

    captured_pdf_content: dict[str, str] = {}

    def _fake_build_pdf_bytes(*, title: str, content: str, **kwargs):
        captured_pdf_content["title"] = title
        captured_pdf_content["content"] = content
        return b"pdf-bytes"

    monkeypatch.setattr(markdown_to_pdf, "build_pdf_bytes", _fake_build_pdf_bytes)

    await runner._ensure_report_file(event)

    canonical_call = next(
        call for call in runner._sandbox.file_write.await_args_list if call.kwargs["file"].endswith("report-abc123.md")
    )
    assert canonical_call.kwargs["content"] == flow.executor._pre_trim_report_cache
    assert event.content == flow.executor._pre_trim_report_cache.rstrip()
    assert captured_pdf_content["content"] == flow.executor._pre_trim_report_cache.rstrip()
    assert event.attachments is not None
    assert any(attachment.filename == "report-abc123.md" for attachment in event.attachments)


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
