"""Scrapling implementation of the Scraper Protocol.

Infrastructure layer — only this file imports from scrapling directly.
Swapping the scraping library means changing only this file.

Tier 1: AsyncFetcher (curl_cffi, TLS fingerprint impersonation) — ~50-300ms
Tier 2: DynamicFetcher (Playwright Chromium, JS rendering) — ~2-4s
Tier 3: StealthyFetcher (hardened Playwright, Cloudflare bypass) — ~4-8s
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from scrapling.fetchers import AsyncFetcher

from app.domain.external.scraper import ScrapedContent, StructuredData
from app.infrastructure.external.scraper.escalation import should_escalate

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)


class ScraplingAdapter:
    """Scrapling implementation of the Scraper Protocol.

    Instantiated once per application via get_scraping_adapter() factory.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._proxy_rotator = None
        if settings.scraping_proxy_enabled and settings.scraping_proxy_list:
            self._init_proxy_rotator(settings.scraping_proxy_list)

    def _init_proxy_rotator(self, proxy_list_str: str) -> None:
        try:
            from scrapling.engines.toolbelt.proxy_rotation import ProxyRotator, cyclic_rotation

            proxies = [p.strip() for p in proxy_list_str.split(",") if p.strip()]
            if proxies:
                self._proxy_rotator = ProxyRotator(proxies=proxies, strategy=cyclic_rotation)
                logger.info(f"Proxy rotator initialised with {len(proxies)} proxies")
        except Exception:
            logger.warning("Failed to initialise ProxyRotator — continuing without proxy rotation", exc_info=True)

    # ── Tier 1: HTTP ──────────────────────────────────────────────────────────

    async def fetch(self, url: str, **kwargs: object) -> ScrapedContent:
        """Tier 1: HTTP fetch with TLS fingerprint impersonation."""
        proxy = self._proxy_rotator.get_proxy() if self._proxy_rotator else None
        try:
            page = await AsyncFetcher.get(
                url,
                impersonate=self._settings.scraping_default_impersonate,
                timeout=self._settings.scraping_http_timeout,
                proxy=proxy,
                follow_redirects=True,
            )
            text = str(page.get_all_text(separator="\n\n"))
            # Trim to configured max
            if len(text) > self._settings.scraping_max_content_length:
                text = text[: self._settings.scraping_max_content_length]

            title_el = page.css("title")
            title = title_el[0].text if title_el else None

            return ScrapedContent(
                success=True,
                url=str(page.url),
                text=text,
                html=str(page.html_content) if hasattr(page, "html_content") else None,
                title=title,
                status_code=page.status,
                tier_used="http",
            )
        except Exception as exc:
            logger.debug(f"Scrapling Tier 1 failed for {url}: {exc}")
            return ScrapedContent(success=False, url=url, text="", error=str(exc), tier_used="http")

    # ── Tier 2: Dynamic (Playwright + JS) ────────────────────────────────────

    async def _fetch_dynamic(self, url: str, **kwargs: object) -> ScrapedContent:
        """Tier 2: Playwright Chromium with full JS rendering."""
        try:
            from scrapling.fetchers import DynamicFetcher

            proxy = self._proxy_rotator.get_proxy() if self._proxy_rotator else None
            page = await DynamicFetcher.async_fetch(
                url,
                headless=self._settings.scraping_headless,
                network_idle=True,
                proxy=proxy,
            )
            text = str(page.get_all_text(separator="\n\n"))
            if len(text) > self._settings.scraping_max_content_length:
                text = text[: self._settings.scraping_max_content_length]

            title_el = page.css("title")
            title = title_el[0].text if title_el else None

            return ScrapedContent(
                success=True,
                url=str(page.url),
                text=text,
                html=str(page.html_content) if hasattr(page, "html_content") else None,
                title=title,
                status_code=page.status,
                tier_used="dynamic",
            )
        except Exception as exc:
            logger.debug(f"Scrapling Tier 2 failed for {url}: {exc}")
            return ScrapedContent(success=False, url=url, text="", error=str(exc), tier_used="dynamic")

    # ── Tier 3: Stealthy (hardened Playwright, Cloudflare bypass) ─────────────

    async def _fetch_stealthy(self, url: str, **kwargs: object) -> ScrapedContent:
        """Tier 3: StealthyFetcher — stealth patches, Cloudflare/Turnstile bypass."""
        try:
            from scrapling.fetchers import StealthyFetcher

            proxy = self._proxy_rotator.get_proxy() if self._proxy_rotator else None
            page = await StealthyFetcher.async_fetch(
                url,
                headless=self._settings.scraping_headless,
                network_idle=True,
                proxy=proxy,
            )
            text = str(page.get_all_text(separator="\n\n"))
            if len(text) > self._settings.scraping_max_content_length:
                text = text[: self._settings.scraping_max_content_length]

            title_el = page.css("title")
            title = title_el[0].text if title_el else None

            return ScrapedContent(
                success=True,
                url=str(page.url),
                text=text,
                html=str(page.html_content) if hasattr(page, "html_content") else None,
                title=title,
                status_code=page.status,
                tier_used="stealthy",
            )
        except Exception as exc:
            logger.debug(f"Scrapling Tier 3 failed for {url}: {exc}")
            return ScrapedContent(success=False, url=url, text="", error=str(exc), tier_used="stealthy")

    # ── Escalation ────────────────────────────────────────────────────────────

    async def fetch_with_escalation(self, url: str, **kwargs: object) -> ScrapedContent:
        """Three-tier escalation: HTTP → Dynamic → Stealthy."""
        min_len = self._settings.scraping_min_content_length

        # Tier 1: HTTP
        result = await self.fetch(url, **kwargs)
        if not should_escalate(result, min_len):
            logger.debug(f"Scrapling Tier 1 resolved {url} ({len(result.text)} chars)")
            return result

        # Tier 2: Dynamic
        if self._settings.scraping_escalation_enabled:
            logger.debug(f"Scrapling escalating to Tier 2 for {url}")
            result = await self._fetch_dynamic(url, **kwargs)
            if not should_escalate(result, min_len):
                logger.debug(f"Scrapling Tier 2 resolved {url} ({len(result.text)} chars)")
                return result

        # Tier 3: Stealthy
        if self._settings.scraping_stealth_enabled:
            logger.debug(f"Scrapling escalating to Tier 3 for {url}")
            result = await self._fetch_stealthy(url, **kwargs)
            if result.success:
                logger.debug(f"Scrapling Tier 3 resolved {url} ({len(result.text)} chars)")
                return result

        # All tiers exhausted — return last result (with error info for fallback)
        logger.debug(f"Scrapling all tiers exhausted for {url}")
        return result

    # ── Structured extraction ─────────────────────────────────────────────────

    async def extract_structured(
        self, url: str, selectors: dict[str, str], **kwargs: object
    ) -> StructuredData:
        """Extract structured data using CSS selectors after fetching via escalation.

        When scraping_adaptive_tracking=True, uses Scrapling's adaptive element
        tracking (SQLite fingerprints) to relocate elements even if CSS selectors
        drift after site redesigns.
        """
        fetched = await self.fetch_with_escalation(url)
        if not fetched.success or not fetched.html:
            return StructuredData(success=False, url=url, data={}, error=fetched.error or "Fetch failed")

        try:
            from scrapling.parser import Adaptor

            adaptive_mode = self._settings.scraping_adaptive_tracking
            adaptor_kwargs: dict = {}

            if adaptive_mode:
                # Configure domain-scoped SQLite fingerprint storage
                import hashlib
                import os
                from urllib.parse import urlparse

                domain = urlparse(url).netloc or "unknown"
                domain_hash = hashlib.md5(domain.encode()).hexdigest()[:12]  # noqa: S324
                storage_dir = self._settings.scraping_adaptive_storage_dir
                os.makedirs(storage_dir, exist_ok=True)
                storage_path = os.path.join(storage_dir, f"{domain_hash}.db")

                from scrapling.core.storage import SQLiteStorageSystem

                adaptor_kwargs["_storage"] = SQLiteStorageSystem(storage_file=storage_path, url=url)

            page = Adaptor(fetched.html, url=url, **adaptor_kwargs)
            data: dict[str, list[str] | str] = {}
            for field_name, selector in selectors.items():
                matches = (
                    page.css(selector, auto_save=True, adaptive=True)
                    if adaptive_mode
                    else page.css(selector)
                )
                if matches:
                    values = [str(el.text or "").strip() for el in matches]
                    data[field_name] = values if len(values) > 1 else values[0]
                else:
                    data[field_name] = []

            return StructuredData(success=True, url=url, data=data, selectors_used=selectors)
        except Exception as exc:
            logger.warning(f"Structured extraction failed for {url}: {exc}")
            return StructuredData(success=False, url=url, data={}, error=str(exc))

    # ── Batch fetch ───────────────────────────────────────────────────────────

    async def fetch_batch(
        self, urls: list[str], concurrency: int = 5, **kwargs: object
    ) -> list[ScrapedContent]:
        """Fetch multiple URLs concurrently.

        Uses ResearchSpider when scraping_spider_enabled=True for per-domain
        throttling. Falls back to plain asyncio.gather otherwise.
        """
        if self._settings.scraping_spider_enabled and len(urls) > 1:
            return await self._fetch_batch_spider(urls)

        semaphore = asyncio.Semaphore(concurrency)

        async def _bounded_fetch(url: str) -> ScrapedContent:
            async with semaphore:
                return await self.fetch_with_escalation(url, **kwargs)

        return list(await asyncio.gather(*[_bounded_fetch(u) for u in urls]))

    async def _fetch_batch_spider(self, urls: list[str]) -> list[ScrapedContent]:
        """Fetch via ResearchSpider for per-domain throttled crawling."""
        from app.infrastructure.external.scraper.research_spider import ResearchSpider

        spider = ResearchSpider(
            start_urls=urls,
            impersonate=self._settings.scraping_default_impersonate,
            timeout=self._settings.scraping_http_timeout,
            max_text_length=self._settings.scraping_max_content_length,
        )

        items_by_url: dict[str, dict] = {}
        try:
            async for item in spider.stream():
                items_by_url[item["url"]] = item
        except Exception as exc:
            logger.warning(f"ResearchSpider stream error: {exc}")

        results: list[ScrapedContent] = []
        for url in urls:
            item = items_by_url.get(url)
            if item and item.get("text"):
                results.append(
                    ScrapedContent(
                        success=True,
                        url=item["url"],
                        text=item["text"],
                        title=item.get("title"),
                        status_code=item.get("status"),
                        tier_used="spider",
                    )
                )
            else:
                results.append(
                    ScrapedContent(
                        success=False,
                        url=url,
                        text="",
                        error="Spider did not return content for URL",
                        tier_used="spider",
                    )
                )
        return results


# ── Singleton factory ──────────────────────────────────────────────────────────

_adapter: ScraplingAdapter | None = None


def get_scraping_adapter() -> ScraplingAdapter:
    """Return the application-scoped ScraplingAdapter singleton."""
    global _adapter
    if _adapter is None:
        from app.core.config import get_settings

        _adapter = ScraplingAdapter(get_settings())
    return _adapter
