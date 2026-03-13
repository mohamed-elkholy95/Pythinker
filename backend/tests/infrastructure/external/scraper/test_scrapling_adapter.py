from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain.external.stealth_types import StealthMode
from app.infrastructure.external.scraper.scrapling_adapter import ScraplingAdapter


class _DummyPage:
    def __init__(
        self,
        url: str = "https://example.com",
        text: str = "Deal content",
        title: str = "Deal",
        status: int = 200,
    ) -> None:
        self.url = url
        self.status = status
        self.html_content = "<html><title>Deal</title><body>Deal content</body></html>"
        self._text = text
        self._title = title

    def get_all_text(self, separator: str = "\n\n") -> str:
        return self._text

    def css(self, selector: str):
        if selector == "title":
            return [SimpleNamespace(text=self._title)]
        return []


def _settings(*, http1_fallback_enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        scraping_proxy_enabled=False,
        scraping_proxy_list="",
        scraping_hf_token="",
        scraping_spider_enabled=True,
        scraping_spider_top_k=5,
        scraping_default_impersonate="chrome",
        scraping_http_timeout=15,
        scraping_max_content_length=100000,
        scraping_min_content_length=500,
        scraping_escalation_enabled=True,
        scraping_stealth_enabled=True,
        scraping_headless=True,
        scraping_http1_fallback_enabled=http1_fallback_enabled,
        scraping_cache_enabled=True,
        scraping_cache_l1_max_size=100,
        scraping_cache_l2_ttl=300,
        scraping_cache_key_include_mode=True,
        stealth_proxy_max_failures=3,
        stealth_session_timeout=30000,
        stealth_session_network_idle=True,
        stealth_canvas_noise=True,
        stealth_webrtc_block=True,
        stealth_webgl_enabled=True,
        stealth_google_referer=True,
        stealth_session_max_pages=3,
        stealth_cloudflare_timeout=60,
        stealth_disable_resources=False,
        stealth_session_idle_cleanup_interval=0,
        stealth_session_idle_threshold_seconds=300,
    )


class _FakeContentCache:
    def __init__(self, cached: dict | None = None):
        self.cached = cached
        self.get_calls: list[tuple[str, StealthMode]] = []
        self.set_calls: list[tuple[str, StealthMode, dict]] = []
        self.invalidated: list[str | None] = []

    async def get(self, url: str, mode: StealthMode):
        self.get_calls.append((url, mode))
        return self.cached

    async def set(self, url: str, mode: StealthMode, result: dict) -> None:
        self.set_calls.append((url, mode, result))

    async def invalidate(self, url: str | None = None) -> int:
        self.invalidated.append(url)
        return 2

    async def get_stats(self) -> dict[str, object]:
        return {"l1_size": 1}


class _FakeHealthTracker:
    def __init__(self):
        self.health = {"http://proxy1:8080": "healthy"}

    def get_all_health(self) -> dict[str, str]:
        return self.health


@pytest.mark.asyncio
async def test_fetch_retries_with_http1_when_http2_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP/2 transport failures should trigger one HTTP/1.1 retry before escalation."""
    adapter = ScraplingAdapter(settings=_settings())
    mock_get = AsyncMock(
        side_effect=[
            RuntimeError("curl: (92) HTTP/2 stream 1 was not closed cleanly: INTERNAL_ERROR"),
            _DummyPage(),
        ]
    )
    monkeypatch.setattr("app.infrastructure.external.scraper.scrapling_adapter.AsyncFetcher.get", mock_get)

    result = await adapter.fetch("https://example.com/deals")

    assert result.success is True
    assert result.tier_used == "http"
    assert mock_get.await_count == 2
    first_call = mock_get.await_args_list[0].kwargs
    second_call = mock_get.await_args_list[1].kwargs
    assert "http_version" not in first_call
    assert second_call.get("http_version") is not None


@pytest.mark.asyncio
async def test_fetch_does_not_retry_http1_on_non_http2_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-HTTP/2 failures should not trigger HTTP/1.1 fallback retries."""
    adapter = ScraplingAdapter(settings=_settings())
    mock_get = AsyncMock(side_effect=RuntimeError("DNS resolution failed"))
    monkeypatch.setattr("app.infrastructure.external.scraper.scrapling_adapter.AsyncFetcher.get", mock_get)

    result = await adapter.fetch("https://example.com/deals")

    assert result.success is False
    assert mock_get.await_count == 1


