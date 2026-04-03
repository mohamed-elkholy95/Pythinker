"""Tests for mode-aware auto-enrichment budgets in SearchTool.

Verifies that _auto_enrich_results and the info_search_web enrichment wiring
honour the CompactionProfile for both standard and deep-research modes.
Deep-research mode (complexity_score >= 0.8) enriches more URLs with longer
snippets than standard mode.  Defaults are unchanged.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.search import SearchTool

# Patch target: get_settings is imported inline in search.py methods.
_SETTINGS_PATCH = "app.core.config.get_settings"


def _make_items(count: int = 10) -> list[SearchResultItem]:
    """Create N search result items with short snippets."""
    return [
        SearchResultItem(
            title=f"Result {i}",
            link=f"https://example{i}.com/page",
            snippet=f"Short snippet {i}.",
        )
        for i in range(count)
    ]


def _make_search_data(count: int = 10) -> SearchResults:
    return SearchResults(
        query="test query",
        date_range=None,
        total_results=count,
        results=_make_items(count),
    )


def _make_scraper_response(urls: list[str], text_len: int = 2500) -> list[MagicMock]:
    """Build fake scraper.fetch_batch() results with sufficient content."""
    results = []
    for url in urls:
        r = MagicMock()
        r.url = url
        r.success = True
        r.text = f"Full page content for {url}. " * (text_len // 40)
        r.title = f"Page Title for {url}"
        results.append(r)
    return results


def _default_settings(**overrides) -> MagicMock:
    """Create a MagicMock settings object with all required attributes."""
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
        "search_auto_enrich_skip_dynamic_fallback": True,
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


@pytest.fixture
def mock_search_engine():
    engine = AsyncMock()
    engine.provider_name = "test"
    return engine


@pytest.fixture
def mock_scraper():
    return AsyncMock()


# ---------------------------------------------------------------------------
# _auto_enrich_results: standard vs deep-research budgets
# ---------------------------------------------------------------------------


class TestAutoEnrichStandardMode:
    """Standard mode (no complexity_score) keeps existing enrichment budgets."""

    @pytest.mark.asyncio
    async def test_enriches_top_5_by_default(self, mock_search_engine, mock_scraper) -> None:
        """Standard mode enriches at most 5 URLs (search_auto_enrich_top_k)."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=mock_search_engine, scraper=mock_scraper)

        data = _make_search_data(10)
        urls = [item.link for item in data.results[:5]]
        mock_scraper.fetch_batch.return_value = _make_scraper_response(urls)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            await tool._auto_enrich_results(data)

        called_urls = mock_scraper.fetch_batch.call_args[0][0]
        assert len(called_urls) == 5

    @pytest.mark.asyncio
    async def test_snippet_capped_at_2000_chars(self, mock_search_engine, mock_scraper) -> None:
        """Standard mode caps enriched snippets at 2000 chars."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=mock_search_engine, scraper=mock_scraper)

        data = _make_search_data(1)
        url = data.results[0].link
        response = _make_scraper_response([url], text_len=10000)
        mock_scraper.fetch_batch.return_value = response

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            await tool._auto_enrich_results(data)

        assert len(data.results[0].snippet) == 2000

    @pytest.mark.asyncio
    async def test_disabled_returns_zero(self, mock_search_engine, mock_scraper) -> None:
        """When search_auto_enrich_enabled is False, no enrichment occurs."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings(search_auto_enrich_enabled=False)
            tool = SearchTool(search_engine=mock_search_engine, scraper=mock_scraper)

        data = _make_search_data(3)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings(search_auto_enrich_enabled=False)
            count = await tool._auto_enrich_results(data)

        assert count == 0
        mock_scraper.fetch_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_scraper_returns_zero(self, mock_search_engine) -> None:
        """Without a scraper, enrichment is skipped."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=mock_search_engine, scraper=None)

        data = _make_search_data(3)
        count = await tool._auto_enrich_results(data)
        assert count == 0


class TestAutoEnrichDeepResearchMode:
    """Deep-research mode (complexity >= 0.8) uses expanded enrichment budgets."""

    @pytest.mark.asyncio
    async def test_enriches_top_8_urls(self, mock_search_engine, mock_scraper) -> None:
        """Deep-research mode enriches up to 8 URLs (search_auto_enrich_top_k_deep)."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(
                search_engine=mock_search_engine,
                scraper=mock_scraper,
                complexity_score=0.85,
            )

        data = _make_search_data(12)
        urls = [item.link for item in data.results[:8]]
        mock_scraper.fetch_batch.return_value = _make_scraper_response(urls)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            count = await tool._auto_enrich_results(data)

        assert count == 8
        called_urls = mock_scraper.fetch_batch.call_args[0][0]
        assert len(called_urls) == 8

    @pytest.mark.asyncio
    async def test_snippet_capped_at_3000_chars(self, mock_search_engine, mock_scraper) -> None:
        """Deep-research mode caps enriched snippets at 3000 chars."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(
                search_engine=mock_search_engine,
                scraper=mock_scraper,
                complexity_score=0.9,
            )

        data = _make_search_data(1)
        url = data.results[0].link
        response = _make_scraper_response([url], text_len=10000)
        mock_scraper.fetch_batch.return_value = response

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            await tool._auto_enrich_results(data)

        assert len(data.results[0].snippet) == 3000

    @pytest.mark.asyncio
    async def test_boundary_0_8_activates_deep_budgets(self, mock_search_engine, mock_scraper) -> None:
        """complexity_score exactly 0.8 activates deep-research enrichment."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(
                search_engine=mock_search_engine,
                scraper=mock_scraper,
                complexity_score=0.8,
            )

        data = _make_search_data(10)
        urls = [item.link for item in data.results[:8]]
        mock_scraper.fetch_batch.return_value = _make_scraper_response(urls)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            count = await tool._auto_enrich_results(data)

        called_urls = mock_scraper.fetch_batch.call_args[0][0]
        assert len(called_urls) == 8
        assert count == 8

    @pytest.mark.asyncio
    async def test_boundary_0_79_uses_standard_budgets(self, mock_search_engine, mock_scraper) -> None:
        """complexity_score 0.79 should use standard enrichment budgets."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(
                search_engine=mock_search_engine,
                scraper=mock_scraper,
                complexity_score=0.79,
            )

        data = _make_search_data(10)
        urls = [item.link for item in data.results[:5]]
        mock_scraper.fetch_batch.return_value = _make_scraper_response(urls)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            count = await tool._auto_enrich_results(data)

        called_urls = mock_scraper.fetch_batch.call_args[0][0]
        assert len(called_urls) == 5
        assert count == 5

    @pytest.mark.asyncio
    async def test_custom_deep_settings_respected(self, mock_search_engine, mock_scraper) -> None:
        """Custom config values for deep-research mode are honoured."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings(
                search_auto_enrich_top_k_deep=12,
                search_auto_enrich_snippet_chars_deep=5000,
            )
            tool = SearchTool(
                search_engine=mock_search_engine,
                scraper=mock_scraper,
                complexity_score=0.95,
            )

        data = _make_search_data(15)
        urls = [item.link for item in data.results[:12]]
        mock_scraper.fetch_batch.return_value = _make_scraper_response(urls, text_len=10000)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings(
                search_auto_enrich_top_k_deep=12,
                search_auto_enrich_snippet_chars_deep=5000,
            )
            count = await tool._auto_enrich_results(data)

        assert count == 12
        assert len(data.results[0].snippet) == 5000

    @pytest.mark.asyncio
    async def test_fewer_results_than_top_k(self, mock_search_engine, mock_scraper) -> None:
        """When fewer results exist than top_k, enrich only what's available."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(
                search_engine=mock_search_engine,
                scraper=mock_scraper,
                complexity_score=0.85,
            )

        data = _make_search_data(3)
        urls = [item.link for item in data.results[:3]]
        mock_scraper.fetch_batch.return_value = _make_scraper_response(urls)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            count = await tool._auto_enrich_results(data)

        assert count == 3
        called_urls = mock_scraper.fetch_batch.call_args[0][0]
        assert len(called_urls) == 3

    @pytest.mark.asyncio
    async def test_pdf_urls_skipped_in_deep_mode(self, mock_search_engine, mock_scraper) -> None:
        """PDF URLs should be filtered out even in deep-research mode."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(
                search_engine=mock_search_engine,
                scraper=mock_scraper,
                complexity_score=0.9,
            )

        data = _make_search_data(5)
        data.results[0].link = "https://example.com/report.pdf"
        data.results[2].link = "https://example.com/doc.PDF"

        non_pdf_urls = [item.link for item in data.results if not item.link.lower().endswith(".pdf")]
        mock_scraper.fetch_batch.return_value = _make_scraper_response(non_pdf_urls)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            await tool._auto_enrich_results(data)

        called_urls = mock_scraper.fetch_batch.call_args[0][0]
        assert "https://example.com/report.pdf" not in called_urls
        assert "https://example.com/doc.PDF" not in called_urls

    @pytest.mark.asyncio
    async def test_denied_domains_skipped_in_deep_mode(self, mock_search_engine, mock_scraper) -> None:
        """Spider-denylisted domains are skipped even in deep-research mode."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(
                search_engine=mock_search_engine,
                scraper=mock_scraper,
                complexity_score=0.9,
            )

        data = _make_search_data(3)
        data.results[0].link = "https://www.reddit.com/r/python/comments/abc"
        data.results[1].link = "https://x.com/user/status/123"
        data.results[2].link = "https://example.com/valid"

        mock_scraper.fetch_batch.return_value = _make_scraper_response(["https://example.com/valid"])

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            count = await tool._auto_enrich_results(data)

        called_urls = mock_scraper.fetch_batch.call_args[0][0]
        assert len(called_urls) == 1
        assert called_urls[0] == "https://example.com/valid"
        assert count == 1

    @pytest.mark.asyncio
    async def test_scraper_error_returns_zero(self, mock_search_engine, mock_scraper) -> None:
        """Scraper failure in deep-research mode returns 0 without crashing."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(
                search_engine=mock_search_engine,
                scraper=mock_scraper,
                complexity_score=0.9,
            )

        data = _make_search_data(5)
        mock_scraper.fetch_batch.side_effect = ConnectionError("Network error")

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            count = await tool._auto_enrich_results(data)

        assert count == 0
        assert data.results[0].snippet == "Short snippet 0."


