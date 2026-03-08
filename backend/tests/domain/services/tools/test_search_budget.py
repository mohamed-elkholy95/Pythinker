"""Tests for SearchTool budget tracking, query clamping, and dedup skip."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.search import SearchTool, SearchType


def _make_search_result(query: str = "test") -> ToolResult:
    """Create a successful search ToolResult."""
    return ToolResult(
        success=True,
        message="[INFO SEARCH]\nResults",
        data=SearchResults(
            query=query,
            date_range=None,
            total_results=1,
            results=[
                SearchResultItem(
                    title="Test Result",
                    link="https://example.com",
                    snippet="A test result.",
                )
            ],
        ),
    )


# ---------------------------------------------------------------------------
# _BudgetTracker unit tests
# ---------------------------------------------------------------------------


class TestBudgetTracker:
    def test_initial_state_allows_search(self) -> None:
        bt = SearchTool._BudgetTracker(max_api_calls=10, max_wide_research=3)
        ok, reason = bt.can_search()
        assert ok is True
        assert reason == ""

    def test_initial_state_allows_wide_research(self) -> None:
        bt = SearchTool._BudgetTracker(max_api_calls=10, max_wide_research=3)
        ok, reason = bt.can_wide_research()
        assert ok is True
        assert reason == ""

    def test_api_calls_exhaust_budget(self) -> None:
        bt = SearchTool._BudgetTracker(max_api_calls=3, max_wide_research=2)
        bt.record_api_call(3)
        ok, reason = bt.can_search()
        assert ok is False
        assert "3/3" in reason

    def test_wide_research_limit(self) -> None:
        bt = SearchTool._BudgetTracker(max_api_calls=100, max_wide_research=2)
        bt.record_wide_research()
        bt.record_wide_research()
        ok, reason = bt.can_wide_research()
        assert ok is False
        assert "2/2" in reason

    def test_wide_research_blocked_by_api_budget(self) -> None:
        bt = SearchTool._BudgetTracker(max_api_calls=5, max_wide_research=10)
        bt.record_api_call(5)
        ok, reason = bt.can_wide_research()
        assert ok is False
        assert "5/5" in reason

    def test_remaining_tracks_correctly(self) -> None:
        bt = SearchTool._BudgetTracker(max_api_calls=10, max_wide_research=3)
        assert bt.remaining() == 10
        bt.record_api_call(4)
        assert bt.remaining() == 6
        bt.record_api_call(7)
        assert bt.remaining() == 0

    def test_record_api_call_with_count(self) -> None:
        bt = SearchTool._BudgetTracker(max_api_calls=20, max_wide_research=3)
        bt.record_api_call(5)
        bt.record_api_call(3)
        assert bt.remaining() == 12


# ---------------------------------------------------------------------------
# info_search_web budget enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_info_search_web_budget_exhausted() -> None:
    """info_search_web returns error when budget is exhausted."""
    tool = SearchTool(search_engine=MagicMock())
    tool._budget.record_api_call(tool._budget._max_api)

    result = await tool.info_search_web("test query")

    assert result.success is False
    assert "budget exhausted" in result.message.lower()


@pytest.mark.asyncio
async def test_info_search_web_dedup_skip() -> None:
    """info_search_web skips duplicate queries when dedup is enabled."""
    tool = SearchTool(search_engine=MagicMock())
    tool._dedup_skip = True

    # Mock TaskStateManager to return is_new=False
    mock_tsm = MagicMock()
    mock_tsm.record_query.return_value = False

    # Patch the source module (local import in info_search_web)
    with patch.dict(
        "sys.modules",
        {"app.domain.services.agents.task_state_manager": MagicMock(get_task_state_manager=lambda: mock_tsm)},
    ):
        result = await tool.info_search_web("duplicate query")

    assert result.success is False
    assert "already searched" in result.message.lower()


@pytest.mark.asyncio
async def test_info_search_web_records_budget() -> None:
    """info_search_web records the API call in budget tracker."""
    engine = AsyncMock()
    engine.search = AsyncMock(return_value=_make_search_result("budget test"))
    engine.provider_name = "test"
    tool = SearchTool(search_engine=engine)
    tool._dedup_skip = False  # Disable dedup so we reach the API path

    assert tool._budget._api_calls == 0
    await tool.info_search_web("budget test query")
    assert tool._budget._api_calls == 1


@pytest.mark.asyncio
async def test_info_search_web_allows_new_query() -> None:
    """info_search_web proceeds for new queries even with dedup enabled."""
    engine = AsyncMock()
    engine.search = AsyncMock(return_value=_make_search_result("new query"))
    tool = SearchTool(search_engine=engine)
    tool._dedup_skip = True

    mock_tsm = MagicMock()
    mock_tsm.record_query.return_value = True  # is_new

    with patch.dict(
        "sys.modules",
        {"app.domain.services.agents.task_state_manager": MagicMock(get_task_state_manager=lambda: mock_tsm)},
    ):
        result = await tool.info_search_web("new query")

    assert result.success is True


# ---------------------------------------------------------------------------
# wide_research budget enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wide_research_budget_exhausted() -> None:
    """wide_research returns error when wide_research limit is reached."""
    tool = SearchTool(search_engine=MagicMock())
    # Exhaust wide_research limit
    for _ in range(tool._budget._max_wide):
        tool._budget.record_wide_research()

    result = await tool.wide_research(
        topic="test",
        queries=["q1", "q2"],
    )

    assert result.success is False
    assert "wide research limit" in result.message.lower()


@pytest.mark.asyncio
async def test_wide_research_clamps_queries() -> None:
    """wide_research clamps queries to max_wide_research_queries."""
    engine = AsyncMock()
    engine.search = AsyncMock(return_value=_make_search_result())
    engine.provider_name = "test"
    tool = SearchTool(search_engine=engine)
    tool._max_wide_queries = 2

    # Mock _execute_typed_search to track how many unique base queries are used
    call_queries: list[str] = []

    async def tracking_execute(query: str, *args, **kwargs):
        call_queries.append(query)
        return _make_search_result(query)

    tool._execute_typed_search = tracking_execute

    await tool.wide_research(
        topic="test topic",
        queries=["q1", "q2", "q3", "q4", "q5"],  # 5 queries, limit is 2
    )

    # With 2 queries x 2 variants (QueryExpander) = up to 4 total queries
    # But the input was clamped from 5 to 2 base queries
    assert len(call_queries) <= 4  # 2 base queries x 2 variants max


@pytest.mark.asyncio
async def test_wide_research_trims_to_remaining_budget() -> None:
    """wide_research trims query list to remaining API call budget."""
    engine = AsyncMock()
    engine.search = AsyncMock(return_value=_make_search_result())
    engine.provider_name = "test"
    tool = SearchTool(search_engine=engine)

    # Leave only 2 API calls remaining
    tool._budget.record_api_call(tool._budget._max_api - 2)

    call_count = 0

    async def counting_execute(query: str, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _make_search_result(query)

    tool._execute_typed_search = counting_execute

    await tool.wide_research(
        topic="test topic",
        queries=["q1", "q2", "q3"],
    )

    # Should only execute 2 queries (trimmed to remaining budget)
    assert call_count <= 2


@pytest.mark.asyncio
async def test_wide_research_preserves_reserved_follow_up_budget() -> None:
    """wide_research should leave reserve calls for follow-up verification."""
    engine = AsyncMock()
    engine.search = AsyncMock(return_value=_make_search_result())
    engine.provider_name = "test"
    tool = SearchTool(search_engine=engine)

    # Leave only 3 API calls; implementation should reserve 2 for follow-up.
    tool._budget.record_api_call(tool._budget._max_api - 3)

    call_count = 0

    async def counting_execute(query: str, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _make_search_result(query)

    tool._execute_typed_search = counting_execute

    await tool.wide_research(
        topic="reserve budget test",
        queries=["q1", "q2", "q3"],
    )

    assert call_count <= 1


@pytest.mark.asyncio
async def test_wide_research_records_invocation() -> None:
    """wide_research records the invocation in budget tracker."""
    engine = AsyncMock()
    engine.search = AsyncMock(return_value=_make_search_result())
    engine.provider_name = "test"
    tool = SearchTool(search_engine=engine)
    tool._execute_typed_search = AsyncMock(return_value=_make_search_result())

    initial_wide = tool._budget._wide_calls
    await tool.wide_research(topic="test", queries=["q1"])
    assert tool._budget._wide_calls == initial_wide + 1


@pytest.mark.asyncio
async def test_wide_research_skips_pdf_urls_before_spider_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = AsyncMock()
    engine.provider_name = "test"
    scraper = AsyncMock()
    scraper.fetch_batch = AsyncMock(return_value=[])

    tool = SearchTool(search_engine=engine, scraper=scraper)
    tool._execute_typed_search = AsyncMock(
        return_value=ToolResult.ok(
            data=SearchResults(
                query="test",
                total_results=2,
                results=[
                    SearchResultItem(
                        title="PDF result",
                        link="https://example.com/report.pdf",
                        snippet="pdf snippet",
                    ),
                    SearchResultItem(
                        title="HTML result",
                        link="https://example.com/post",
                        snippet="html snippet",
                    ),
                ],
            )
        )
    )

    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: MagicMock(scraping_spider_enabled=True, scraping_spider_top_k=5),
    )

    await tool.wide_research(topic="test", queries=["test"])

    scraper.fetch_batch.assert_awaited_once_with(["https://example.com/post"])


# ---------------------------------------------------------------------------
# _execute_typed_search budget enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_typed_search_records_api_call() -> None:
    """_execute_typed_search records API call in budget after successful search."""
    engine = AsyncMock()
    engine.search = AsyncMock(return_value=_make_search_result())
    engine.provider_name = "serper"
    tool = SearchTool(search_engine=engine)

    initial = tool._budget._api_calls
    await tool._execute_typed_search("test query")
    assert tool._budget._api_calls == initial + 1


@pytest.mark.asyncio
async def test_execute_typed_search_blocked_by_budget() -> None:
    """_execute_typed_search returns error when budget is exhausted."""
    engine = AsyncMock()
    engine.search = AsyncMock(return_value=_make_search_result())
    tool = SearchTool(search_engine=engine)
    tool._budget.record_api_call(tool._budget._max_api)

    result = await tool._execute_typed_search("test query")

    assert result.success is False
    assert "budget exhausted" in result.message.lower()
    # Verify the engine was never called
    engine.search.assert_not_called()


@pytest.mark.asyncio
async def test_execute_typed_search_quota_failure_falls_back_to_browser() -> None:
    """Quota-exhausted API failures should degrade to browser search when available."""
    engine = AsyncMock()
    engine.search = AsyncMock(
        return_value=ToolResult(success=False, message='HTTP 400: {"message":"Not enough credits"}')
    )
    engine.provider_name = "serper"

    tool = SearchTool(search_engine=engine, browser=MagicMock())
    fallback_result = ToolResult(success=True, message="fallback result", data=SearchResults(query="q"))
    tool._search_via_browser = AsyncMock(return_value=fallback_result)

    result = await tool._execute_typed_search("quota fallback query", search_type=SearchType.INFO)

    assert result.success is True
    assert "fallback" in (result.message or "").lower()
    tool._search_via_browser.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_hit_does_not_consume_budget() -> None:
    """Cached results do not consume API budget."""
    engine = AsyncMock()
    engine.search = AsyncMock(return_value=_make_search_result())
    engine.provider_name = "serper"
    tool = SearchTool(search_engine=engine)

    # First call — hits API
    await tool._execute_typed_search("cached query")
    assert tool._budget._api_calls == 1

    # Second call — should hit cache, not increment budget
    await tool._execute_typed_search("cached query")
    assert tool._budget._api_calls == 1
    # Verify engine was only called once (second call served from cache)
    assert engine.search.call_count == 1
