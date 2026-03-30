"""Tests for mode-aware preview budgets in SearchTool.

Verifies that _schedule_background_preview and _browse_top_results honour
the CompactionProfile for both standard and deep-research modes.  Deep-research
mode (complexity_score >= 0.8) should preview more URLs than standard mode.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.search import CompactionProfile, SearchTool

# Patch target: get_settings is imported inline in search.py methods.
_SETTINGS_PATCH = "app.core.config.get_settings"


def _make_items(count: int = 10) -> list[SearchResultItem]:
    """Create N search result items."""
    return [
        SearchResultItem(
            title=f"Result {i}",
            link=f"https://example{i}.com/page{i}",
            snippet=f"Snippet {i}.",
        )
        for i in range(count)
    ]


def _make_search_data(count: int = 10) -> SearchResults:
    return SearchResults(
        query="deep research topic",
        date_range=None,
        total_results=count,
        results=_make_items(count),
    )


def _default_settings(**overrides) -> MagicMock:
    """Create a MagicMock settings object with all required search attributes."""
    defaults = {
        "max_search_api_calls_per_task": 50,
        "max_search_api_calls_deep_research": 100,
        "max_wide_research_calls_per_task": 5,
        "max_wide_research_queries": 6,
        "max_wide_research_queries_complex": 10,
        "search_dedup_skip_existing": False,
        "search_quota_manager_enabled": False,
        "search_auto_enrich_enabled": True,
        "search_auto_enrich_top_k": 5,
        "search_auto_enrich_top_k_deep": 8,
        "search_auto_enrich_snippet_chars": 2000,
        "search_auto_enrich_snippet_chars_deep": 3000,
        "scraping_spider_enabled": False,
        "browser_background_preview_count": 5,
        "search_preview_count_deep": 8,
        "search_compaction_max_results_deep": 15,
        "search_compaction_max_summaries_deep": 12,
        "search_compaction_summary_snippet_chars_deep": 250,
    }
    defaults.update(overrides)
    s = MagicMock()
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


# ---------------------------------------------------------------------------
# CompactionProfile._get_compaction_profile
# ---------------------------------------------------------------------------


class TestGetCompactionProfile:
    """Verify _get_compaction_profile returns correct profiles per mode."""

    def test_standard_mode_returns_defaults(self) -> None:
        """Standard mode (no complexity_score) returns baseline limits."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=AsyncMock())

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            profile = tool._get_compaction_profile()

        assert profile.preview_count == 5
        assert profile.max_results == 10
        assert profile.max_summaries == 8
        assert profile.summary_snippet_chars == 150
        assert profile.enrich_top_k == 5
        assert profile.enrich_snippet_chars == 2000

    def test_deep_research_mode_returns_expanded_limits(self) -> None:
        """Deep-research mode (complexity >= 0.8) returns higher limits."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=AsyncMock(), complexity_score=0.85)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            profile = tool._get_compaction_profile()

        assert profile.preview_count == 8
        assert profile.max_results == 15
        assert profile.max_summaries == 12
        assert profile.summary_snippet_chars == 250
        assert profile.enrich_top_k == 8
        assert profile.enrich_snippet_chars == 3000

    def test_boundary_complexity_0_8_is_deep(self) -> None:
        """complexity_score exactly 0.8 triggers deep-research profile."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=AsyncMock(), complexity_score=0.8)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            profile = tool._get_compaction_profile()

        assert profile.preview_count == 8

    def test_boundary_complexity_0_79_is_standard(self) -> None:
        """complexity_score 0.79 should use standard profile."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=AsyncMock(), complexity_score=0.79)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            profile = tool._get_compaction_profile()

        assert profile.preview_count == 5

    def test_set_complexity_score_switches_profile(self) -> None:
        """set_complexity_score() can upgrade from standard to deep profile."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=AsyncMock())

        # Verify standard initially
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            assert tool._get_compaction_profile().preview_count == 5

        # Upgrade to deep
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool.set_complexity_score(0.9)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            assert tool._get_compaction_profile().preview_count == 8

    def test_none_complexity_is_standard(self) -> None:
        """None complexity_score always uses standard profile."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=AsyncMock(), complexity_score=None)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            profile = tool._get_compaction_profile()

        assert profile.preview_count == 5


# ---------------------------------------------------------------------------
# _schedule_background_preview mode-aware count
# ---------------------------------------------------------------------------


class TestScheduleBackgroundPreview:
    """Verify preview scheduling uses mode-aware URL count."""

    @pytest.mark.asyncio
    async def test_standard_mode_previews_5_urls(self) -> None:
        """Standard mode schedules preview for 5 URLs (default)."""
        engine = AsyncMock()
        engine.provider_name = "test"
        browser = AsyncMock()
        browser.allow_background_browsing = MagicMock()
        browser.is_connected = MagicMock(return_value=True)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=engine, browser=browser)

        data = _make_search_data(10)
        # Mock _browse_top_results so we don't need a real browser
        browsed_urls: list[str] = []

        async def mock_browse(search_data, count=5):
            items = search_data.results if hasattr(search_data, "results") else []
            browsed_urls.extend([item.link for item in items[:count]])

        tool._browse_top_results = mock_browse

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            await tool._schedule_background_preview(data)

        # Wait for the fire-and-forget task to complete
        await tool._current_browse_task
        assert len(browsed_urls) == 5

    @pytest.mark.asyncio
    async def test_deep_research_mode_previews_8_urls(self) -> None:
        """Deep-research mode schedules preview for 8 URLs."""
        engine = AsyncMock()
        engine.provider_name = "test"
        browser = AsyncMock()
        browser.allow_background_browsing = MagicMock()
        browser.is_connected = MagicMock(return_value=True)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=engine, browser=browser, complexity_score=0.85)

        data = _make_search_data(12)
        browsed_count: int = 0

        async def mock_browse(search_data, count=5):
            nonlocal browsed_count
            browsed_count = count

        tool._browse_top_results = mock_browse

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            await tool._schedule_background_preview(data)

        await tool._current_browse_task
        assert browsed_count == 8

    @pytest.mark.asyncio
    async def test_explicit_count_overrides_profile(self) -> None:
        """Explicitly passed count overrides profile-based default."""
        engine = AsyncMock()
        engine.provider_name = "test"
        browser = AsyncMock()
        browser.allow_background_browsing = MagicMock()

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=engine, browser=browser)

        data = _make_search_data(10)
        passed_count: int = 0

        async def mock_browse(search_data, count=5):
            nonlocal passed_count
            passed_count = count

        tool._browse_top_results = mock_browse

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            await tool._schedule_background_preview(data, count=3)

        await tool._current_browse_task
        assert passed_count == 3


# ---------------------------------------------------------------------------
# wide_research result cap is mode-aware
# ---------------------------------------------------------------------------


class TestWideResearchResultCap:
    """Verify wide_research caps results using CompactionProfile."""

    @pytest.mark.asyncio
    async def test_standard_mode_caps_at_10(self) -> None:
        """Standard mode caps wide_research results at 10."""
        engine = AsyncMock()
        engine.provider_name = "test"

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=engine)

        # Return 20 unique items per search to exceed the cap
        items_20 = [
            SearchResultItem(
                title=f"Result {i}",
                link=f"https://unique{i}.example.com/page",
                snippet=f"Snippet {i}.",
            )
            for i in range(20)
        ]

        async def mock_execute(query, *args, **kwargs):
            return ToolResult(
                success=True,
                message="ok",
                data=SearchResults(
                    query=query,
                    total_results=20,
                    results=items_20,
                ),
            )

        tool._execute_typed_search = mock_execute

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            result = await tool.wide_research(topic="test", queries=["q1"])

        assert result.success is True
        assert len(result.data.results) == 10

    @pytest.mark.asyncio
    async def test_deep_research_mode_caps_at_15(self) -> None:
        """Deep-research mode caps wide_research results at 15."""
        engine = AsyncMock()
        engine.provider_name = "test"

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=engine, complexity_score=0.9)

        items_20 = [
            SearchResultItem(
                title=f"Result {i}",
                link=f"https://unique{i}.example.com/page",
                snippet=f"Snippet {i}.",
            )
            for i in range(20)
        ]

        async def mock_execute(query, *args, **kwargs):
            return ToolResult(
                success=True,
                message="ok",
                data=SearchResults(
                    query=query,
                    total_results=20,
                    results=items_20,
                ),
            )

        tool._execute_typed_search = mock_execute

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            result = await tool.wide_research(topic="test", queries=["q1"])

        assert result.success is True
        assert len(result.data.results) == 15


# ---------------------------------------------------------------------------
# wide_research summary formatting is mode-aware
# ---------------------------------------------------------------------------


class TestWideResearchSummaryFormatting:
    """Verify wide_research message summaries use CompactionProfile."""

    @pytest.mark.asyncio
    async def test_standard_mode_summaries_at_150_chars(self) -> None:
        """Standard mode: summary snippets capped at 150 chars."""
        engine = AsyncMock()
        engine.provider_name = "test"

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=engine)

        long_items = [
            SearchResultItem(
                title=f"Result {i}",
                link=f"https://example{i}.com",
                snippet="X" * 500,
            )
            for i in range(10)
        ]

        async def mock_execute(query, *args, **kwargs):
            return ToolResult(
                success=True,
                message="ok",
                data=SearchResults(query=query, total_results=10, results=long_items),
            )

        tool._execute_typed_search = mock_execute

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            result = await tool.wide_research(topic="test", queries=["q1"])

        # Count summary lines (format: "1. [Title](url)\n   snippet...")
        # Each snippet in the message should be <= 150 chars
        lines = result.message.split("\n")
        for line in lines:
            if line.startswith("   ") and line.strip():
                assert len(line.strip()) <= 150

    @pytest.mark.asyncio
    async def test_deep_research_mode_summaries_at_250_chars(self) -> None:
        """Deep-research mode: summary snippets capped at 250 chars."""
        engine = AsyncMock()
        engine.provider_name = "test"

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=engine, complexity_score=0.85)

        long_items = [
            SearchResultItem(
                title=f"Result {i}",
                link=f"https://example{i}.com",
                snippet="Y" * 500,
            )
            for i in range(10)
        ]

        async def mock_execute(query, *args, **kwargs):
            return ToolResult(
                success=True,
                message="ok",
                data=SearchResults(query=query, total_results=10, results=long_items),
            )

        tool._execute_typed_search = mock_execute

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            result = await tool.wide_research(topic="test", queries=["q1"])

        lines = result.message.split("\n")
        deep_snippets = [line for line in lines if line.startswith("   ") and line.strip()]
        for snippet_line in deep_snippets:
            # Should be > 150 but <= 250 (deep-research mode)
            assert len(snippet_line.strip()) <= 250


# ---------------------------------------------------------------------------
# CompactionProfile frozen dataclass
# ---------------------------------------------------------------------------


class TestCompactionProfileFrozen:
    """Verify CompactionProfile is immutable."""

    def test_frozen_raises_on_setattr(self) -> None:
        """CompactionProfile should be frozen (immutable)."""
        profile = CompactionProfile(
            max_results=10,
            max_summaries=8,
            summary_snippet_chars=150,
            enrich_top_k=5,
            enrich_snippet_chars=2000,
            preview_count=5,
        )
        with pytest.raises(AttributeError):
            profile.preview_count = 99  # type: ignore[misc]
