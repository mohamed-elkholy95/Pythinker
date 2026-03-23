# backend/tests/domain/services/agents/test_base_format_enforcement.py
"""Tests for JSON format re-enforcement after the tool-calling loop completes.

When BaseAgent.execute() is invoked with format="json_object" and tools are
present, the while-loop intentionally runs without format enforcement to avoid
empty-response bugs with some LLM providers.  Once the loop exits the agent
must check whether the final message is valid JSON and, if not, make one more
ask_with_messages() call that passes format="json_object" explicitly.
"""

import json
from unittest.mock import AsyncMock, MagicMock

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
    async def test_non_json_response_wrapped_directly(self, repo, llm, parser, tool_registry):
        """When the post-loop message is free-form prose (not JSON), it should
        be wrapped directly as JSON without an extra LLM re-enforcement call.
        This avoids costly recovery round-trips for providers that don't
        handle json_object format well (e.g. GLM-class models)."""
        agent = _make_agent(repo, llm, parser, tool_registry)

        prose_text = "Here is what I found: the task is done."

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

        # Post-loop: returns free-form text — not valid JSON
        agent.ask_with_messages = AsyncMock(
            return_value={"content": prose_text},
        )

        events = await _collect(agent.execute("do the work"))

        message_events = [e for e in events if isinstance(e, MessageEvent)]
        assert len(message_events) == 1
        # Prose should be wrapped as JSON with success=True
        result = json.loads(message_events[0].message)
        assert result["success"] is True
        assert result["result"] == prose_text
        assert result["attachments"] == []
        # Only one ask_with_messages call (the tool-result call) — no re-enforcement
        assert agent.ask_with_messages.await_count == 1

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
