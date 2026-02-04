"""Tests for Wide Research Orchestrator.

Tests the WideResearchOrchestrator class implementing Manus AI's
"Wide Research" pattern:
- Research decomposition into independent sub-tasks
- Parallel execution with separate contexts
- Consistent quality across all items (100th = 1st)
- Result synthesis into unified output
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.domain.models.research_task import ResearchStatus, ResearchTask
from app.domain.services.research.wide_research import WideResearchOrchestrator


@pytest.fixture
def mock_search_tool():
    """Mock search tool for testing."""
    tool = AsyncMock()
    tool.execute = AsyncMock(return_value={"results": [{"title": "Test", "content": "Result"}]})
    return tool


@pytest.fixture
def mock_llm():
    """Mock LLM for testing."""
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="Synthesized result")
    return llm


class TestDecompose:
    """Tests for decompose method."""

    @pytest.mark.asyncio
    async def test_decompose_research_query(self):
        """Test decomposing queries into research tasks."""
        orchestrator = WideResearchOrchestrator(session_id="test", search_tool=AsyncMock(), llm=AsyncMock())

        queries = ["Item 1", "Item 2", "Item 3"]
        tasks = await orchestrator.decompose(queries, parent_id="parent_123")

        assert len(tasks) == 3
        assert all(t.status == ResearchStatus.PENDING for t in tasks)
        assert tasks[0].index == 0
        assert tasks[2].index == 2

    @pytest.mark.asyncio
    async def test_decompose_sets_parent_id(self):
        """Test that decompose sets parent_task_id correctly."""
        orchestrator = WideResearchOrchestrator(session_id="test", search_tool=AsyncMock(), llm=AsyncMock())

        tasks = await orchestrator.decompose(["Query 1", "Query 2"], parent_id="abc123")

        assert all(t.parent_task_id == "abc123" for t in tasks)

    @pytest.mark.asyncio
    async def test_decompose_sets_total_count(self):
        """Test that decompose sets total count correctly on all tasks."""
        orchestrator = WideResearchOrchestrator(session_id="test", search_tool=AsyncMock(), llm=AsyncMock())

        tasks = await orchestrator.decompose(["Q1", "Q2", "Q3", "Q4", "Q5"], parent_id="parent")

        assert all(t.total == 5 for t in tasks)

    @pytest.mark.asyncio
    async def test_decompose_empty_queries(self):
        """Test decompose with empty query list."""
        orchestrator = WideResearchOrchestrator(session_id="test", search_tool=AsyncMock(), llm=AsyncMock())

        tasks = await orchestrator.decompose([], parent_id="parent")

        assert len(tasks) == 0


class TestParallelExecution:
    """Tests for parallel execution."""

    @pytest.mark.asyncio
    async def test_parallel_execution(self, mock_search_tool, mock_llm):
        """Test executing tasks in parallel."""
        orchestrator = WideResearchOrchestrator(
            session_id="test",
            search_tool=mock_search_tool,
            llm=mock_llm,
            max_concurrency=5,
        )

        queries = [f"Query {i}" for i in range(10)]
        tasks = await orchestrator.decompose(queries, parent_id="parent_123")

        results = await orchestrator.execute_parallel(tasks)

        assert len(results) == 10
        # All should be attempted (completed or failed)
        assert all(t.status in [ResearchStatus.COMPLETED, ResearchStatus.FAILED] for t in results)

    @pytest.mark.asyncio
    async def test_parallel_execution_respects_concurrency_limit(self, mock_search_tool, mock_llm):
        """Test that parallel execution respects max_concurrency."""
        concurrent_count = 0
        max_concurrent = 0

        original_execute = mock_search_tool.execute

        async def track_concurrency(*args, **kwargs):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.05)  # Simulate work
            result = await original_execute(*args, **kwargs)
            concurrent_count -= 1
            return result

        mock_search_tool.execute = track_concurrency

        orchestrator = WideResearchOrchestrator(
            session_id="test",
            search_tool=mock_search_tool,
            llm=mock_llm,
            max_concurrency=3,
        )

        queries = [f"Query {i}" for i in range(10)]
        tasks = await orchestrator.decompose(queries, parent_id="parent")

        await orchestrator.execute_parallel(tasks)

        # Should never exceed max_concurrency
        assert max_concurrent <= 3

    @pytest.mark.asyncio
    async def test_parallel_execution_handles_failures(self, mock_llm):
        """Test that parallel execution handles individual task failures."""
        mock_search_tool = AsyncMock()
        call_count = 0

        async def failing_search(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise ValueError("Search failed")
            return {"results": [{"content": "Result"}]}

        mock_search_tool.execute = failing_search

        orchestrator = WideResearchOrchestrator(
            session_id="test",
            search_tool=mock_search_tool,
            llm=mock_llm,
            max_concurrency=5,
        )

        tasks = await orchestrator.decompose([f"Query {i}" for i in range(4)], parent_id="parent")
        results = await orchestrator.execute_parallel(tasks)

        completed = [t for t in results if t.status == ResearchStatus.COMPLETED]
        failed = [t for t in results if t.status == ResearchStatus.FAILED]

        assert len(completed) == 2
        assert len(failed) == 2

    @pytest.mark.asyncio
    async def test_parallel_execution_calls_progress_callback(self, mock_search_tool, mock_llm):
        """Test that progress callback is called during execution."""
        progress_calls = []

        def on_progress(task: ResearchTask):
            progress_calls.append((task.query, task.status))

        orchestrator = WideResearchOrchestrator(
            session_id="test",
            search_tool=mock_search_tool,
            llm=mock_llm,
            on_progress=on_progress,
        )

        tasks = await orchestrator.decompose(["Query 1"], parent_id="parent")
        await orchestrator.execute_parallel(tasks)

        # Should be called at start and end of each task
        assert len(progress_calls) >= 2
        statuses = [status for _, status in progress_calls]
        assert ResearchStatus.IN_PROGRESS in statuses
        assert ResearchStatus.COMPLETED in statuses


class TestSingleTaskExecution:
    """Tests for single task execution."""

    @pytest.mark.asyncio
    async def test_execute_single_extracts_sources(self, mock_llm):
        """Test that execute extracts sources from search results."""
        mock_search_tool = AsyncMock()
        mock_search_tool.execute = AsyncMock(
            return_value={
                "results": [
                    {"url": "https://example.com/1", "content": "Content 1"},
                    {"url": "https://example.com/2", "content": "Content 2"},
                ]
            }
        )

        orchestrator = WideResearchOrchestrator(session_id="test", search_tool=mock_search_tool, llm=mock_llm)

        tasks = await orchestrator.decompose(["Test query"], parent_id="parent")
        results = await orchestrator.execute_parallel(tasks)

        assert len(results[0].sources) == 2
        assert "https://example.com/1" in results[0].sources

    @pytest.mark.asyncio
    async def test_execute_single_handles_snippet_fallback(self, mock_llm):
        """Test that execute handles snippet when content is not available."""
        mock_search_tool = AsyncMock()
        mock_search_tool.execute = AsyncMock(
            return_value={
                "results": [
                    {"url": "https://example.com/1", "snippet": "Snippet text"},
                ]
            }
        )

        orchestrator = WideResearchOrchestrator(session_id="test", search_tool=mock_search_tool, llm=mock_llm)

        tasks = await orchestrator.decompose(["Test query"], parent_id="parent")
        results = await orchestrator.execute_parallel(tasks)

        assert results[0].status == ResearchStatus.COMPLETED
        assert "Snippet text" in results[0].result

    @pytest.mark.asyncio
    async def test_execute_single_handles_empty_results(self, mock_llm):
        """Test that execute handles empty search results."""
        mock_search_tool = AsyncMock()
        mock_search_tool.execute = AsyncMock(return_value={"results": []})

        orchestrator = WideResearchOrchestrator(session_id="test", search_tool=mock_search_tool, llm=mock_llm)

        tasks = await orchestrator.decompose(["Test query"], parent_id="parent")
        results = await orchestrator.execute_parallel(tasks)

        assert results[0].status == ResearchStatus.COMPLETED
        assert results[0].result == "No results found"


class TestSynthesis:
    """Tests for result synthesis."""

    @pytest.mark.asyncio
    async def test_synthesize_combines_results(self, mock_search_tool, mock_llm):
        """Test that synthesize combines completed task results."""
        orchestrator = WideResearchOrchestrator(session_id="test", search_tool=mock_search_tool, llm=mock_llm)

        tasks = await orchestrator.decompose(["Query 1", "Query 2"], parent_id="parent")
        tasks = await orchestrator.execute_parallel(tasks)

        result = await orchestrator.synthesize(tasks)

        # Without synthesis prompt, returns combined findings
        assert "Query 1" in result
        assert "Query 2" in result

    @pytest.mark.asyncio
    async def test_synthesize_uses_llm_with_prompt(self, mock_search_tool, mock_llm):
        """Test that synthesize uses LLM when prompt provided."""
        orchestrator = WideResearchOrchestrator(session_id="test", search_tool=mock_search_tool, llm=mock_llm)

        tasks = await orchestrator.decompose(["Query 1"], parent_id="parent")
        tasks = await orchestrator.execute_parallel(tasks)

        result = await orchestrator.synthesize(tasks, synthesis_prompt="Summarize the findings:")

        mock_llm.complete.assert_called_once()
        assert result == "Synthesized result"

    @pytest.mark.asyncio
    async def test_synthesize_handles_no_completed_tasks(self, mock_search_tool, mock_llm):
        """Test that synthesize handles case with no completed tasks."""
        orchestrator = WideResearchOrchestrator(session_id="test", search_tool=mock_search_tool, llm=mock_llm)

        # Create tasks but don't execute - mark them as failed
        tasks = await orchestrator.decompose(["Query 1"], parent_id="parent")
        tasks[0].fail("Test failure")

        result = await orchestrator.synthesize(tasks)

        assert result == "No research results to synthesize."

    @pytest.mark.asyncio
    async def test_synthesize_includes_sources(self, mock_llm):
        """Test that synthesize includes sources in output."""
        mock_search_tool = AsyncMock()
        mock_search_tool.execute = AsyncMock(
            return_value={
                "results": [
                    {"url": "https://source.com", "content": "Content"},
                ]
            }
        )

        orchestrator = WideResearchOrchestrator(session_id="test", search_tool=mock_search_tool, llm=mock_llm)

        tasks = await orchestrator.decompose(["Query 1"], parent_id="parent")
        tasks = await orchestrator.execute_parallel(tasks)

        result = await orchestrator.synthesize(tasks)

        assert "https://source.com" in result


class TestOrchestratorInitialization:
    """Tests for orchestrator initialization."""

    def test_initialization_with_defaults(self):
        """Test orchestrator initializes with default values."""
        orchestrator = WideResearchOrchestrator(session_id="test", search_tool=AsyncMock(), llm=AsyncMock())

        assert orchestrator.session_id == "test"
        assert orchestrator.max_concurrency == 10
        assert orchestrator.on_progress is None

    def test_initialization_with_custom_concurrency(self):
        """Test orchestrator accepts custom max_concurrency."""
        orchestrator = WideResearchOrchestrator(
            session_id="test",
            search_tool=AsyncMock(),
            llm=AsyncMock(),
            max_concurrency=20,
        )

        assert orchestrator.max_concurrency == 20
