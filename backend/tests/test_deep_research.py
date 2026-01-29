"""Tests for Deep Research feature."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.deep_research_manager import DeepResearchManager, get_deep_research_manager
from app.domain.models.deep_research import (
    DeepResearchConfig,
    DeepResearchSession,
    ResearchQuery,
    ResearchQueryStatus,
)
from app.domain.models.event import (
    DeepResearchEvent,
    DeepResearchQueryData,
    DeepResearchQueryStatus,
    DeepResearchStatus,
)
from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.flows.deep_research import DeepResearchFlow


class TestDeepResearchModels:
    """Test deep research domain models."""

    def test_research_query_creation(self):
        """Test ResearchQuery model creation."""
        query = ResearchQuery(
            id="test123",
            query="test query",
            status=ResearchQueryStatus.PENDING,
        )
        assert query.id == "test123"
        assert query.query == "test query"
        assert query.status == ResearchQueryStatus.PENDING
        assert query.result is None

    def test_research_query_status_transitions(self):
        """Test ResearchQuery status transitions."""
        query = ResearchQuery(id="test", query="test")
        assert query.status == ResearchQueryStatus.PENDING

        query.status = ResearchQueryStatus.SEARCHING
        assert query.status == ResearchQueryStatus.SEARCHING

        query.status = ResearchQueryStatus.COMPLETED
        query.result = [{"title": "Test", "link": "http://test.com", "snippet": "Test"}]
        assert query.status == ResearchQueryStatus.COMPLETED
        assert len(query.result) == 1

    def test_deep_research_config(self):
        """Test DeepResearchConfig model."""
        config = DeepResearchConfig(
            queries=["query1", "query2", "query3"],
            auto_run=True,
            max_concurrent=3,
            timeout_per_query=30,
        )
        assert len(config.queries) == 3
        assert config.auto_run is True
        assert config.max_concurrent == 3
        assert config.timeout_per_query == 30

    def test_deep_research_config_defaults(self):
        """Test DeepResearchConfig default values."""
        config = DeepResearchConfig(queries=["query1"])
        assert config.auto_run is False
        assert config.max_concurrent == 5
        assert config.timeout_per_query == 30

    def test_deep_research_session(self):
        """Test DeepResearchSession model."""
        config = DeepResearchConfig(queries=["q1", "q2"])
        queries = [
            ResearchQuery(id="1", query="q1", status=ResearchQueryStatus.COMPLETED),
            ResearchQuery(id="2", query="q2", status=ResearchQueryStatus.PENDING),
        ]
        session = DeepResearchSession(
            research_id="res123",
            session_id="sess456",
            config=config,
            queries=queries,
        )
        assert session.research_id == "res123"
        assert session.completed_count == 1
        assert session.total_count == 2


class TestDeepResearchEvent:
    """Test deep research event models."""

    def test_deep_research_event_creation(self):
        """Test DeepResearchEvent creation."""
        event = DeepResearchEvent(
            research_id="res123",
            status=DeepResearchStatus.STARTED,
            total_queries=3,
            completed_queries=0,
            queries=[],
            auto_run=False,
        )
        assert event.type == "deep_research"
        assert event.research_id == "res123"
        assert event.status == DeepResearchStatus.STARTED
        assert event.total_queries == 3

    def test_deep_research_query_data(self):
        """Test DeepResearchQueryData creation."""
        query_data = DeepResearchQueryData(
            id="q1",
            query="test query",
            status=DeepResearchQueryStatus.SEARCHING,
        )
        assert query_data.id == "q1"
        assert query_data.status == DeepResearchQueryStatus.SEARCHING


class TestDeepResearchFlow:
    """Test DeepResearchFlow class."""

    @pytest.fixture
    def mock_search_engine(self):
        """Create a mock search engine."""
        engine = AsyncMock()
        engine.search = AsyncMock(return_value=ToolResult(
            success=True,
            data=SearchResults(
                query="test",
                results=[
                    SearchResultItem(title="Result 1", link="http://r1.com", snippet="Snippet 1"),
                    SearchResultItem(title="Result 2", link="http://r2.com", snippet="Snippet 2"),
                ]
            )
        ))
        return engine

    @pytest.fixture
    def flow(self, mock_search_engine):
        """Create a DeepResearchFlow instance."""
        return DeepResearchFlow(
            search_engine=mock_search_engine,
            session_id="test_session",
        )

    @pytest.mark.asyncio
    async def test_flow_auto_run(self, flow, mock_search_engine):
        """Test flow with auto_run enabled."""
        config = DeepResearchConfig(
            queries=["query1", "query2"],
            auto_run=True,
            max_concurrent=2,
        )

        events = []
        async for event in flow.run(config):
            events.append(event)

        # Should have events: STARTED, QUERY_STARTED x2, QUERY_COMPLETED x2, COMPLETED
        assert len(events) >= 2
        assert events[0].status == DeepResearchStatus.STARTED
        assert events[-1].status == DeepResearchStatus.COMPLETED

        # Verify search was called for each query
        assert mock_search_engine.search.call_count == 2

    @pytest.mark.asyncio
    async def test_flow_awaiting_approval(self, flow):
        """Test flow waits for approval when auto_run is False."""
        config = DeepResearchConfig(
            queries=["query1"],
            auto_run=False,
        )

        events = []
        run_task = asyncio.create_task(self._collect_events(flow, config, events))

        # Wait a bit for the flow to start
        await asyncio.sleep(0.1)

        # Should have emitted AWAITING_APPROVAL
        assert len(events) >= 1
        assert events[0].status == DeepResearchStatus.AWAITING_APPROVAL

        # Approve the research
        await flow.approve()

        # Wait for completion
        await run_task

        # Should have completed
        assert events[-1].status == DeepResearchStatus.COMPLETED

    async def _collect_events(self, flow, config, events):
        """Helper to collect events from flow."""
        async for event in flow.run(config):
            events.append(event)

    @pytest.mark.asyncio
    async def test_flow_skip_query(self, flow, mock_search_engine):
        """Test skipping individual queries."""
        # Make search slow
        async def slow_search(query):
            await asyncio.sleep(2)
            return ToolResult(success=True, data=SearchResults(query=query, results=[]))

        mock_search_engine.search = slow_search

        config = DeepResearchConfig(
            queries=["query1", "query2"],
            auto_run=True,
            max_concurrent=1,
            timeout_per_query=10,
        )

        events = []
        run_task = asyncio.create_task(self._collect_events(flow, config, events))

        # Wait for flow to start
        await asyncio.sleep(0.2)

        # Skip all queries
        await flow.skip_all()

        # Wait for completion
        await asyncio.wait_for(run_task, timeout=5)

        # Check that queries were skipped
        session = flow.get_session()
        assert session is not None
        skipped_count = sum(1 for q in session.queries if q.status == ResearchQueryStatus.SKIPPED)
        assert skipped_count >= 1

    def test_compile_results_to_json(self, flow):
        """Test compiling results to JSON."""
        # Manually set up a session with results
        flow._research_id = "test123"
        flow._session = DeepResearchSession(
            research_id="test123",
            session_id="sess456",
            config=DeepResearchConfig(queries=["q1", "q2"]),
            queries=[
                ResearchQuery(
                    id="1",
                    query="query 1",
                    status=ResearchQueryStatus.COMPLETED,
                    result=[{"title": "R1", "link": "http://r1.com", "snippet": "S1"}],
                    completed_at=datetime.now(),
                ),
                ResearchQuery(
                    id="2",
                    query="query 2",
                    status=ResearchQueryStatus.SKIPPED,
                ),
            ],
        )

        json_data = flow.compile_results_to_json()

        assert json_data["research_id"] == "test123"
        assert json_data["total_queries"] == 2
        assert len(json_data["results"]) == 2
        assert json_data["results"][0]["input"] == "query 1"
        assert json_data["results"][1]["output"]["status"] == "skipped"

    def test_generate_research_summary(self, flow):
        """Test generating research summary."""
        flow._research_id = "test123"
        flow._session = DeepResearchSession(
            research_id="test123",
            session_id="sess456",
            config=DeepResearchConfig(queries=["q1"]),
            queries=[
                ResearchQuery(
                    id="1",
                    query="test query",
                    status=ResearchQueryStatus.COMPLETED,
                    result=[{"title": "Result", "link": "http://r.com", "snippet": "Snippet"}],
                ),
            ],
        )

        summary = flow.generate_research_summary()

        assert "# Deep Research Summary" in summary
        assert "test123" in summary
        assert "test query" in summary
        assert "[Result](http://r.com)" in summary


class TestDeepResearchManager:
    """Test DeepResearchManager singleton."""

    @pytest.fixture
    def manager(self):
        """Create a fresh manager instance."""
        # Reset singleton for testing
        DeepResearchManager._instance = None
        return DeepResearchManager()

    @pytest.fixture
    def mock_flow(self):
        """Create a mock flow."""
        flow = MagicMock(spec=DeepResearchFlow)
        flow.approve = AsyncMock()
        flow.skip_query = AsyncMock(return_value=True)
        flow.skip_all = AsyncMock()
        flow.cancel = AsyncMock()
        flow.get_session = MagicMock(return_value=MagicMock(
            research_id="test",
            status="started",
            total_count=3,
            completed_count=1,
        ))
        return flow

    @pytest.mark.asyncio
    async def test_register_and_get(self, manager, mock_flow):
        """Test registering and retrieving a flow."""
        await manager.register("session1", mock_flow)

        retrieved = manager.get("session1")
        assert retrieved is mock_flow

    @pytest.mark.asyncio
    async def test_unregister(self, manager, mock_flow):
        """Test unregistering a flow."""
        await manager.register("session1", mock_flow)
        await manager.unregister("session1")

        assert manager.get("session1") is None

    @pytest.mark.asyncio
    async def test_approve(self, manager, mock_flow):
        """Test approving a research."""
        await manager.register("session1", mock_flow)

        result = await manager.approve("session1")
        assert result is True
        mock_flow.approve.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_nonexistent(self, manager):
        """Test approving nonexistent research."""
        result = await manager.approve("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_skip_query(self, manager, mock_flow):
        """Test skipping a query."""
        await manager.register("session1", mock_flow)

        result = await manager.skip_query("session1", "query1")
        assert result is True
        mock_flow.skip_query.assert_called_once_with("query1")

    @pytest.mark.asyncio
    async def test_skip_all(self, manager, mock_flow):
        """Test skipping all queries."""
        await manager.register("session1", mock_flow)

        result = await manager.skip_query("session1", None)
        assert result is True
        mock_flow.skip_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel(self, manager, mock_flow):
        """Test cancelling research."""
        await manager.register("session1", mock_flow)

        result = await manager.cancel("session1")
        assert result is True
        mock_flow.cancel.assert_called_once()

        # Should be unregistered after cancel
        assert manager.get("session1") is None

    def test_singleton(self):
        """Test that manager is a singleton."""
        DeepResearchManager._instance = None
        m1 = get_deep_research_manager()
        m2 = get_deep_research_manager()
        assert m1 is m2
