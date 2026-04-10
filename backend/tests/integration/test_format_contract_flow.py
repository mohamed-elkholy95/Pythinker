"""Integration test: format contract recovery after tool-call loop.

Validates that when a tool-equipped agent with format='json_object'
receives a non-JSON response after tool calls, the format re-enforcement
block in base.py recovers by making one additional ask_with_messages()
call with format='json_object'.

These tests exercise the following production fixes end-to-end:
  - Task 1 (base.py): Re-enforce JSON format after tool-calling loop exits.
  - Task 2 (execution.py): Skip tool-marker text before JSON parsing.

No real LLM, database, or network calls are made — all LLM interactions
and repository I/O are replaced with lightweight mocks.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.event import MessageEvent
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.base import BaseAgent

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_memory_mock() -> MagicMock:
    """Return a minimal AgentMemory-compatible mock.

    The mock must satisfy every branch that touches ``self.memory`` inside
    BaseAgent._add_to_memory / ask_with_messages / _ensure_within_token_limit.
    """
    mem = MagicMock()
    mem.empty = True
    mem.get_messages = MagicMock(return_value=[])
    mem.add_message = MagicMock()
    mem.add_messages = MagicMock()
    # config attribute accessed by _resolve_feature_flags + graduated_compaction path
    mem.config = MagicMock()
    mem.config.use_graduated_compaction = False
    return mem


def _make_repo_mock() -> AsyncMock:
    """Return a minimal AgentRepository-compatible mock."""
    repo = AsyncMock()
    repo.get_memory = AsyncMock(return_value=_make_memory_mock())
    repo.save_memory = AsyncMock()
    repo.save = AsyncMock()
    return repo


def _make_tool_mock(function_name: str = "web_search") -> MagicMock:
    """Return a minimal BaseTool-compatible mock exposing one function."""
    tool = MagicMock()
    tool.name = "search_tool"
    tool.get_tools = MagicMock(
        return_value=[
            {
                "type": "function",
                "function": {
                    "name": function_name,
                    "description": "Search the web",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                        },
                        "required": [],
                    },
                },
            }
        ]
    )
    tool.has_function = MagicMock(side_effect=lambda name: name == function_name)
    tool.invoke_function = AsyncMock(return_value=ToolResult.ok(message="Found results"))
    return tool


def _build_agent(tools: list | None = None, *, format_override: str = "json_object") -> BaseAgent:
    """Construct a BaseAgent wired with mocks and the given format."""
    llm = MagicMock()
    llm.model_name = "test-model"
    # max_tokens used in _resolve_budget_action / token pressure paths
    llm.max_tokens = 4096

    repo = _make_repo_mock()
    parser = AsyncMock()

    agent = BaseAgent(
        agent_id="integration-format-test",
        agent_repository=repo,
        llm=llm,
        json_parser=parser,
        tools=tools or [],
        # Pass empty feature flags to bypass config lookups
        feature_flags={},
    )
    agent.format = format_override

    # Pre-populate agent.memory so _ensure_memory() skips the repo call.
    agent.memory = _make_memory_mock()

    # Replace _add_to_memory: the real impl calls repo.save_memory and inspects
    # self.memory.  A simple AsyncMock is enough for all execution paths tested here.
    agent._add_to_memory = AsyncMock()

    # Replace _ensure_within_token_limit: the real impl counts tokens from
    # self.memory.get_messages(); since we're not testing compression, skip it.
    agent._ensure_within_token_limit = AsyncMock()

    # Cancellation token: use a null token so check_cancelled() is always a no-op.
    # (BaseAgent.__init__ already does this via CancellationToken.null(), but
    # replacing it explicitly ensures tests are self-contained.)
    cancel = MagicMock()
    cancel.check_cancelled = AsyncMock()
    agent._cancel_token = cancel

    return agent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_tool() -> MagicMock:
    return _make_tool_mock()


@pytest.fixture
def agent(mock_tool: MagicMock) -> BaseAgent:
    return _build_agent(tools=[mock_tool])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFormatContractRecovery:
    """End-to-end: tool calls → non-JSON response → format re-enforcement → valid JSON."""

    @pytest.mark.asyncio
    async def test_full_recovery_flow(self, agent: BaseAgent) -> None:
        """Simulate the complete recovery flow.

        Sequence:
          1. agent.ask() → tool call (LLM wants to invoke web_search)
          2. agent.ask_with_messages() #1 → non-JSON prose (post-tool response)
          3. agent.ask_with_messages() #2 → valid JSON (format re-enforcement call)

        The test asserts that:
          - Exactly one MessageEvent is emitted.
          - Its content is the valid JSON from the re-enforcement call.
          - ask_with_messages was called exactly twice.
        """
        # Round 1 (initial ask): LLM requests a tool call
        agent.ask = AsyncMock(
            return_value={
                "tool_calls": [
                    {
                        "id": "tc-1",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": '{"query": "test"}',
                        },
                    }
                ]
            }
        )

        # Round 2 (after tool result): prose — must trigger JSON re-enforcement
        prose_response = "I searched the web and found relevant information about the topic."
        valid_json = json.dumps({"success": True, "result": "Recovered after JSON re-enforcement", "attachments": []})
        agent.ask_with_messages = AsyncMock(
            side_effect=[
                {"content": prose_response},
                {"content": valid_json},
            ],
        )

        events = [event async for event in agent.execute("Search for test data")]
        message_events = [e for e in events if isinstance(e, MessageEvent)]

        assert len(message_events) == 1, f"Expected exactly 1 MessageEvent, got {len(message_events)}: {message_events}"

        parsed = json.loads(message_events[0].message)
        assert parsed["success"] is True
        assert parsed["result"] == "Recovered after JSON re-enforcement"

        # Two calls: post-tool response + JSON re-enforcement
        assert agent.ask_with_messages.await_count == 2, (
            f"Expected 2 ask_with_messages calls (re-enforcement), got {agent.ask_with_messages.await_count}"
        )
        reenforcement_call = agent.ask_with_messages.await_args_list[1]
        assert reenforcement_call.kwargs["format"] == "json_object"
        assert "Respond with ONLY a valid JSON object" in reenforcement_call.args[0][0]["content"]

    @pytest.mark.asyncio
    async def test_valid_json_passes_through_without_extra_call(self, agent: BaseAgent) -> None:
        """When the post-tool response is already valid JSON, no re-enforcement is made.

        Sequence:
          1. agent.ask() → tool call
          2. agent.ask_with_messages() #1 → valid JSON (no re-enforcement needed)

        The test asserts that ask_with_messages is called exactly once.
        """
        valid_json = json.dumps({"success": True, "result": "Already valid", "attachments": []})

        agent.ask = AsyncMock(
            return_value={
                "tool_calls": [
                    {
                        "id": "tc-2",
                        "type": "function",
                        "function": {"name": "web_search", "arguments": "{}"},
                    }
                ]
            }
        )

        # Post-tool response is already valid JSON — only 1 ask_with_messages call needed
        agent.ask_with_messages = AsyncMock(return_value={"content": valid_json})

        events = [event async for event in agent.execute("search")]
        message_events = [e for e in events if isinstance(e, MessageEvent)]

        assert len(message_events) == 1
        parsed = json.loads(message_events[0].message)
        assert parsed["success"] is True
        assert parsed["result"] == "Already valid"

        # Exactly 1 ask_with_messages call: tool result only, no re-enforcement
        assert agent.ask_with_messages.await_count == 1, (
            f"Expected 1 ask_with_messages call (no re-enforcement), got {agent.ask_with_messages.await_count}"
        )

    @pytest.mark.asyncio
    async def test_no_tool_calls_direct_json_response(self) -> None:
        """When no tools are called, a direct valid-JSON response passes through unchanged.

        When has_tools=True but the LLM immediately returns JSON without calling any
        tool, the while-loop exits on the first iteration (no tool_calls key), and
        the re-enforcement block is evaluated.  Because the content is already valid
        JSON, no extra ask_with_messages call should be made.
        """
        # Agent WITH a registered tool (so has_tools=True), but the LLM skips tool use
        tool = _make_tool_mock()
        agent = _build_agent(tools=[tool])

        valid_json = json.dumps({"success": True, "result": "Done", "attachments": []})

        # ask() returns content directly — no tool_calls key
        agent.ask = AsyncMock(return_value={"content": valid_json})
        agent.ask_with_messages = AsyncMock()  # Must NOT be called

        events = [event async for event in agent.execute("do work")]
        message_events = [e for e in events if isinstance(e, MessageEvent)]

        assert len(message_events) == 1
        parsed = json.loads(message_events[0].message)
        assert parsed["success"] is True
        assert parsed["result"] == "Done"

        # No ask_with_messages calls — re-enforcement was not triggered
        assert agent.ask_with_messages.await_count == 0, (
            "ask_with_messages should not be called when the initial response is already valid JSON"
        )

    @pytest.mark.asyncio
    async def test_required_tool_step_retries_after_text_only_initial_response(self) -> None:
        """Tool-required steps retry instead of accepting a prose-only first response."""
        tool = _make_tool_mock()
        agent = _build_agent(tools=[tool])
        agent._required_tool_names_this_step = {"web_search"}

        valid_json = json.dumps({"success": True, "result": "Recovered after tool use", "attachments": []})

        agent.ask = AsyncMock(return_value={"content": "I can help with that."})
        agent.ask_with_messages = AsyncMock(
            side_effect=[
                {
                    "tool_calls": [
                        {
                            "id": "tc-required-1",
                            "type": "function",
                            "function": {"name": "web_search", "arguments": '{"query": "dgx spark benchmarks"}'},
                        }
                    ]
                },
                {"content": valid_json},
            ]
        )

        events = [event async for event in agent.execute("Search for DGX Spark benchmarks")]
        message_events = [e for e in events if isinstance(e, MessageEvent)]

        assert len(message_events) == 1
        parsed = json.loads(message_events[0].message)
        assert parsed["success"] is True
        assert parsed["result"] == "Recovered after tool use"
        tool.invoke_function.assert_awaited_once()

        assert agent.ask_with_messages.await_count == 2
        first_retry_call = agent.ask_with_messages.await_args_list[0]
        retry_messages = first_retry_call.args[0]
        assert "requires actual tool use" in retry_messages[0]["content"]
        assert "web_search" in retry_messages[0]["content"]

    @pytest.mark.asyncio
    async def test_required_tool_step_returns_failure_when_retry_still_skips_tools(self) -> None:
        """Tool-required steps must not be wrapped into a successful prose JSON result."""
        tool = _make_tool_mock()
        agent = _build_agent(tools=[tool])
        agent._required_tool_names_this_step = {"web_search"}

        agent.ask = AsyncMock(return_value={"content": "Here is a summary from memory."})
        agent.ask_with_messages = AsyncMock(return_value={"content": "Still answering without any tool calls."})

        events = [event async for event in agent.execute("Search for DGX Spark benchmarks")]
        message_events = [e for e in events if isinstance(e, MessageEvent)]

        assert len(message_events) == 1
        parsed = json.loads(message_events[0].message)
        assert parsed["success"] is False
        assert "no tools were called" in parsed["error"]
        tool.invoke_function.assert_not_awaited()
        assert agent.ask_with_messages.await_count == 2

    @pytest.mark.asyncio
    async def test_no_tools_format_used_in_initial_ask(self) -> None:
        """When no tools are registered, initial_format=json_object is used from the start.

        The re-enforcement block is guarded by has_tools=True, so with no tools
        the block is skipped entirely and the initial ask's content is used directly.
        """
        # Agent with NO tools — has_tools will be False
        agent = _build_agent(tools=[])

        valid_json = json.dumps({"success": True, "result": "No tools needed", "attachments": []})

        agent.ask = AsyncMock(return_value={"content": valid_json})
        agent.ask_with_messages = AsyncMock()

        events = [event async for event in agent.execute("answer directly")]
        message_events = [e for e in events if isinstance(e, MessageEvent)]

        assert len(message_events) == 1
        parsed = json.loads(message_events[0].message)
        assert parsed["result"] == "No tools needed"

        # Verify ask was called with format="json_object" (initial_format = format when no tools)
        agent.ask.assert_awaited_once()
        _, kwargs = agent.ask.call_args
        assert kwargs.get("format") == "json_object" or agent.ask.call_args.args[1:] == ("json_object",), (
            "With no tools, initial ask must use format='json_object'"
        )

        # No ask_with_messages calls — re-enforcement block skipped (has_tools=False)
        assert agent.ask_with_messages.await_count == 0

    @pytest.mark.asyncio
    async def test_empty_post_tool_response_triggers_re_enforcement(self, agent: BaseAgent) -> None:
        """An empty content string after tool calls also triggers re-enforcement.

        The re-enforcement block checks for empty content (not just invalid JSON),
        so a response with content='' or content=None must also cause a second call.
        """
        valid_json = json.dumps({"success": True, "result": "Recovered from empty", "attachments": []})

        agent.ask = AsyncMock(
            return_value={
                "tool_calls": [
                    {
                        "id": "tc-3",
                        "type": "function",
                        "function": {"name": "web_search", "arguments": "{}"},
                    }
                ]
            }
        )

        # First ask_with_messages returns empty content → triggers re-enforcement
        # Second returns valid JSON
        agent.ask_with_messages = AsyncMock(
            side_effect=[
                {"content": ""},  # empty → _needs_format_fix = True
                {"content": valid_json},  # re-enforcement response
            ]
        )

        events = [event async for event in agent.execute("search")]
        message_events = [e for e in events if isinstance(e, MessageEvent)]

        assert len(message_events) == 1
        parsed = json.loads(message_events[0].message)
        assert parsed["result"] == "Recovered from empty"

        # Two calls: tool result + re-enforcement
        assert agent.ask_with_messages.await_count == 2

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_then_recovery(self, agent: BaseAgent) -> None:
        """Two sequential tool-call rounds followed by a non-JSON response.

        Simulates a more realistic multi-hop tool loop:
          Round 1: LLM calls web_search
          Round 2: LLM calls web_search again (chained tool use)
          Round 3: LLM returns prose (non-JSON) — re-enforcement must recover JSON
        """
        prose_text = "After searching twice, here is what I found..."
        valid_json = json.dumps({"success": True, "result": "Recovered after two tool rounds", "attachments": []})

        tool_call_response = {
            "tool_calls": [
                {
                    "id": "tc-multi",
                    "type": "function",
                    "function": {"name": "web_search", "arguments": '{"query": "follow-up"}'},
                }
            ]
        }

        agent.ask = AsyncMock(return_value=tool_call_response)

        agent.ask_with_messages = AsyncMock(
            side_effect=[
                tool_call_response,  # Round 2: another tool call
                {"content": prose_text},  # prose → JSON re-enforcement
                {"content": valid_json},
            ]
        )

        events = [event async for event in agent.execute("multi-hop search")]
        message_events = [e for e in events if isinstance(e, MessageEvent)]

        assert len(message_events) == 1
        parsed = json.loads(message_events[0].message)
        assert parsed["success"] is True
        assert parsed["result"] == "Recovered after two tool rounds"

        # 3 calls: tool-result-1, tool-result-2, JSON re-enforcement
        assert agent.ask_with_messages.await_count == 3

    @pytest.mark.asyncio
    async def test_post_tool_prose_reenforcement_fails_closed_when_json_still_invalid(self, agent: BaseAgent) -> None:
        """A tool-executing step must fail closed if the model still refuses JSON after re-enforcement."""
        agent.ask = AsyncMock(
            return_value={
                "tool_calls": [
                    {
                        "id": "tc-4",
                        "type": "function",
                        "function": {"name": "web_search", "arguments": '{"query": "dgx spark"}'},
                    }
                ]
            }
        )
        agent.ask_with_messages = AsyncMock(
            side_effect=[
                {"content": "I found several benchmark sources."},
                {"content": "Here is a plain-English summary instead of JSON."},
            ]
        )

        events = [event async for event in agent.execute("Search for DGX Spark benchmarks")]
        message_events = [e for e in events if isinstance(e, MessageEvent)]

        assert len(message_events) == 1
        parsed = json.loads(message_events[0].message)
        assert parsed["success"] is False
        assert parsed["result"] is None
        assert "valid JSON" in parsed["error"]
        assert agent.ask_with_messages.await_count == 2
