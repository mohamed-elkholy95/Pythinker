"""ResearchSpider — Scrapling Spider for batch URL fetching in wide_research().

Uses Scrapling's Spider framework to provide:
- Per-domain request throttling (concurrent_requests_per_domain)
- Multi-session escalation: fast HTTP → stealth browser on blocked requests
- Blocked-request detection with automatic retry and session escalation
- Streaming results for incremental processing
- robots.txt compliance

This lives in the infrastructure layer; the domain layer interacts with it
exclusively through the Scraper Protocol (fetch_batch method).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from scrapling.fetchers import AsyncStealthySession, FetcherSession
from scrapling.spiders import SessionManager, Spider

if TYPE_CHECKING:
    from scrapling.spiders import Request, Response

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 100_000  # Default cap matching scraping_max_content_length

# Domains that block anonymous scraping or require OAuth/API access.
# Search snippets are preserved for these URLs — no spider enrichment.
SPIDER_DENYLIST_DOMAINS: frozenset[str] = frozenset(
    {
        "reddit.com",  # Responsible Builder Policy — requires OAuth
        "x.com",  # Aggressive bot blocking
        "twitter.com",  # Legacy domain for x.com
    }
)


def should_skip_spider(url: str) -> bool:
    """Check if URL should be skipped by the spider (domain denylist)."""
    try:
        hostname = urlparse(url).hostname or ""
        hostname = hostname.removeprefix("www.")
        return any(hostname == domain or hostname.endswith(f".{domain}") for domain in SPIDER_DENYLIST_DOMAINS)
    except Exception:
        return False


class ResearchSpider(Spider):
    """A Scrapling Spider that fetches a fixed set of research URLs.

    Uses two sessions:
    - ``http``: Fast HTTP via curl_cffi with TLS fingerprint impersonation.
    - ``stealth``: Hardened Playwright browser (lazy-loaded, only started when
      a request is escalated after being blocked).

    When a request is blocked (429/5xx), ``retry_blocked_request`` escalates it
    to the stealth session for a single retry with full browser rendering.

    Provides per-domain throttling and blocked-request detection that plain
    asyncio.gather lacks. Results are yielded as dicts with keys:
    url, text, title, status.
    """

    name = "research"
    robots_txt_obey: bool = True

    # Concurrency — 5 global, max 2 per domain to avoid hammering single hosts
    concurrent_requests: int = 5
    concurrent_requests_per_domain: int = 2
    download_delay: float = 0.3

    # Allow one retry via stealth session before giving up
    max_blocked_retries: int = 1

    def __init__(
        self,
        start_urls: list[str],
        impersonate: str = "chrome",
        timeout: int = 15,
        max_text_length: int = _MAX_TEXT_LENGTH,
        *,
        stealth_enabled: bool = True,
    ) -> None:
        """Initialise the spider.

        Args:
            start_urls: URLs to fetch (each fetched exactly once).
            impersonate: curl_cffi TLS fingerprint to impersonate.
            timeout: Per-request timeout in seconds.
            max_text_length: Maximum characters to return per page.
            stealth_enabled: Register a lazy stealth session for blocked-request
                escalation. Disable to skip browser overhead entirely.
        """
        # Set instance attrs BEFORE super().__init__() so configure_sessions can use them.
        self.start_urls = list(start_urls)
        self._impersonate = impersonate
        self._timeout = timeout
        self._max_text_length = max_text_length
        self._stealth_enabled = stealth_enabled
        super().__init__()  # no crawldir — no checkpoint persistence needed

    def configure_sessions(self, manager: SessionManager) -> None:
        """Register HTTP (default) and optional stealth (lazy) sessions."""
        manager.add(
            "http",
            FetcherSession(
                impersonate=self._impersonate,
                timeout=self._timeout,
                follow_redirects=True,
                stealthy_headers=True,
            ),
            default=True,
        )
        if self._stealth_enabled:
            manager.add(
                "stealth",
                AsyncStealthySession(
                    block_webrtc=True,
                    allow_webgl=True,
                    google_search=True,
                    timeout=self._timeout * 1000,  # ms
                ),
                lazy=True,  # only start browser when actually needed
            )

    # Only retry transient failures — 403 is a permanent access denial and
    # retrying wastes ~1-2s per URL (observed: ProductHunt 403 x 4 attempts).
    _RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

    async def is_blocked(self, response: Response) -> bool:
        """Override Spider.is_blocked to skip retries on non-retryable codes (403, 401).

        The default Scrapling BLOCKED_CODES includes 403, which causes 3 wasted
        retries on sites that permanently deny bot access.
        """
        return response.status in self._RETRYABLE_STATUS_CODES

    async def retry_blocked_request(self, request: Request, response: Response) -> Request:
        """Escalate blocked requests from HTTP to the stealth browser session."""
        if self._stealth_enabled:
            logger.info(
                "ResearchSpider escalating blocked request to stealth session: %s (status %s)",
                request.url,
                response.status,
            )
            request.sid = "stealth"
        return request

    async def parse(self, response: Response) -> AsyncGenerator[dict | Request | None, None]:
        """Extract text content from each fetched page."""
        text = str(response.get_all_text(separator="\n\n"))
        if len(text) > self._max_text_length:
            text = text[: self._max_text_length]

        title_el = response.css("title")
        title = title_el[0].text if title_el else None

        yield {
            "url": str(response.url),
            "text": text,
            "title": title,
            "status": response.status,
        }
