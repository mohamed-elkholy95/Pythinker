"""Tests for AgentTaskRunner._pop_event behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain.models.event import MessageEvent
from app.domain.services.agent_task_runner import AgentTaskRunner


@pytest.mark.asyncio
async def test_pop_event_returns_none_for_empty_payload() -> None:
    runner = AgentTaskRunner.__new__(AgentTaskRunner)
    runner._agent_id = "agent-test"
    task = SimpleNamespace(input_stream=SimpleNamespace(pop=AsyncMock(return_value=("1-0", None))))

    event = await AgentTaskRunner._pop_event(runner, task)

    assert event is None


@pytest.mark.asyncio
async def test_pop_event_parses_and_assigns_event_id() -> None:
    runner = AgentTaskRunner.__new__(AgentTaskRunner)
    runner._agent_id = "agent-test"
    payload = MessageEvent(message="hello", role="assistant").model_dump_json()
    task = SimpleNamespace(input_stream=SimpleNamespace(pop=AsyncMock(return_value=("9-0", payload))))

    event = await AgentTaskRunner._pop_event(runner, task)

    assert event is not None
    assert event.id == "9-0"
