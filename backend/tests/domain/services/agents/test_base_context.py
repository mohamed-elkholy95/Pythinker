# backend/tests/domain/services/agents/test_base_context.py
"""Tests for BaseAgent context manager integration.

These tests verify the Manus-style attention manipulation pattern
where the context manager provides goal/todo context to agents.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.agents.base import BaseAgent


@pytest.fixture
def mock_context_manager():
    """Create a mock context manager for testing."""
    cm = AsyncMock()
    cm.get_attention_context = AsyncMock(return_value="## Current Goal\nTest goal")
    cm.update_todo = AsyncMock()
    return cm


@pytest.fixture
def mock_agent_repository():
    """Create a mock agent repository."""
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
    """Create a mock LLM."""
    llm = MagicMock()
    llm.model_name = "gpt-4"
    return llm


@pytest.fixture
def mock_json_parser():
    """Create a mock JSON parser."""
    parser = AsyncMock()
    parser.parse = AsyncMock(return_value={})
    return parser


@pytest.mark.asyncio
async def test_agent_injects_attention_context(
    mock_context_manager,
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
):
    """Agent should inject attention context into prompts.

    This tests the attention manipulation pattern from Manus AI architecture.
    The context manager provides goal/todo context that should be injected
    into agent prompts to prevent goal drift in long conversations.
    """
    agent = BaseAgent(
        agent_id="test",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
    )
    agent.context_manager = mock_context_manager

    context = await agent._get_attention_context()
    assert "Current Goal" in context
    mock_context_manager.get_attention_context.assert_called_once()


@pytest.mark.asyncio
async def test_agent_returns_empty_string_without_context_manager(
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
):
    """Agent should return empty string when no context manager is set.

    The context manager is optional, so agents without one should still work.
    """
    agent = BaseAgent(
        agent_id="test",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
    )
    # context_manager is None by default

    context = await agent._get_attention_context()
    assert context == ""


@pytest.mark.asyncio
async def test_context_manager_default_is_none(
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
):
    """Agent should have context_manager=None by default."""
    agent = BaseAgent(
        agent_id="test",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
    )

    assert agent.context_manager is None
