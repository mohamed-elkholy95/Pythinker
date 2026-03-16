"""Tests for BaseAgent efficiency controls (hard-stop filtering + memory compaction)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.base import BaseAgent


@pytest.fixture
def mock_agent_repository():
    repo = AsyncMock()
    repo.get_memory = AsyncMock(
        return_value=MagicMock(
            empty=True,
            get_messages=MagicMock(return_value=[]),
            add_message=MagicMock(),
            add_messages=MagicMock(),
        )
    )
    return repo


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.model_name = "gpt-4"
    return llm


@pytest.fixture
def mock_json_parser():
    parser = AsyncMock()
    parser.parse = AsyncMock(return_value={})
    return parser


@pytest.fixture
def mixed_tool_registry():
    tool = MagicMock()
    tool.name = "test_tools"
    tool.get_tools = MagicMock(
        return_value=[
            {
                "type": "function",
                "function": {
                    "name": "file_read",
                    "description": "Read file",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "file_find_by_name",
                    "description": "Find files",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search web",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "file_write",
                    "description": "Write file",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        ]
    )
    return tool


def test_hard_stop_filters_all_read_tools(
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
    mixed_tool_registry,
):
    agent = BaseAgent(
        agent_id="agent-test",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
        tools=[mixed_tool_registry],
    )

    agent._efficiency_monitor._consecutive_reads = agent._efficiency_monitor.strong_threshold

    names = {tool["function"]["name"] for tool in agent.get_available_tools() or []}
    assert "file_write" in names
    assert "file_read" not in names
    assert "file_find_by_name" not in names
    assert "search" not in names


def test_critical_budget_blocks_repeated_tool_even_if_exempt(
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
    mixed_tool_registry,
):
    agent = BaseAgent(
        agent_id="agent-test",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
        tools=[mixed_tool_registry],
    )

    # Simulate loop pressure on an exempt tool (file_write) while token budget is critical.
    agent._efficiency_monitor._last_tool_name = "file_write"
    agent._efficiency_monitor._consecutive_same_tool = agent._efficiency_monitor.same_tool_threshold
    agent._current_token_usage_ratio = MagicMock(return_value=0.985)

    names = {tool["function"]["name"] for tool in agent.get_available_tools() or []}
    assert "file_write" not in names


def test_tool_result_memory_compaction_caps_large_payload(
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
):
    agent = BaseAgent(
        agent_id="agent-test",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
    )

    result = ToolResult(
        success=True,
        message="ok",
        data={"blob": "x" * 50000},
    )
    serialized = agent._serialize_tool_result_for_memory(result)

    assert len(serialized) <= agent._TOOL_RESULT_MEMORY_MAX_CHARS

    parsed = json.loads(serialized)
    assert parsed["success"] is True
    assert parsed["data"]["_compacted"] is True
    assert parsed["data"]["_original_size_chars"] > agent._TOOL_RESULT_MEMORY_MAX_CHARS


def test_tool_result_memory_serialization_keeps_small_payload(
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
):
    agent = BaseAgent(
        agent_id="agent-test",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
    )

    result = ToolResult(success=True, message="ok", data={"value": "small"})
    serialized = agent._serialize_tool_result_for_memory(result)
    parsed = json.loads(serialized)

    assert parsed["success"] is True
    assert parsed["data"]["value"] == "small"
