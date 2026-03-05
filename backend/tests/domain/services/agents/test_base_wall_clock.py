import itertools
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.event import MessageEvent
from app.domain.services.agents.base import BaseAgent


@pytest.mark.asyncio
async def test_wall_clock_warning_skips_current_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = AsyncMock()
    repo.get_memory = AsyncMock(
        return_value=MagicMock(
            empty=True,
            get_messages=MagicMock(return_value=[]),
            add_message=MagicMock(),
            add_messages=MagicMock(),
        )
    )

    llm = MagicMock()
    llm.model_name = "gpt-4"

    parser = AsyncMock()
    parser.parse = AsyncMock(return_value={})

    tool = MagicMock()
    tool.name = "test_tool"
    tool.get_tools = MagicMock(
        return_value=[
            {
                "type": "function",
                "function": {
                    "name": "file_read",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }
        ]
    )
    tool.has_function = MagicMock(side_effect=lambda name: name == "file_read")
    tool.invoke_function = AsyncMock(return_value=MagicMock(success=True, message="ok", data={}))

    agent = BaseAgent(
        agent_id="agent-wall-clock",
        agent_repository=repo,
        llm=llm,
        json_parser=parser,
        tools=[tool],
    )

    # First model turn asks for a tool call; second turn is the final answer.
    agent.ask = AsyncMock(
        return_value={
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "file_read", "arguments": "{}"},
                }
            ]
        }
    )
    agent.ask_with_messages = AsyncMock(return_value={"content": "wrapped up"})
    agent._add_to_memory = AsyncMock()
    agent._cancel_token.check_cancelled = AsyncMock()

    # Start at t=0, then first loop check sees t=76 => 76% of 100s wall limit.
    # 76% triggers URGENT (>=75%) which blocks read-only tools and requests graceful completion.
    monotonic_values = itertools.chain([0.0, 76.0], itertools.repeat(76.0))
    monkeypatch.setattr("app.domain.services.agents.base.time.monotonic", lambda: next(monotonic_values))
    # Use MagicMock so any accessed attribute returns a sensible default
    mock_settings = MagicMock()
    mock_settings.max_step_wall_clock_seconds = 100.0
    monkeypatch.setattr("app.core.config.get_settings", lambda: mock_settings)

    events = [event async for event in agent.execute("do work")]

    # Pending tool call is skipped when wall-clock threshold is reached.
    tool.invoke_function.assert_not_awaited()
    assert agent._add_to_memory.await_count >= 1  # May get advisory + urgent at 70%
    warning_messages = agent._add_to_memory.await_args.args[0]
    assert warning_messages[0]["role"] == "user"
    assert "STEP TIME URGENT" in warning_messages[0]["content"]  # Graduated: URGENT at >=75%

    # The cycle should request completion guidance instead of executing tools.
    ask_payload = agent.ask_with_messages.await_args.args[0]
    assert any(
        msg.get("role") == "system" and "Approaching execution limit" in msg.get("content", "") for msg in ask_payload
    )

    final_messages = [e for e in events if isinstance(e, MessageEvent)]
    assert len(final_messages) == 1
    assert final_messages[0].message == "wrapped up"


@pytest.mark.asyncio
async def test_wall_clock_fallback_message_is_structured_json(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = AsyncMock()
    repo.get_memory = AsyncMock(
        return_value=MagicMock(
            empty=True,
            get_messages=MagicMock(return_value=[]),
            add_message=MagicMock(),
            add_messages=MagicMock(),
        )
    )

    llm = MagicMock()
    llm.model_name = "gpt-4"

    parser = AsyncMock()
    parser.parse = AsyncMock(return_value={})

    tool = MagicMock()
    tool.name = "test_tool"
    tool.get_tools = MagicMock(
        return_value=[
            {
                "type": "function",
                "function": {
                    "name": "file_read",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }
        ]
    )
    tool.has_function = MagicMock(side_effect=lambda name: name == "file_read")
    tool.invoke_function = AsyncMock(return_value=MagicMock(success=True, message="ok", data={}))

    agent = BaseAgent(
        agent_id="agent-wall-clock-json-fallback",
        agent_repository=repo,
        llm=llm,
        json_parser=parser,
        tools=[tool],
    )
    agent.ask = AsyncMock(
        return_value={
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "file_read", "arguments": "{}"},
                }
            ]
        }
    )
    agent.ask_with_messages = AsyncMock(return_value={"content": None})
    agent._add_to_memory = AsyncMock()
    agent._cancel_token.check_cancelled = AsyncMock()

    # 76% triggers URGENT (>=75%) which blocks tools and requests graceful completion.
    monotonic_values = itertools.chain([0.0, 76.0], itertools.repeat(76.0))
    monkeypatch.setattr("app.domain.services.agents.base.time.monotonic", lambda: next(monotonic_values))
    mock_settings = MagicMock()
    mock_settings.max_step_wall_clock_seconds = 100.0
    monkeypatch.setattr("app.core.config.get_settings", lambda: mock_settings)

    events = [event async for event in agent.execute("do work")]
    final_messages = [event for event in events if isinstance(event, MessageEvent)]
    assert len(final_messages) == 1

    payload = json.loads(final_messages[0].message)
    assert payload["success"] is False
    assert payload["result"] is None
    assert "error" in payload
