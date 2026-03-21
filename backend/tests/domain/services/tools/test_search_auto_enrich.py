"""Tests for SearchTool auto-enrichment of info_search_web results."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.search import SearchTool

# Patch target: get_settings is imported inline in search.py methods,
# so we patch the source in app.core.config.
_SETTINGS_PATCH = "app.core.config.get_settings"


def _make_items(count: int = 5) -> list[SearchResultItem]:
    """Create N search result items with short snippets."""
    return [
        SearchResultItem(
            title=f"Result {i}",
            link=f"https://example{i}.com/page",
            snippet=f"Short snippet {i}.",
        )
        for i in range(count)
    ]


def _make_search_data(count: int = 5) -> SearchResults:
    return SearchResults(
        query="test query",
        date_range=None,
        total_results=count,
        results=_make_items(count),
    )


def _make_scraper_response(urls: list[str]) -> list[MagicMock]:
    """Build fake scraper.fetch_batch() results with ~2000-char content."""
    results = []
    for url in urls:
        r = MagicMock()
        r.url = url
        r.success = True
        r.text = f"Full page content for {url}. " * 100  # >200 chars
        r.title = f"Page Title for {url}"
        results.append(r)
    return results


def _default_settings(**overrides) -> MagicMock:
    """Create a MagicMock settings object with all required attributes."""
    defaults = {
        "max_search_api_calls_per_task": 50,
        "max_wide_research_calls_per_task": 5,
        "max_wide_research_queries": 6,
        "max_wide_research_queries_complex": 10,
        "search_dedup_skip_existing": False,
        "search_quota_manager_enabled": False,
        "search_auto_enrich_enabled": True,
        "search_auto_enrich_top_k": 5,
        "search_auto_enrich_snippet_chars": 2000,
        "scraping_spider_enabled": False,
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


@pytest.fixture
def search_tool(mock_search_engine, mock_scraper):
    with patch(_SETTINGS_PATCH) as mock_gs:
        mock_gs.return_value = _default_settings()
        return SearchTool(
            search_engine=mock_search_engine,
            scraper=mock_scraper,
        )


class TestAutoEnrichResults:
    """Unit tests for _auto_enrich_results()."""

    @pytest.mark.asyncio
    async def test_enriches_top_k_results(self, search_tool, mock_scraper):
        """Should fetch and replace snippets for top-K URLs."""
        data = _make_search_data(5)
        urls = [item.link for item in data.results]
        mock_scraper.fetch_batch.return_value = _make_scraper_response(urls)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            count = await search_tool._auto_enrich_results(data)

        assert count == 5
        for item in data.results:
            assert len(item.snippet) > 50
            assert "Full page content" in item.snippet

    @pytest.mark.asyncio
    async def test_respects_snippet_char_limit(self, search_tool, mock_scraper):
        """Enriched snippets should be capped at search_auto_enrich_snippet_chars."""
        data = _make_search_data(1)
        url = data.results[0].link
        response = _make_scraper_response([url])
        response[0].text = "X" * 5000  # Exceeds 2000 limit
        mock_scraper.fetch_batch.return_value = response

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            await search_tool._auto_enrich_results(data)

        assert len(data.results[0].snippet) == 2000

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self, search_tool, mock_scraper):
        """Should return 0 when search_auto_enrich_enabled is False."""
        data = _make_search_data(3)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings(search_auto_enrich_enabled=False)
            count = await search_tool._auto_enrich_results(data)

        assert count == 0
        mock_scraper.fetch_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_without_scraper(self, mock_search_engine):
        """Should return 0 when no scraper is available."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(search_engine=mock_search_engine, scraper=None)

        data = _make_search_data(3)
        count = await tool._auto_enrich_results(data)
        assert count == 0

    @pytest.mark.asyncio
    async def test_skips_pdf_urls(self, search_tool, mock_scraper):
        """PDF URLs should be filtered out of enrichment candidates."""
        data = _make_search_data(3)
        data.results[0].link = "https://example.com/report.pdf"
        data.results[1].link = "https://example.com/page"
        data.results[2].link = "https://example.com/doc.PDF"

        non_pdf_urls = ["https://example.com/page"]
        mock_scraper.fetch_batch.return_value = _make_scraper_response(non_pdf_urls)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            count = await search_tool._auto_enrich_results(data)

        called_urls = mock_scraper.fetch_batch.call_args[0][0]
        assert "https://example.com/report.pdf" not in called_urls
        assert "https://example.com/doc.PDF" not in called_urls
        assert count == 1

    @pytest.mark.asyncio
    async def test_skips_denied_domains(self, search_tool, mock_scraper):
        """URLs on the spider denylist should be excluded from enrichment."""
        data = _make_search_data(3)
        data.results[0].link = "https://www.reddit.com/r/python/comments/abc"
        data.results[1].link = "https://x.com/user/status/123"
        data.results[2].link = "https://example.com/valid"

        mock_scraper.fetch_batch.return_value = _make_scraper_response(["https://example.com/valid"])

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            count = await search_tool._auto_enrich_results(data)

        called_urls = mock_scraper.fetch_batch.call_args[0][0]
        assert len(called_urls) == 1
        assert called_urls[0] == "https://example.com/valid"
        assert count == 1

    @pytest.mark.asyncio
    async def test_handles_fetch_failure_gracefully(self, search_tool, mock_scraper):
        """Scraper errors should not crash the search — returns 0."""
        data = _make_search_data(3)
        mock_scraper.fetch_batch.side_effect = ConnectionError("Network error")

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            count = await search_tool._auto_enrich_results(data)

        assert count == 0
        assert data.results[0].snippet == "Short snippet 0."

    @pytest.mark.asyncio
    async def test_skips_short_fetch_results(self, search_tool, mock_scraper):
        """Fetched content under 200 chars should not replace the original snippet."""
        data = _make_search_data(2)
        urls = [item.link for item in data.results]
        responses = _make_scraper_response(urls)
        responses[0].text = "Too short"  # < 200 chars
        mock_scraper.fetch_batch.return_value = responses

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            count = await search_tool._auto_enrich_results(data)

        assert count == 1
        assert data.results[0].snippet == "Short snippet 0."
        assert "Full page content" in data.results[1].snippet

    @pytest.mark.asyncio
    async def test_fills_empty_titles(self, search_tool, mock_scraper):
        """When a result has no title, enrichment should fill it from the page."""
        data = _make_search_data(1)
        data.results[0].title = ""
        url = data.results[0].link
        mock_scraper.fetch_batch.return_value = _make_scraper_response([url])

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            await search_tool._auto_enrich_results(data)

        assert data.results[0].title != ""
        assert "Page Title" in data.results[0].title


