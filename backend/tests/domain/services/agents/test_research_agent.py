"""Tests for Research Sub-Agent.

Tests the ResearchSubAgent class implementing individual research tasks
for the wide research pattern. Each agent instance has its own context,
preventing interference between parallel research tasks.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.research_task import ResearchTask
from app.domain.services.agents.research_agent import ResearchSubAgent


@pytest.fixture
def mock_llm():
    """Mock LLM following LLMProtocol."""
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value=MagicMock(content="Research findings..."))
    return llm


@pytest.fixture
def mock_tools():
    """Mock tools dictionary with search tool."""
    search = AsyncMock()
    search.execute = AsyncMock(return_value={"results": [{"content": "Found info"}]})
    return {"search": search}


class TestResearchAgentBasics:
    """Basic functionality tests."""

    @pytest.mark.asyncio
    async def test_research_agent_processes_task(self, mock_llm, mock_tools):
        """Test that agent can process a research task and return results."""
        agent = ResearchSubAgent(
            session_id="test",
            llm=mock_llm,
            tools=mock_tools,
        )

        task = ResearchTask(
            query="What is machine learning?",
            parent_task_id="parent_123",
            index=0,
            total=1,
        )

        result = await agent.research(task)

        assert result is not None
        assert "findings" in result.lower() or len(result) > 0

    @pytest.mark.asyncio
    async def test_research_agent_calls_search_tool(self, mock_llm, mock_tools):
        """Test that agent uses search tool to gather information."""
        agent = ResearchSubAgent(
            session_id="test",
            llm=mock_llm,
            tools=mock_tools,
        )

        task = ResearchTask(
            query="Python programming",
            parent_task_id="parent_123",
            index=0,
            total=1,
        )

        await agent.research(task)

        mock_tools["search"].execute.assert_called_once_with(query="Python programming")

    @pytest.mark.asyncio
    async def test_research_agent_calls_llm_with_context(self, mock_llm, mock_tools):
        """Test that agent synthesizes search results with LLM."""
        agent = ResearchSubAgent(
            session_id="test",
            llm=mock_llm,
            tools=mock_tools,
        )

        task = ResearchTask(
            query="Data science",
            parent_task_id="parent_123",
            index=0,
            total=1,
        )

        await agent.research(task)

        mock_llm.chat.assert_called_once()
        call_args = mock_llm.chat.call_args[0][0]
        # Should include system prompt and user message with query
        assert len(call_args) == 2
        assert call_args[0]["role"] == "system"
        assert call_args[1]["role"] == "user"
        assert "Data science" in call_args[1]["content"]


class TestSearchToolHandling:
    """Tests for search tool integration."""

    @pytest.mark.asyncio
    async def test_research_agent_handles_missing_search_tool(self, mock_llm):
        """Test that agent works without search tool."""
        agent = ResearchSubAgent(
            session_id="test",
            llm=mock_llm,
            tools={},  # No search tool
        )

        task = ResearchTask(
            query="Test query",
            parent_task_id="parent_123",
            index=0,
            total=1,
        )

        result = await agent.research(task)

        assert result is not None
        mock_llm.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_research_agent_extracts_content_from_results(self, mock_llm):
        """Test that agent extracts content from search results."""
        mock_search = AsyncMock()
        mock_search.execute = AsyncMock(
            return_value={
                "results": [
                    {"content": "First result content"},
                    {"content": "Second result content"},
                    {"content": "Third result content"},
                ]
            }
        )

        agent = ResearchSubAgent(
            session_id="test",
            llm=mock_llm,
            tools={"search": mock_search},
        )

        task = ResearchTask(
            query="Test query",
            parent_task_id="parent_123",
            index=0,
            total=1,
        )

        await agent.research(task)

        # Check that content was passed to LLM
        call_args = mock_llm.chat.call_args[0][0]
        user_message = call_args[1]["content"]
        assert "First result content" in user_message
        assert "Second result content" in user_message

    @pytest.mark.asyncio
    async def test_research_agent_handles_snippet_fallback(self, mock_llm):
        """Test that agent uses snippet when content is not available."""
        mock_search = AsyncMock()
        mock_search.execute = AsyncMock(
            return_value={
                "results": [
                    {"snippet": "Snippet text instead of content"},
                ]
            }
        )

        agent = ResearchSubAgent(
            session_id="test",
            llm=mock_llm,
            tools={"search": mock_search},
        )

        task = ResearchTask(
            query="Test query",
            parent_task_id="parent_123",
            index=0,
            total=1,
        )

        await agent.research(task)

        call_args = mock_llm.chat.call_args[0][0]
        user_message = call_args[1]["content"]
        assert "Snippet text instead of content" in user_message

    @pytest.mark.asyncio
    async def test_research_agent_limits_results(self, mock_llm):
        """Test that agent limits number of results processed."""
        mock_search = AsyncMock()
        mock_search.execute = AsyncMock(return_value={"results": [{"content": f"Result {i}"} for i in range(10)]})

        agent = ResearchSubAgent(
            session_id="test",
            llm=mock_llm,
            tools={"search": mock_search},
        )

        task = ResearchTask(
            query="Test query",
            parent_task_id="parent_123",
            index=0,
            total=1,
        )

        await agent.research(task)

        # Check that only MAX_SEARCH_RESULTS are processed
        call_args = mock_llm.chat.call_args[0][0]
        user_message = call_args[1]["content"]
        # Should have first 5 results (0-4), not result 5+
        assert "Result 0" in user_message
        assert "Result 4" in user_message
        assert "Result 5" not in user_message

    @pytest.mark.asyncio
    async def test_research_agent_handles_empty_results(self, mock_llm):
        """Test that agent handles empty search results gracefully."""
        mock_search = AsyncMock()
        mock_search.execute = AsyncMock(return_value={"results": []})

        agent = ResearchSubAgent(
            session_id="test",
            llm=mock_llm,
            tools={"search": mock_search},
        )

        task = ResearchTask(
            query="Test query",
            parent_task_id="parent_123",
            index=0,
            total=1,
        )

        result = await agent.research(task)

        assert result is not None


class TestLLMResponseHandling:
    """Tests for LLM response handling."""

    @pytest.mark.asyncio
    async def test_research_agent_returns_llm_content(self, mock_tools):
        """Test that agent returns LLM response content."""
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(content="This is the research summary."))

        agent = ResearchSubAgent(
            session_id="test",
            llm=mock_llm,
            tools=mock_tools,
        )

        task = ResearchTask(
            query="Test query",
            parent_task_id="parent_123",
            index=0,
            total=1,
        )

        result = await agent.research(task)

        assert result == "This is the research summary."

    @pytest.mark.asyncio
    async def test_research_agent_handles_string_response(self, mock_tools):
        """Test that agent handles string response (no content attribute)."""
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="String response without content attribute")

        agent = ResearchSubAgent(
            session_id="test",
            llm=mock_llm,
            tools=mock_tools,
        )

        task = ResearchTask(
            query="Test query",
            parent_task_id="parent_123",
            index=0,
            total=1,
        )

        result = await agent.research(task)

        assert "String response" in result


class TestAgentInitialization:
    """Tests for agent initialization."""

    def test_agent_initialization(self, mock_llm, mock_tools):
        """Test agent initializes with required parameters."""
        agent = ResearchSubAgent(
            session_id="test_session",
            llm=mock_llm,
            tools=mock_tools,
        )

        assert agent.session_id == "test_session"
        assert agent.llm is mock_llm
        assert agent.tools is mock_tools

    def test_agent_has_system_prompt(self, mock_llm, mock_tools):
        """Test agent has a system prompt defined."""
        agent = ResearchSubAgent(
            session_id="test",
            llm=mock_llm,
            tools=mock_tools,
        )

        assert agent.SYSTEM_PROMPT is not None
        assert len(agent.SYSTEM_PROMPT) > 0
        assert "research" in agent.SYSTEM_PROMPT.lower()
