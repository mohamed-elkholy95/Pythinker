# backend/tests/domain/services/agents/test_base_format_enforcement.py
"""Tests for JSON format re-enforcement after the tool-calling loop completes.

When BaseAgent.execute() is invoked with format="json_object" and tools are
present, the while-loop intentionally runs without format enforcement to avoid
empty-response bugs with some LLM providers.  Once the loop exits the agent
must check whether the final message is valid JSON and, if not, make one more
ask_with_messages() call that passes format="json_object" explicitly.
"""

import json
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.domain.models.event import MessageEvent
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.base import BaseAgent


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo():
    r = AsyncMock()
    r.get_memory = AsyncMock(
        return_value=MagicMock(
            empty=True,
            get_messages=MagicMock(return_value=[]),
            add_message=MagicMock(),
            add_messages=MagicMock(),
        )
    )
    return r


@pytest.fixture
def llm():
    m = MagicMock()
    m.model_name = "gpt-4"
    return m


@pytest.fixture
def parser():
    p = AsyncMock()
    p.parse = AsyncMock(return_value={})
    return p


@pytest.fixture
def tool_registry():
    """A single tool registry that exposes one function: do_work."""
    t = MagicMock()
    t.name = "work_tool"
    t.get_tools = MagicMock(
        return_value=[
            {
                "type": "function",
                "function": {
                    "name": "do_work",
                    "description": "Does some work",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }
        ]
    )
    t.has_function = MagicMock(side_effect=lambda name: name == "do_work")
    t.invoke_function = AsyncMock(return_value=ToolResult.ok(message="work done"))
    return t


def _make_agent(repo, llm, parser, tool_registry, format_value="json_object"):
    agent = BaseAgent(
        agent_id="test-format-enforcement",
        agent_repository=repo,
        llm=llm,
        json_parser=parser,
        tools=[tool_registry],
    )
    agent.format = format_value
    # Prevent real memory / token-limit I/O
    agent._add_to_memory = AsyncMock()
    agent._cancel_token.check_cancelled = AsyncMock()
    return agent


# ---------------------------------------------------------------------------
# Helper to collect all events from execute()
# ---------------------------------------------------------------------------


async def _collect(gen):
    return [event async for event in gen]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestJsonFormatReEnforcement:
    """JSON format re-enforcement after the tool-calling while-loop."""

    @pytest.mark.asyncio
    async def test_non_json_response_triggers_re_enforcement(self, repo, llm, parser, tool_registry):
        """When the post-loop message is free-form text, a second ask with
        format='json_object' must be made and its result used as the final
        MessageEvent content."""
        agent = _make_agent(repo, llm, parser, tool_registry)

        valid_json = json.dumps({"success": True, "result": "done"})

        # Round 1: agent asks for a tool call
        agent.ask = AsyncMock(
            return_value={
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "do_work", "arguments": "{}"},
                    }
                ]
            }
        )

        # Round 2 (after tool result): returns free-form text — not valid JSON
        # Round 3 (re-enforcement call): returns proper JSON
        agent.ask_with_messages = AsyncMock(
            side_effect=[
                {"content": "Here is what I found: the task is done."},  # non-JSON
                {"content": valid_json},  # re-enforced JSON
            ]
        )

        events = await _collect(agent.execute("do the work"))

        message_events = [e for e in events if isinstance(e, MessageEvent)]
        assert len(message_events) == 1
        # Final content must be the JSON-enforced response, not the free-form text
        assert message_events[0].message == valid_json
        # Verify the re-enforcement call passed format="json_object"
        enforcement_call = agent.ask_with_messages.call_args_list[1]
        assert enforcement_call == call(
            [
                {
                    "role": "user",
                    "content": (
                        "Your previous response was not in the required JSON format. "
                        "Restate your response as ONLY a valid JSON object matching the "
                        "expected schema. No prose, no markdown fencing."
                    ),
                }
            ],
            format="json_object",
        )

    @pytest.mark.asyncio
    async def test_valid_json_response_skips_re_enforcement(self, repo, llm, parser, tool_registry):
        """When the post-loop message is already valid JSON, no extra LLM call
        should be made."""
        agent = _make_agent(repo, llm, parser, tool_registry)

        valid_json = json.dumps({"success": True, "result": "all good"})

        agent.ask = AsyncMock(
            return_value={
                "tool_calls": [
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {"name": "do_work", "arguments": "{}"},
                    }
                ]
            }
        )

        # Post-loop response is already valid JSON — only one ask_with_messages call expected
        agent.ask_with_messages = AsyncMock(return_value={"content": valid_json})

        events = await _collect(agent.execute("do the work"))

        message_events = [e for e in events if isinstance(e, MessageEvent)]
        assert len(message_events) == 1
        assert message_events[0].message == valid_json
        # Exactly one call: the tool-result call; no re-enforcement call
        assert agent.ask_with_messages.await_count == 1

    @pytest.mark.asyncio
    async def test_empty_response_triggers_re_enforcement(self, repo, llm, parser, tool_registry):
        """An empty content string after the loop should also trigger
        re-enforcement rather than falling through to the generic fallback."""
        agent = _make_agent(repo, llm, parser, tool_registry)

        valid_json = json.dumps({"success": True, "result": "recovered"})

        agent.ask = AsyncMock(
            return_value={
                "tool_calls": [
                    {
                        "id": "call_3",
                        "type": "function",
                        "function": {"name": "do_work", "arguments": "{}"},
                    }
                ]
            }
        )

        agent.ask_with_messages = AsyncMock(
            side_effect=[
                {"content": ""},  # empty — should trigger re-enforcement
                {"content": valid_json},
            ]
        )

        events = await _collect(agent.execute("do the work"))

        message_events = [e for e in events if isinstance(e, MessageEvent)]
        assert len(message_events) == 1
        assert message_events[0].message == valid_json
        assert agent.ask_with_messages.await_count == 2

    @pytest.mark.asyncio
    async def test_no_re_enforcement_when_format_is_none(self, repo, llm, parser, tool_registry):
        """When the agent's format is not 'json_object' the re-enforcement
        block must not fire — the free-form text is acceptable."""
        agent = _make_agent(repo, llm, parser, tool_registry, format_value=None)

        agent.ask = AsyncMock(
            return_value={
                "tool_calls": [
                    {
                        "id": "call_4",
                        "type": "function",
                        "function": {"name": "do_work", "arguments": "{}"},
                    }
                ]
            }
        )

        free_text = "Task complete. Here is a summary."
        agent.ask_with_messages = AsyncMock(return_value={"content": free_text})

        events = await _collect(agent.execute("do the work"))

        message_events = [e for e in events if isinstance(e, MessageEvent)]
        assert len(message_events) == 1
        assert message_events[0].message == free_text
        # Only the tool-result call — no re-enforcement
        assert agent.ask_with_messages.await_count == 1

    @pytest.mark.asyncio
    async def test_no_re_enforcement_when_no_tools(self, repo, llm, parser):
        """Without tools has_tools is False, so the re-enforcement block
        should never be entered regardless of format."""
        # Build agent without any tool registry
        agent = BaseAgent(
            agent_id="test-no-tools",
            agent_repository=repo,
            llm=llm,
            json_parser=parser,
            tools=[],
        )
        agent.format = "json_object"
        agent._add_to_memory = AsyncMock()
        agent._cancel_token.check_cancelled = AsyncMock()

        free_text = "plain prose answer"
        # With no tools, ask() returns a final answer directly (no tool_calls key)
        agent.ask = AsyncMock(return_value={"content": free_text})
        agent.ask_with_messages = AsyncMock()

        events = await _collect(agent.execute("answer me"))

        message_events = [e for e in events if isinstance(e, MessageEvent)]
        assert len(message_events) == 1
        assert message_events[0].message == free_text
        # ask_with_messages should never be called when there are no tools
        agent.ask_with_messages.assert_not_awaited()