@pytest.mark.asyncio
async def test_fetch_respects_http1_fallback_feature_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """When fallback is disabled, adapter should return original HTTP/2 error after one attempt."""
    adapter = ScraplingAdapter(settings=_settings(http1_fallback_enabled=False))
    mock_get = AsyncMock(side_effect=RuntimeError("HTTP/2 stream 1 INTERNAL_ERROR"))
    monkeypatch.setattr("app.infrastructure.external.scraper.scrapling_adapter.AsyncFetcher.get", mock_get)

    result = await adapter.fetch("https://example.com/deals")

    assert result.success is False
    assert mock_get.await_count == 1


@pytest.mark.asyncio
async def test_fetch_batch_spider_falls_back_for_urls_without_spider_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeSpider:
        def __init__(self, start_urls: list[str], **_: object) -> None:
            self._start_urls = start_urls

        async def stream(self):
            # Spider returns only first URL, second URL must use fallback fetch.
            yield {
                "url": self._start_urls[0],
                "text": "spider content",
                "title": "from spider",
                "status": 200,
            }

    monkeypatch.setattr("app.infrastructure.external.scraper.research_spider.ResearchSpider", _FakeSpider)

    adapter = ScraplingAdapter(settings=_settings())
    adapter.fetch_with_escalation = AsyncMock(
        return_value=SimpleNamespace(
            success=True,
            url="https://b.example.com",
            text="fallback content",
            title="from fallback",
            status_code=200,
            tier_used="dynamic",
        )
    )

    urls = ["https://a.example.com", "https://b.example.com"]
    results = await adapter.fetch_batch(urls)

    assert len(results) == 2
    assert results[0].success is True
    assert results[0].tier_used == "spider"
    assert results[1].success is True
    assert results[1].text == "fallback content"
    assert adapter.fetch_with_escalation.await_count == 1


@pytest.mark.asyncio
async def test_fetch_with_escalation_skips_dynamic_on_terminal_client_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = ScraplingAdapter(settings=_settings())
    mock_get = AsyncMock(return_value=_DummyPage(status=404))
    monkeypatch.setattr("app.infrastructure.external.scraper.scrapling_adapter.AsyncFetcher.get", mock_get)
    dynamic_fetch = AsyncMock()
    stealth_fetch = AsyncMock()
    monkeypatch.setattr(adapter, "_fetch_dynamic", dynamic_fetch)
    monkeypatch.setattr(adapter, "_fetch_stealthy", stealth_fetch)

    result = await adapter.fetch_with_escalation("https://example.com/missing")

    assert result.success is False
    assert result.status_code == 404
    dynamic_fetch.assert_not_awaited()
    stealth_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetch_dynamic_returns_failure_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = ScraplingAdapter(settings=_settings())
    mock_dynamic_fetch = AsyncMock(return_value=_DummyPage(status=404))
    monkeypatch.setattr("scrapling.fetchers.DynamicFetcher.async_fetch", mock_dynamic_fetch)

    result = await adapter._fetch_dynamic("https://example.com/missing")

    assert result.success is False
    assert result.status_code == 404
    assert result.tier_used == "dynamic"
    assert "HTTP 404" in (result.error or "")


@pytest.mark.asyncio
async def test_fetch_stealthy_returns_failure_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = ScraplingAdapter(settings=_settings())
    mock_stealth_fetch = AsyncMock(return_value=_DummyPage(status=404))
    monkeypatch.setattr("scrapling.fetchers.StealthyFetcher.async_fetch", mock_stealth_fetch)

    result = await adapter._fetch_stealthy("https://example.com/missing")

    assert result.success is False
    assert result.status_code == 404
    assert result.tier_used == "stealthy"
    assert "HTTP 404" in (result.error or "")


