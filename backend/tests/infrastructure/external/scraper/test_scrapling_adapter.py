from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.external.scraper.scrapling_adapter import ScraplingAdapter


class _DummyPage:
    def __init__(self, url: str = "https://example.com", text: str = "Deal content", title: str = "Deal") -> None:
        self.url = url
        self.status = 200
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
        scraping_default_impersonate="chrome",
        scraping_http_timeout=15,
        scraping_max_content_length=100000,
        scraping_http1_fallback_enabled=http1_fallback_enabled,
    )


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
