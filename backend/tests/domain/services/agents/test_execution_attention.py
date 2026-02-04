# backend/tests/domain/services/agents/test_execution_attention.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.agents.execution import ExecutionAgent


@pytest.fixture
def mock_attention_injector():
    injector = MagicMock()
    injector.inject = MagicMock(
        return_value=[{"role": "system", "content": "Attention context"}, {"role": "user", "content": "Do the task"}]
    )
    return injector


@pytest.fixture
def mock_llm():
    """Create a properly configured mock LLM."""
    llm = MagicMock()
    llm.model_name = "gpt-4"  # TokenManager needs this as a string
    llm.ask = AsyncMock(return_value={"content": "{}"})
    return llm


@pytest.fixture
def mock_agent_repo():
    return MagicMock()


@pytest.fixture
def mock_json_parser():
    return MagicMock()


@pytest.mark.asyncio
async def test_execution_uses_attention_injection(mock_attention_injector, mock_llm, mock_agent_repo, mock_json_parser):
    """Execution agent should inject attention context."""
    agent = ExecutionAgent(
        agent_id="test",
        agent_repository=mock_agent_repo,
        llm=mock_llm,
        tools=[],
        json_parser=mock_json_parser,
        attention_injector=mock_attention_injector,
    )

    # Set goal and todo
    agent.current_goal = "Complete analysis"
    agent.current_todo = ["Step 1", "Step 2"]

    messages = [{"role": "user", "content": "Execute step 1"}]
    agent._apply_attention(messages)

    mock_attention_injector.inject.assert_called_once()
    # Verify goal and todo were passed
    call_kwargs = mock_attention_injector.inject.call_args[1]
    assert call_kwargs.get("goal") == "Complete analysis"


@pytest.mark.asyncio
async def test_execution_attention_with_todo_list(mock_attention_injector, mock_llm, mock_agent_repo, mock_json_parser):
    """Execution agent should pass todo list to attention injector."""
    agent = ExecutionAgent(
        agent_id="test",
        agent_repository=mock_agent_repo,
        llm=mock_llm,
        tools=[],
        json_parser=mock_json_parser,
        attention_injector=mock_attention_injector,
    )

    agent.current_goal = "Build feature"
    agent.current_todo = ["Write tests", "Implement code", "Review"]

    messages = [{"role": "user", "content": "Continue"}]
    agent._apply_attention(messages)

    call_kwargs = mock_attention_injector.inject.call_args[1]
    assert call_kwargs.get("todo") == ["Write tests", "Implement code", "Review"]


@pytest.mark.asyncio
async def test_execution_attention_default_injector(mock_llm, mock_agent_repo, mock_json_parser):
    """Execution agent should create default AttentionInjector if not provided."""
    agent = ExecutionAgent(
        agent_id="test",
        agent_repository=mock_agent_repo,
        llm=mock_llm,
        tools=[],
        json_parser=mock_json_parser,
        # No attention_injector provided
    )

    # Should have default injector
    assert agent._attention_injector is not None
    # Default goal and todo should be initialized
    assert agent.current_goal is None
    assert agent.current_todo == []


@pytest.mark.asyncio
async def test_execution_attention_returns_injected_messages(
    mock_attention_injector, mock_llm, mock_agent_repo, mock_json_parser
):
    """_apply_attention should return the result from the injector."""
    agent = ExecutionAgent(
        agent_id="test",
        agent_repository=mock_agent_repo,
        llm=mock_llm,
        tools=[],
        json_parser=mock_json_parser,
        attention_injector=mock_attention_injector,
    )

    agent.current_goal = "Test goal"
    agent.current_todo = []

    messages = [{"role": "user", "content": "Original message"}]
    result = agent._apply_attention(messages)

    # Should return what the injector returns
    assert result == [{"role": "system", "content": "Attention context"}, {"role": "user", "content": "Do the task"}]
