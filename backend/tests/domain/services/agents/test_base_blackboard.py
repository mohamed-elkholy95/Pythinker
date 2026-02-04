# backend/tests/domain/services/agents/test_base_blackboard.py
"""Tests for BaseAgent blackboard integration.

These tests verify the State Manifest (Blackboard Architecture) integration
with BaseAgent, allowing agents to share state via a common blackboard.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.state_manifest import StateEntry, StateManifest
from app.domain.services.agents.base import BaseAgent


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


@pytest.fixture
def shared_manifest():
    """Create a shared StateManifest for testing."""
    return StateManifest(session_id="test-session")


@pytest.mark.asyncio
async def test_agent_can_post_to_blackboard(
    shared_manifest,
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
):
    """Agent should be able to post state to the shared blackboard.

    This tests the blackboard architecture pattern where agents post findings
    to a shared state manifest for other agents to discover.
    """
    agent = BaseAgent(
        agent_id="test-agent",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
        state_manifest=shared_manifest,
    )

    await agent.post_state("finding", {"data": "value"})

    entry = shared_manifest.get("finding")
    assert entry is not None
    assert entry.value == {"data": "value"}
    assert entry.posted_by == "test-agent"


@pytest.mark.asyncio
async def test_agent_can_read_blackboard(
    shared_manifest,
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
):
    """Agent should be able to read state from the shared blackboard.

    This tests the discovery pattern where agents can find findings
    posted by other agents.
    """
    # Another agent posts to the blackboard
    shared_manifest.post(
        StateEntry(
            key="research",
            value="Important finding",
            posted_by="other-agent",
        )
    )

    agent = BaseAgent(
        agent_id="test-agent",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
        state_manifest=shared_manifest,
    )

    value = await agent.read_state("research")
    assert value == "Important finding"


@pytest.mark.asyncio
async def test_agent_read_returns_none_for_missing_key(
    shared_manifest,
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
):
    """Agent should return None when reading a non-existent key."""
    agent = BaseAgent(
        agent_id="test-agent",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
        state_manifest=shared_manifest,
    )

    value = await agent.read_state("nonexistent")
    assert value is None


@pytest.mark.asyncio
async def test_agent_post_without_manifest_raises(
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
):
    """Agent should raise error when posting without a manifest."""
    agent = BaseAgent(
        agent_id="test-agent",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
        # No state_manifest provided
    )

    with pytest.raises(ValueError, match="No state manifest configured"):
        await agent.post_state("key", "value")


@pytest.mark.asyncio
async def test_agent_read_without_manifest_returns_none(
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
):
    """Agent should return None when reading without a manifest configured."""
    agent = BaseAgent(
        agent_id="test-agent",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
        # No state_manifest provided
    )

    value = await agent.read_state("key")
    assert value is None


@pytest.mark.asyncio
async def test_agent_post_with_metadata(
    shared_manifest,
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
):
    """Agent should be able to post state with metadata."""
    agent = BaseAgent(
        agent_id="test-agent",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
        state_manifest=shared_manifest,
    )

    await agent.post_state(
        "analysis_result",
        {"score": 0.95},
        metadata={"model": "gpt-4", "confidence": "high"},
    )

    entry = shared_manifest.get("analysis_result")
    assert entry is not None
    assert entry.value == {"score": 0.95}
    assert entry.metadata["model"] == "gpt-4"
    assert entry.metadata["confidence"] == "high"


@pytest.mark.asyncio
async def test_get_blackboard_context_with_entries(
    shared_manifest,
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
):
    """Agent should be able to get blackboard state for LLM context."""
    # Add some entries to the manifest
    shared_manifest.post(
        StateEntry(
            key="finding1",
            value="First discovery",
            posted_by="research-agent",
        )
    )
    shared_manifest.post(
        StateEntry(
            key="finding2",
            value="Second discovery",
            posted_by="analysis-agent",
        )
    )

    agent = BaseAgent(
        agent_id="test-agent",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
        state_manifest=shared_manifest,
    )

    context = agent._get_blackboard_context()
    assert "Shared State" in context or "Blackboard" in context
    assert "finding1" in context or "First discovery" in context


@pytest.mark.asyncio
async def test_get_blackboard_context_without_manifest(
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
):
    """Agent should return empty string for context when no manifest configured."""
    agent = BaseAgent(
        agent_id="test-agent",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
        # No state_manifest provided
    )

    context = agent._get_blackboard_context()
    assert context == ""


@pytest.mark.asyncio
async def test_state_manifest_default_is_none(
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
):
    """Agent should have state_manifest=None by default."""
    agent = BaseAgent(
        agent_id="test-agent",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
    )

    assert agent.state_manifest is None


@pytest.mark.asyncio
async def test_multiple_agents_share_blackboard(
    shared_manifest,
    mock_agent_repository,
    mock_llm,
    mock_json_parser,
):
    """Multiple agents should be able to share the same blackboard."""
    agent1 = BaseAgent(
        agent_id="planner-agent",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
        state_manifest=shared_manifest,
    )

    agent2 = BaseAgent(
        agent_id="executor-agent",
        agent_repository=mock_agent_repository,
        llm=mock_llm,
        json_parser=mock_json_parser,
        state_manifest=shared_manifest,
    )

    # Agent 1 posts
    await agent1.post_state("plan", {"steps": ["step1", "step2"]})

    # Agent 2 reads
    plan = await agent2.read_state("plan")
    assert plan == {"steps": ["step1", "step2"]}

    # Verify posted_by is correct
    entry = shared_manifest.get("plan")
    assert entry.posted_by == "planner-agent"
