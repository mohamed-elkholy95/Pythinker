"""Tests for LeadAgentRuntime wiring inside AgentTaskRunner."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import DoneEvent, MessageEvent, WaitEvent
from app.domain.models.message import Message
from app.domain.models.session import AgentMode, ResearchMode
from app.domain.services.agent_task_runner import AgentTaskRunner
from app.domain.services.runtime.middleware import RuntimeContext


class _FlowStub:
    def __init__(self, *events: object) -> None:
        self._events = events
        self.called = False
        self.cancel_token = None

    def set_cancel_token(self, cancel_token: object) -> None:
        self.cancel_token = cancel_token

    async def run(self, _message: Message) -> AsyncGenerator[object, None]:
        self.called = True
        for event in self._events:
            yield event


def _build_runner(monkeypatch: pytest.MonkeyPatch, flow: _FlowStub) -> AgentTaskRunner:
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
    sandbox.ensure_sandbox = AsyncMock(return_value=None)

    return AgentTaskRunner(
        session_id="session-rt",
        agent_id="agent-rt",
        user_id="user-rt",
        llm=MagicMock(model="test-model", model_name="test-model"),
        sandbox=sandbox,
        browser=AsyncMock(),
        agent_repository=AsyncMock(),
        session_repository=AsyncMock(),
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(get_mcp_config=AsyncMock(return_value=SimpleNamespace(mcp_servers={}))),
        search_engine=AsyncMock(),
        mode=AgentMode.AGENT,
        research_mode=ResearchMode.DEEP_RESEARCH,
    )


@patch("app.core.config.get_settings")
@pytest.mark.asyncio
async def test_run_initializes_and_finalizes_runtime(
    mock_settings: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AgentTaskRunner.run() must drive the LeadAgentRuntime lifecycle."""
    mock_settings.return_value = MagicMock(default_language="English", screenshot_capture_enabled=False)
    runner = _build_runner(monkeypatch, _FlowStub(DoneEvent()))
    runner._mcp_tool.initialized = AsyncMock(return_value=None)
    runner._sync_message_attachments_to_sandbox = AsyncMock(return_value=None)
    runner._put_and_add_event = AsyncMock()
    runner._session_repository.update_status = AsyncMock()
    runner._session_repository.update_title = AsyncMock()
    runner._session_repository.update_latest_message = AsyncMock()
    runner._session_repository.increment_unread_message_count = AsyncMock()

    runtime_ctx = RuntimeContext(session_id=runner.session_id, agent_id="agent-rt")
    runtime = SimpleNamespace(
        context=None,
        finalize=AsyncMock(return_value=runtime_ctx),
        before_step=AsyncMock(return_value=runtime_ctx),
        after_step=AsyncMock(return_value=runtime_ctx),
        before_tool=AsyncMock(return_value=runtime_ctx),
        after_tool=AsyncMock(return_value=runtime_ctx),
    )

    async def _initialize_runtime() -> RuntimeContext:
        runtime.context = runtime_ctx
        return runtime_ctx

    runtime.initialize = AsyncMock(side_effect=_initialize_runtime)
    runner._lead_agent_runtime = runtime

    task = SimpleNamespace(
        id="task-id",
        input_stream=SimpleNamespace(is_empty=AsyncMock(side_effect=[False, True, True])),
        paused=False,
    )
    runner._pop_event = AsyncMock(return_value=MessageEvent(message="do work", role="user"))

    await runner.run(task)
    await runner.destroy()

    runner._lead_agent_runtime.initialize.assert_awaited_once()
    runner._lead_agent_runtime.finalize.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_flow_emits_clarification_and_skips_underlying_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A clarification request from the runtime should pause execution before the flow runs."""
    flow = _FlowStub(MessageEvent(message="should not run", role="assistant"))
    runner = _build_runner(monkeypatch, flow)

    clarification_ctx = RuntimeContext(session_id="session-rt", agent_id="agent-rt")
    clarification_ctx.metadata["awaiting_clarification"] = True
    clarification_ctx.events.append(
        {
            "type": "clarification",
            "formatted": "[?] Which environment should I target?",
        }
    )
    runner._lead_agent_runtime = SimpleNamespace(
        context=clarification_ctx,
        before_step=AsyncMock(return_value=clarification_ctx),
        after_step=AsyncMock(return_value=clarification_ctx),
        before_tool=AsyncMock(return_value=clarification_ctx),
        after_tool=AsyncMock(return_value=clarification_ctx),
    )

    events = [event async for event in runner._run_flow(Message(message="Deploy this change"))]

    assert any(isinstance(event, MessageEvent) for event in events)
    assert any(isinstance(event, WaitEvent) for event in events)
    assert flow.called is False
    runner._lead_agent_runtime.after_step.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_flow_populates_runtime_metadata_and_runs_after_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime metadata should receive the user request and final textual output."""
    flow = _FlowStub(MessageEvent(message="Paris is the capital of France.", role="assistant"))
    runner = _build_runner(monkeypatch, flow)

    runtime_ctx = RuntimeContext(session_id="session-rt", agent_id="agent-rt")
    runner._lead_agent_runtime = SimpleNamespace(
        context=runtime_ctx,
        before_step=AsyncMock(return_value=runtime_ctx),
        after_step=AsyncMock(return_value=runtime_ctx),
        before_tool=AsyncMock(return_value=runtime_ctx),
        after_tool=AsyncMock(return_value=runtime_ctx),
    )

    events = [event async for event in runner._run_flow(Message(message="What is the capital of France?"))]

    assert len(events) == 1
    assert runtime_ctx.metadata["user_request"] == "What is the capital of France?"
    assert runtime_ctx.metadata["step_output"] == "Paris is the capital of France."
    runner._lead_agent_runtime.before_step.assert_awaited_once()
    runner._lead_agent_runtime.after_step.assert_awaited_once()