class TestInfoSearchWebEnrichmentIntegration:
    """Integration tests for enrichment wiring into info_search_web."""

    @pytest.mark.asyncio
    async def test_enrichment_note_appended_when_enriched(self, search_tool, mock_search_engine, mock_scraper):
        """System note should mention enrichment count when auto-enrich succeeds."""
        search_data = _make_search_data(3)
        mock_search_engine.search.return_value = ToolResult(
            success=True,
            message="Results",
            data=search_data,
        )
        urls = [item.link for item in search_data.results]
        mock_scraper.fetch_batch.return_value = _make_scraper_response(urls)

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            result = await search_tool.info_search_web("test query")

        assert "enriched" in result.message.lower()
        assert "3 search results" in result.message

    @pytest.mark.asyncio
    async def test_browse_guidance_when_no_enrichment(self, mock_search_engine):
        """When enrichment is off but browser exists, note should encourage browsing."""
        mock_browser = AsyncMock()
        # Sync methods — use MagicMock to avoid unawaited coroutine warnings
        mock_browser.allow_background_browsing = MagicMock()
        mock_browser.is_connected = MagicMock(return_value=True)
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings(search_auto_enrich_enabled=False)
            tool = SearchTool(
                search_engine=mock_search_engine,
                browser=mock_browser,
                scraper=None,
                search_prefer_browser=False,
            )

        mock_search_engine.search.return_value = ToolResult(
            success=True,
            message="Results",
            data=_make_search_data(3),
        )

        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings(search_auto_enrich_enabled=False)
            result = await tool.info_search_web("test query")

        assert "browser_navigate" in result.message.lower()
        assert "Do NOT" not in result.message

    @pytest.mark.asyncio
    async def test_no_note_when_no_browser_and_no_enrichment(self, mock_search_engine):
        """When neither browser nor scraper, no system note should be appended."""
        with patch(_SETTINGS_PATCH) as ms:
            ms.return_value = _default_settings()
            tool = SearchTool(
                search_engine=mock_search_engine,
                browser=None,
                scraper=None,
            )

        mock_search_engine.search.return_value = ToolResult(
            success=True,
            message="Results",
            data=_make_search_data(2),
        )

        result = await tool.info_search_web("test query")

        assert "SYSTEM NOTE" not in result.message
