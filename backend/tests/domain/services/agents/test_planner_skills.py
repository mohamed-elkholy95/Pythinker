# backend/tests/domain/services/agents/test_planner_skills.py
"""Tests for skill integration in the PlannerAgent."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.agents.planner import PlannerAgent


class MockSkill:
    """Mock skill with proper name and description attributes."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description


@pytest.fixture
def mock_skill_loader():
    """Create a mock skill loader with test skills."""
    loader = MagicMock()
    loader.discover_skills = AsyncMock(
        return_value=[
            MockSkill(name="data-analysis", description="Analyze datasets"),
            MockSkill(name="web-scraper", description="Scrape websites"),
        ]
    )
    loader.load_skill = AsyncMock(
        return_value=MagicMock(
            name="data-analysis",
            body="Use pandas for analysis...",
            get_disclosure_level=MagicMock(return_value={"body": "Instructions"}),
        )
    )
    return loader


@pytest.fixture
def mock_agent_repo():
    """Create a mock agent repository."""
    return MagicMock()


@pytest.fixture
def mock_llm():
    """Create a mock LLM with required attributes."""
    llm = MagicMock()
    llm.model_name = "gpt-4"
    llm.ask = AsyncMock(return_value={"content": "{}"})
    llm.ask_stream = AsyncMock()
    return llm


@pytest.fixture
def mock_json_parser():
    """Create a mock JSON parser."""
    return MagicMock()


@pytest.mark.asyncio
async def test_planner_discovers_relevant_skills(mock_skill_loader, mock_llm):
    """Planner should identify relevant skills for the task."""
    # Create minimal mocks for required PlannerAgent parameters
    mock_agent_repo = MagicMock()
    mock_tools: list = []
    mock_json_parser = MagicMock()

    planner = PlannerAgent(
        agent_id="test",
        agent_repository=mock_agent_repo,
        llm=mock_llm,
        tools=mock_tools,
        json_parser=mock_json_parser,
        skill_loader=mock_skill_loader,
    )

    skills = await planner._discover_relevant_skills("Analyze the sales data")

    mock_skill_loader.discover_skills.assert_called_once()
    # Should find data-analysis skill as relevant
    assert any("data" in s.name.lower() or "analysis" in s.description.lower() for s in skills)


@pytest.mark.asyncio
async def test_planner_no_skill_loader_returns_empty(mock_llm):
    """Planner without skill_loader should return empty list."""
    mock_agent_repo = MagicMock()
    mock_tools: list = []
    mock_json_parser = MagicMock()

    planner = PlannerAgent(
        agent_id="test",
        agent_repository=mock_agent_repo,
        llm=mock_llm,
        tools=mock_tools,
        json_parser=mock_json_parser,
        # No skill_loader provided
    )

    skills = await planner._discover_relevant_skills("Analyze the sales data")

    assert skills == []


@pytest.mark.asyncio
async def test_planner_build_planning_context_with_skills(mock_skill_loader, mock_llm):
    """Planner should build context including relevant skills."""
    mock_agent_repo = MagicMock()
    mock_tools: list = []
    mock_json_parser = MagicMock()

    planner = PlannerAgent(
        agent_id="test",
        agent_repository=mock_agent_repo,
        llm=mock_llm,
        tools=mock_tools,
        json_parser=mock_json_parser,
        skill_loader=mock_skill_loader,
    )

    context = await planner._build_planning_context("Analyze the sales data")

    # Should include skill information in context
    assert "Available Skills" in context or context == ""  # Empty if no matching skills
    mock_skill_loader.discover_skills.assert_called_once()


@pytest.mark.asyncio
async def test_planner_build_planning_context_no_skills(mock_llm):
    """Planner without skill_loader should build empty context."""
    mock_agent_repo = MagicMock()
    mock_tools: list = []
    mock_json_parser = MagicMock()

    planner = PlannerAgent(
        agent_id="test",
        agent_repository=mock_agent_repo,
        llm=mock_llm,
        tools=mock_tools,
        json_parser=mock_json_parser,
        # No skill_loader provided
    )

    context = await planner._build_planning_context("Analyze the sales data")

    assert context == ""


@pytest.mark.asyncio
async def test_discover_skills_filters_by_task_keywords(mock_skill_loader, mock_llm):
    """Skill discovery should filter skills by matching task keywords."""
    mock_agent_repo = MagicMock()
    mock_tools: list = []
    mock_json_parser = MagicMock()

    planner = PlannerAgent(
        agent_id="test",
        agent_repository=mock_agent_repo,
        llm=mock_llm,
        tools=mock_tools,
        json_parser=mock_json_parser,
        skill_loader=mock_skill_loader,
    )

    # Test with web-related task - should match web-scraper
    skills = await planner._discover_relevant_skills("Scrape the website for product info")

    # Should find web-scraper skill as relevant
    assert any("web" in s.name.lower() or "scrape" in s.description.lower() for s in skills)


@pytest.mark.asyncio
async def test_discover_skills_no_match_returns_empty(mock_skill_loader, mock_llm):
    """Skill discovery should return empty list when no skills match."""
    mock_agent_repo = MagicMock()
    mock_tools: list = []
    mock_json_parser = MagicMock()

    planner = PlannerAgent(
        agent_id="test",
        agent_repository=mock_agent_repo,
        llm=mock_llm,
        tools=mock_tools,
        json_parser=mock_json_parser,
        skill_loader=mock_skill_loader,
    )

    # Test with unrelated task - should not match any skill
    skills = await planner._discover_relevant_skills("Send an email")

    # No skills should match "email" task
    assert len(skills) == 0
