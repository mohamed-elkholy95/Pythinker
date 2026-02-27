"""ResearchSpider — Scrapling Spider for batch URL fetching in wide_research().

Uses Scrapling's Spider framework to provide:
- Per-domain request throttling (concurrent_requests_per_domain)
- Blocked-request detection with automatic retry
- Streaming results for incremental processing

This lives in the infrastructure layer; the domain layer interacts with it
exclusively through the Scraper Protocol (fetch_batch method).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from scrapling.spiders.session import FetcherSession, SessionManager
from scrapling.spiders.spider import Spider

if TYPE_CHECKING:
    from scrapling.engines.toolbelt.custom import Response
    from scrapling.spiders.request import Request

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 100_000  # Default cap matching scraping_max_content_length


class ResearchSpider(Spider):
    """A Scrapling Spider that fetches a fixed set of research URLs.

    Provides per-domain throttling and blocked-request detection that plain
    asyncio.gather lacks. Results are yielded as dicts with keys:
    url, text, title, status.
    """

    name = "research"

    # Concurrency — 5 global, max 2 per domain to avoid hammering single hosts
    concurrent_requests: int = 5
    concurrent_requests_per_domain: int = 2
    download_delay: float = 0.3

    def __init__(
        self,
        start_urls: list[str],
        impersonate: str = "chrome",
        timeout: int = 15,
        max_text_length: int = _MAX_TEXT_LENGTH,
    ) -> None:
        """Initialise the spider.

        Args:
            start_urls: URLs to fetch (each fetched exactly once).
            impersonate: curl_cffi TLS fingerprint to impersonate.
            timeout: Per-request timeout in seconds.
            max_text_length: Maximum characters to return per page.
        """
        # Set instance attrs BEFORE super().__init__() so configure_sessions can use them.
        self.start_urls = list(start_urls)
        self._impersonate = impersonate
        self._timeout = timeout
        self._max_text_length = max_text_length
        super().__init__()  # no crawldir — no checkpoint persistence needed

    def configure_sessions(self, session_manager: SessionManager) -> None:
        """Register an HTTP session with TLS fingerprint impersonation."""
        session_manager.add(
            "http",
            FetcherSession(
                impersonate=self._impersonate,
                timeout=self._timeout,
                follow_redirects=True,
                stealthy_headers=True,
            ),
            default=True,
        )

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
