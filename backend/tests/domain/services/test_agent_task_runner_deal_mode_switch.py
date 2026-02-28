"""Tests for dynamic deal-mode switching in AgentTaskRunner._run_flow."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.event import BaseEvent, ResearchModeEvent
from app.domain.models.message import Message
from app.domain.models.session import AgentMode, ResearchMode
from app.domain.services.agent_task_runner import AgentTaskRunner


class _DummyPlanActFlow:
    def __init__(self, research_mode: str) -> None:
        self.research_mode = research_mode
        self.set_mode_calls = 0

    def set_research_mode(self, research_mode: str) -> None:
        self.research_mode = research_mode
        self.set_mode_calls += 1

    async def run(self, _message: Message) -> AsyncGenerator[BaseEvent, None]:
        yield ResearchModeEvent(research_mode=self.research_mode)


def _build_runner(monkeypatch: pytest.MonkeyPatch, plan_flow: _DummyPlanActFlow, research_mode: ResearchMode) -> AgentTaskRunner:
    monkeypatch.setattr(
        AgentTaskRunner,
        "_init_plan_act_flow",
        lambda self: setattr(self, "_plan_act_flow", plan_flow),
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

    return AgentTaskRunner(
        session_id="session-1",
        agent_id="agent-1",
        user_id="user-1",
        llm=MagicMock(),
        sandbox=AsyncMock(),
        browser=AsyncMock(),
        agent_repository=AsyncMock(),
        session_repository=AsyncMock(),
        json_parser=MagicMock(),
        file_storage=AsyncMock(),
        mcp_repository=AsyncMock(),
        search_engine=MagicMock(),
        mode=AgentMode.AGENT,
        research_mode=research_mode,
    )


@pytest.mark.asyncio
async def test_run_flow_switches_deal_intent_to_deal_finding_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    plan_flow = _DummyPlanActFlow(research_mode=ResearchMode.DEEP_RESEARCH.value)
    runner = _build_runner(monkeypatch, plan_flow, research_mode=ResearchMode.DEEP_RESEARCH)

    events = [event async for event in runner._run_flow(Message(message="Act as a professional deal finder for RTX 5090"))]

    assert runner._research_mode == ResearchMode.DEAL_FINDING
    assert plan_flow.research_mode == ResearchMode.DEAL_FINDING.value
    assert plan_flow.set_mode_calls == 1
    assert any(isinstance(event, ResearchModeEvent) and event.research_mode == "deal_finding" for event in events)


@pytest.mark.asyncio
async def test_run_flow_keeps_non_deal_intent_mode_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    plan_flow = _DummyPlanActFlow(research_mode=ResearchMode.DEEP_RESEARCH.value)
    runner = _build_runner(monkeypatch, plan_flow, research_mode=ResearchMode.DEEP_RESEARCH)

    events = [event async for event in runner._run_flow(Message(message="Summarize the uploaded architecture document."))]

    assert runner._research_mode == ResearchMode.DEEP_RESEARCH
    assert plan_flow.research_mode == ResearchMode.DEEP_RESEARCH.value
    assert plan_flow.set_mode_calls == 0
    assert any(isinstance(event, ResearchModeEvent) and event.research_mode == "deep_research" for event in events)


@pytest.mark.asyncio
async def test_run_flow_does_not_reapply_switch_when_already_deal_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    plan_flow = _DummyPlanActFlow(research_mode=ResearchMode.DEAL_FINDING.value)
    runner = _build_runner(monkeypatch, plan_flow, research_mode=ResearchMode.DEAL_FINDING)

    events = [event async for event in runner._run_flow(Message(message="Find best deals and coupons for laptops"))]

    assert runner._research_mode == ResearchMode.DEAL_FINDING
    assert plan_flow.research_mode == ResearchMode.DEAL_FINDING.value
    assert plan_flow.set_mode_calls == 0
    assert any(isinstance(event, ResearchModeEvent) and event.research_mode == "deal_finding" for event in events)
