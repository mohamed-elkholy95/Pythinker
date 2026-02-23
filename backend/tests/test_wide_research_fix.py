"""Tests for Wide Research fix - _search_tool initialization and WideResearchEvent emission."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.event import (
    WideResearchEvent,
    WideResearchStatus,
)
from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.flows.wide_research import WideResearchConfig


class TestWideResearchEvent:
    """Test WideResearchEvent model."""

    def test_wide_research_event_creation(self):
        """Test WideResearchEvent can be created with all fields."""
        event = WideResearchEvent(
            research_id="test123",
            topic="best LLM for coding",
            status=WideResearchStatus.PENDING,
            total_queries=6,
            completed_queries=0,
            sources_found=0,
            search_types=["info", "news"],
        )
        assert event.type == "wide_research"
        assert event.research_id == "test123"
        assert event.topic == "best LLM for coding"
        assert event.status == WideResearchStatus.PENDING
        assert event.total_queries == 6

    def test_wide_research_status_values(self):
        """Test all WideResearchStatus enum values."""
        assert WideResearchStatus.PENDING == "pending"
        assert WideResearchStatus.SEARCHING == "searching"
        assert WideResearchStatus.AGGREGATING == "aggregating"
        assert WideResearchStatus.COMPLETED == "completed"
        assert WideResearchStatus.FAILED == "failed"

    def test_wide_research_event_with_errors(self):
        """Test WideResearchEvent with error list."""
        event = WideResearchEvent(
            research_id="test456",
            topic="test topic",
            status=WideResearchStatus.FAILED,
            total_queries=4,
            completed_queries=2,
            sources_found=5,
            search_types=["info"],
            errors=["Query timeout", "Rate limit exceeded"],
        )
        assert event.status == WideResearchStatus.FAILED
        assert len(event.errors) == 2
        assert "Query timeout" in event.errors


class TestWideResearchConfig:
    """Test WideResearchConfig with deep_dive_top_n default."""

    def test_deep_dive_enabled_by_default(self):
        """Test that deep_dive_top_n defaults to 3 (enabled)."""
        config = WideResearchConfig(
            topic="test topic",
            queries=["query1", "query2"],
        )
        # After fix, deep_dive_top_n should default to 3
        assert config.deep_dive_top_n == 3


class TestPlanActFlowSearchTool:
    """Test _search_tool initialization in PlanActFlow."""

    @pytest.fixture
    def mock_search_engine(self):
        """Create a mock search engine."""
        engine = AsyncMock()
        engine.search = AsyncMock(
            return_value=ToolResult(
                success=True,
                data=SearchResults(
                    query="test",
                    results=[
                        SearchResultItem(title="Result 1", link="http://r1.com", snippet="Snippet 1"),
                        SearchResultItem(title="Result 2", link="http://r2.com", snippet="Snippet 2"),
                    ],
                ),
            )
        )
        return engine

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM."""
        llm = AsyncMock()
        llm.ask = AsyncMock(return_value={"content": "test response"})
        llm.model_name = "test-model"
        llm.count_tokens = MagicMock(return_value=100)
        return llm

    @pytest.fixture
    def mock_sandbox(self):
        """Create a mock sandbox."""
        sandbox = AsyncMock()
        sandbox.shell = AsyncMock()
        sandbox.file = AsyncMock()
        return sandbox

    @pytest.fixture
    def mock_browser(self):
        """Create a mock browser."""
        browser = AsyncMock()
        browser.navigate = AsyncMock(return_value=ToolResult(success=True, data={"content": "page content"}))
        return browser

    @pytest.fixture
    def mock_json_parser(self):
        """Create a mock JSON parser."""
        parser = MagicMock()
        parser.parse = MagicMock(return_value={})
        return parser

    @pytest.fixture
    def mock_mcp_tool(self):
        """Create a mock MCP tool."""
        tool = MagicMock()
        tool.name = "mcp"
        tool.description = "MCP tool"
        return tool

    @pytest.fixture
    def mock_repositories(self):
        """Create mock repositories."""
        agent_repo = AsyncMock()
        session_repo = AsyncMock()
        return agent_repo, session_repo

    def test_search_tool_initialized_with_search_engine(
        self,
        mock_search_engine,
        mock_llm,
        mock_sandbox,
        mock_browser,
        mock_json_parser,
        mock_mcp_tool,
        mock_repositories,
    ):
        """Test that _search_tool is properly initialized when search_engine is provided."""
        from app.domain.services.flows.plan_act import PlanActFlow

        agent_repo, session_repo = mock_repositories

        flow = PlanActFlow(
            agent_id="test_agent",
            agent_repository=agent_repo,
            session_id="test_session",
            session_repository=session_repo,
            llm=mock_llm,
            sandbox=mock_sandbox,
            browser=mock_browser,
            json_parser=mock_json_parser,
            mcp_tool=mock_mcp_tool,
            search_engine=mock_search_engine,
        )

        # After fix, _search_tool should be initialized
        assert flow._search_tool is not None
        assert flow._search_tool.search_engine is mock_search_engine

    def test_search_tool_none_without_search_engine(
        self,
        mock_llm,
        mock_sandbox,
        mock_browser,
        mock_json_parser,
        mock_mcp_tool,
        mock_repositories,
    ):
        """Test that _search_tool is None when search_engine is not provided."""
        from app.domain.services.flows.plan_act import PlanActFlow

        agent_repo, session_repo = mock_repositories

        flow = PlanActFlow(
            agent_id="test_agent",
            agent_repository=agent_repo,
            session_id="test_session",
            session_repository=session_repo,
            llm=mock_llm,
            sandbox=mock_sandbox,
            browser=mock_browser,
            json_parser=mock_json_parser,
            mcp_tool=mock_mcp_tool,
            search_engine=None,
        )

        # _search_tool should be None
        assert flow._search_tool is None
