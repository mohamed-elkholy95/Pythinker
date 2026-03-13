"""Tests for BrowserWorkflowService."""

from types import SimpleNamespace

import pytest

from app.application.services.browser_workflow_service import BrowserWorkflowService
from app.domain.external.scraper import ScrapedContent
from app.domain.external.stealth_types import ProxyHealth, ProxyStatus, StealthMode


class _FakeScraper:
    def __init__(self) -> None:
        self.calls: list[tuple[str, StealthMode]] = []
        self.cache_result = ScrapedContent(
            success=True,
            url="https://example.com",
            text="cached content",
            html="<html>cached content</html>",
            tier_used="cache",
        )
        self.mode_results: dict[StealthMode, ScrapedContent] = {
            StealthMode.HTTP: ScrapedContent(success=False, url="https://example.com", text="", error="blocked"),
            StealthMode.STEALTH: ScrapedContent(
                success=True,
                url="https://example.com/final",
                text="stealth content",
                html="<html>stealth content</html>",
                tier_used="stealthy",
            ),
        }

    async def fetch_cached(self, url: str, **kwargs: object) -> ScrapedContent:
        self.calls.append(("cached", kwargs.get("mode", StealthMode.HTTP)))  # type: ignore[arg-type]
        return self.cache_result

    async def fetch_with_mode(self, url: str, mode: StealthMode, **kwargs: object) -> ScrapedContent:
        self.calls.append(("mode", mode))
        return self.mode_results[mode]

    def get_proxy_health(self) -> dict[str, ProxyHealth]:
        return {
            "http://proxy1:8080": ProxyHealth(
                proxy_url="http://proxy1:8080",
                status=ProxyStatus.HEALTHY,
                success_count=4,
            )
        }

    async def get_cache_stats(self) -> dict[str, object]:
        return {"l1_size": 1, "l1_max_size": 100, "l2_enabled": False, "l2_ttl": 300}

    async def invalidate_cache(self, url: str | None = None) -> int:
        return 3


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        stealth_cloudflare_enabled=True,
        scraping_cache_enabled=True,
        scraping_batch_max_concurrency=3,
    )


@pytest.mark.asyncio
async def test_get_capabilities_returns_available_modes_and_stats() -> None:
    service = BrowserWorkflowService(scraper=_FakeScraper(), settings=_settings())

    capabilities = await service.get_capabilities()

    assert capabilities["available_modes"] == ["http", "dynamic", "stealth", "cloudflare"]
    assert capabilities["cache_enabled"] is True
    assert capabilities["cache"]["l1_size"] == 1
    assert capabilities["proxy_health"]["http://proxy1:8080"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_fetch_with_escalation_uses_next_mode_until_success() -> None:
    scraper = _FakeScraper()
    scraper.cache_result = ScrapedContent(success=False, url="https://example.com", text="", error="blocked")
    service = BrowserWorkflowService(scraper=scraper, settings=_settings())

    result = await service.fetch_with_escalation(
        "https://example.com",
        {"mode": StealthMode.HTTP},
    )

    assert result["mode_used"] == StealthMode.STEALTH
    assert result["content"] == "<html>stealth content</html>"
    assert scraper.calls == [("cached", StealthMode.HTTP), ("mode", StealthMode.STEALTH)]


@pytest.mark.asyncio
async def test_fetch_with_progress_yields_start_and_completion_events() -> None:
    service = BrowserWorkflowService(scraper=_FakeScraper(), settings=_settings())

    events = [event async for event in service.fetch_with_progress("https://example.com", StealthMode.HTTP)]

    assert [event["phase"] for event in events] == ["started", "fetching", "completed"]
    assert all("event_id" in event for event in events)
    assert events[-1]["tier_used"] == "cache"
    assert events[-1]["from_cache"] is True


@pytest.mark.asyncio
async def test_fetch_with_progress_suggests_next_mode_on_failure() -> None:
    scraper = _FakeScraper()
    scraper.cache_result = ScrapedContent(success=False, url="https://example.com", text="", error="blocked")
    scraper.mode_results[StealthMode.HTTP] = ScrapedContent(
        success=False,
        url="https://example.com",
        text="",
        error="blocked",
        tier_used="http",
    )
    service = BrowserWorkflowService(scraper=scraper, settings=_settings())

    events = [event async for event in service.fetch_with_progress("https://example.com", StealthMode.HTTP)]

    assert events[-1]["phase"] == "failed"
    assert events[-1]["suggested_mode"] == "stealth"


@pytest.mark.asyncio
async def test_invalidate_cache_delegates_to_scraper() -> None:
    service = BrowserWorkflowService(scraper=_FakeScraper(), settings=_settings())

    assert await service.invalidate_cache("https://example.com") == 3


@pytest.mark.asyncio
async def test_fetch_with_progress_invalid_mode_falls_back_to_http() -> None:
    service = BrowserWorkflowService(scraper=_FakeScraper(), settings=_settings())

    events = [event async for event in service.fetch_with_progress("https://example.com", "invalid-mode")]

    assert events[0]["mode"] == "http"
    assert events[-1]["tier_used"] == "cache"