@pytest.mark.asyncio
async def test_fetch_dynamic_dependency_error_includes_setup_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = ScraplingAdapter(settings=_settings())
    mock_dynamic_fetch = AsyncMock(side_effect=RuntimeError("Executable doesn't exist at /tmp/chromium"))
    monkeypatch.setattr("scrapling.fetchers.DynamicFetcher.async_fetch", mock_dynamic_fetch)

    result = await adapter._fetch_dynamic("https://example.com")

    assert result.success is False
    assert 'pip install "scrapling[fetchers]"' in (result.error or "")
    assert "scrapling install" in (result.error or "")


@pytest.mark.asyncio
async def test_fetch_http_dependency_error_includes_setup_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = ScraplingAdapter(settings=_settings())
    mock_get = AsyncMock(side_effect=RuntimeError("No module named 'playwright'"))
    monkeypatch.setattr("app.infrastructure.external.scraper.scrapling_adapter.AsyncFetcher.get", mock_get)

    result = await adapter.fetch("https://example.com")

    assert result.success is False
    assert 'pip install "scrapling[fetchers]"' in (result.error or "")
    assert "scrapling install" in (result.error or "")


@pytest.mark.asyncio
async def test_fetch_cached_returns_cached_result_without_fetch() -> None:
    cached = {
        "content": "<html>cached</html>",
        "url": "https://example.com",
        "final_url": "https://example.com",
        "mode_used": "http",
        "proxy_used": None,
        "response_time_ms": 1.0,
        "from_cache": True,
        "cloudflare_solved": False,
        "error": None,
    }
    cache = _FakeContentCache(cached=cached)
    adapter = ScraplingAdapter(settings=_settings(), content_cache=cache)
    adapter.fetch = AsyncMock()

    result = await adapter.fetch_cached("https://example.com")

    assert result.success is True
    assert result.tier_used == "cache"
    adapter.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetch_cached_does_not_mutate_cached_entry() -> None:
    cached = {
        "content": "<html>cached</html>",
        "url": "https://example.com",
        "final_url": "https://example.com",
        "mode_used": "http",
        "proxy_used": None,
        "response_time_ms": 1.0,
        "from_cache": False,
        "cloudflare_solved": False,
        "error": None,
    }
    cache = _FakeContentCache(cached=cached)
    adapter = ScraplingAdapter(settings=_settings(), content_cache=cache)

    result = await adapter.fetch_cached("https://example.com")

    assert result.success is True
    assert cached["from_cache"] is False


@pytest.mark.asyncio
async def test_fetch_stealth_session_uses_default_timeout_when_none_passed() -> None:
    adapter = ScraplingAdapter(settings=_settings())
    adapter._stealth_manager.fetch = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "content": "<html>ok</html>",
            "url": "https://example.com",
            "final_url": "https://example.com/final",
            "mode_used": StealthMode.STEALTH,
            "proxy_used": None,
            "response_time_ms": 10.0,
            "from_cache": False,
            "cloudflare_solved": False,
            "error": None,
        }
    )

    result = await adapter.fetch_stealth_session("https://example.com", timeout_ms=None)

    assert result.success is True
    options = adapter._stealth_manager.fetch.await_args.args[1]  # type: ignore[union-attr]
    assert options["timeout_ms"] == 30000


@pytest.mark.asyncio
async def test_invalidate_cache_delegates_to_cache() -> None:
    cache = _FakeContentCache()
    adapter = ScraplingAdapter(settings=_settings(), content_cache=cache)

    deleted = await adapter.invalidate_cache("https://example.com")

    assert deleted == 2
    assert cache.invalidated == ["https://example.com"]


def test_get_proxy_health_returns_tracker_data() -> None:
    tracker = _FakeHealthTracker()
    adapter = ScraplingAdapter(settings=_settings(), health_tracker=tracker)

    assert adapter.get_proxy_health() == {"http://proxy1:8080": "healthy"}