# ---------------------------------------------------------------------------
# info_search_web enrichment integration: mode-aware
# ---------------------------------------------------------------------------


class TestInfoSearchWebEnrichmentModeAware:
    """Integration tests verifying enrichment note reflects mode-aware counts."""

    @pytest.mark.asyncio
    async def test_standard_mode_enrichment_note(self, mock_search_engine, mock_scraper) -> None:
        """Standard mode: enrichment note shows count up to 5."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(
                search_engine=mock_search_engine,
                scraper=mock_scraper,
            )

        search_data = _make_search_data(5)
        mock_search_engine.search.return_value = ToolResult(
            success=True,
            message="Results",
            data=search_data,
        )
        urls = [item.link for item in search_data.results[:5]]
        mock_scraper.fetch_batch.return_value = _make_scraper_response(urls)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            result = await tool.info_search_web("test query")

        assert result.success is True
        assert "enriched" in result.message.lower()
        assert "5 search results" in result.message

    @pytest.mark.asyncio
    async def test_browse_guidance_when_no_enrichment(self, mock_search_engine, mock_scraper):
        """When enrichment is off but browser exists, note should encourage browsing."""
        mock_browser = AsyncMock()
        # Sync methods — use MagicMock to avoid unawaited coroutine warnings
        mock_browser.allow_background_browsing = MagicMock()
        mock_browser.is_connected = MagicMock(return_value=True)
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings(search_auto_enrich_enabled=False)
            tool = SearchTool(
                search_engine=mock_search_engine,
                scraper=mock_scraper,
                complexity_score=0.9,
            )

        mock_search_engine.search.return_value = ToolResult(
            success=True,
            message="Results",
            data=_make_search_data(5),
        )

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings(search_auto_enrich_enabled=False)
            result = await tool.info_search_web("test query")

        mock_scraper.fetch_batch.assert_not_called()
        assert "enriched" not in (result.message or "").lower()
