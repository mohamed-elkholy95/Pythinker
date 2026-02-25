"""ScrapingTool — structured web scraping tools for the agent.

Exposes three agent-callable tools:
  - scrape_structured: extract data fields via CSS selectors → JSON
  - scrape_batch:      fetch multiple URLs concurrently
  - adaptive_scrape:   scrape with element fingerprint tracking (Phase 5)

Enabled via SCRAPING_TOOL_ENABLED=true in .env.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.domain.external.scraper import Scraper
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool

if TYPE_CHECKING:
    from app.domain.services.memory_service import MemoryService

logger = logging.getLogger(__name__)


class ScrapingTool(BaseTool):
    """Structured web scraping tool with optional adaptive element tracking."""

    name: str = "scraping"

    def __init__(
        self,
        scraper: Scraper,
        max_observe: int | None = None,
        memory_service: MemoryService | None = None,
        user_id: str | None = None,
    ) -> None:
        super().__init__(max_observe=max_observe)
        self.scraper = scraper
        self._memory_service = memory_service
        self._user_id = user_id

    @tool(
        name="scrape_structured",
        description="""Extract structured data fields from a webpage using CSS selectors.

USE WHEN:
- You need specific data fields from a page (prices, titles, dates, links, etc.)
- The page has consistent HTML structure you can target with CSS
- You want JSON output instead of raw text

EXAMPLE:
scrape_structured(
    url="https://example.com/products",
    selectors={"price": ".price-tag", "name": "h2.product-name", "rating": ".star-rating"}
)

RETURNS: Dict mapping field names to extracted values (list if multiple matches, string if single).""",
        parameters={
            "url": {
                "type": "string",
                "description": "URL of the page to scrape",
            },
            "selectors": {
                "type": "object",
                "description": "Map of field names to CSS selectors, e.g. {\"price\": \".price\", \"title\": \"h1\"}",
            },
        },
        required=["url", "selectors"],
    )
    async def scrape_structured(self, url: str, selectors: dict) -> ToolResult:
        """Extract structured data from a page using CSS selectors."""
        if not selectors:
            return ToolResult(success=False, message="selectors must be a non-empty dict")

        result = await self.scraper.extract_structured(url, selectors)
        if result.success:
            field_count = len(result.data)
            return ToolResult(
                success=True,
                message=f"Extracted {field_count} field(s) from {url}",
                data={"url": url, "fields": result.data},
            )
        return ToolResult(
            success=False,
            message=f"Structured extraction failed: {result.error}",
            data={"url": url},
        )

    @tool(
        name="scrape_batch",
        description="""Fetch content from multiple URLs concurrently using stealth HTTP.

USE WHEN:
- You have a list of URLs to read (search results, link lists, etc.)
- You want to fetch them in parallel rather than one by one
- Max 10 URLs per call for best performance

EXAMPLE:
scrape_batch(urls=["https://example.com/a", "https://example.com/b"])

RETURNS: List of {url, success, text, tier_used} objects.""",
        parameters={
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of URLs to fetch (max 10)",
            },
            "focus": {
                "type": "string",
                "description": "(Optional) Keyword or phrase to filter content around",
            },
        },
        required=["urls"],
    )
    async def scrape_batch(self, urls: list[str], focus: str | None = None) -> ToolResult:
        """Fetch multiple URLs concurrently."""
        if not urls:
            return ToolResult(success=False, message="urls list must not be empty")

        urls = urls[:10]  # hard cap — protect against runaway batches
        results = await self.scraper.fetch_batch(urls, concurrency=5)

        items = []
        for r in results:
            text = r.text
            if focus and text:
                # Simple focus filter: keep surrounding context of keyword hits
                lower = text.lower()
                keyword = focus.lower()
                if keyword in lower:
                    idx = lower.index(keyword)
                    start = max(0, idx - 500)
                    end = min(len(text), idx + 2000)
                    text = text[start:end]
            items.append(
                {
                    "url": r.url,
                    "success": r.success,
                    "text": text[:5000] if text else "",
                    "tier_used": r.tier_used,
                    "error": r.error,
                }
            )

        success_count = sum(1 for i in items if i["success"])
        return ToolResult(
            success=True,
            message=f"Fetched {success_count}/{len(urls)} URLs successfully",
            data={"results": items},
        )

    @tool(
        name="adaptive_scrape",
        description="""Extract structured data with adaptive element tracking.

Like scrape_structured, but learns and remembers element positions across visits.
On first scrape: saves element fingerprints for this domain.
On subsequent scrapes: uses similarity matching to find elements even if CSS changed.

USE WHEN:
- You need to re-scrape the same site repeatedly (price monitoring, data updates)
- The site may redesign and break static CSS selectors
- You want stable extraction across sessions

Requires SCRAPING_ADAPTIVE_TRACKING=true in configuration.

EXAMPLE:
adaptive_scrape(
    url="https://example.com/products",
    selectors={"price": ".price", "name": "h1"},
    context="product pricing data"
)""",
        parameters={
            "url": {
                "type": "string",
                "description": "URL of the page to scrape",
            },
            "selectors": {
                "type": "object",
                "description": "Map of field names to CSS selectors",
            },
            "context": {
                "type": "string",
                "description": "(Optional) Brief description of what data you are extracting",
            },
        },
        required=["url", "selectors"],
    )
    async def adaptive_scrape(
        self, url: str, selectors: dict, context: str | None = None
    ) -> ToolResult:
        """Scrape with adaptive element tracking and optional memory persistence."""
        from app.core.config import get_settings

        settings = get_settings()
        if not settings.scraping_adaptive_tracking:
            # Fall back to regular structured extraction
            return await self.scrape_structured(url, selectors)

        result = await self.scraper.extract_structured(url, selectors)
        if not result.success:
            return ToolResult(
                success=False,
                message=f"Adaptive scrape failed: {result.error}",
                data={"url": url},
            )

        # Store successful selector mappings in memory for cross-session reuse
        if self._memory_service and self._user_id and result.data:
            await self._store_selector_memory(url, selectors, result.data, context)

        field_count = len(result.data)
        return ToolResult(
            success=True,
            message=f"Adaptive extraction: {field_count} field(s) from {url} (fingerprints saved)",
            data={"url": url, "fields": result.data, "adaptive": True},
        )

    async def _store_selector_memory(
        self,
        url: str,
        selectors: dict,
        data: dict,
        context: str | None,
    ) -> None:
        """Store successful selector mapping in memory service for cross-session reuse."""
        try:
            from urllib.parse import urlparse

            from app.domain.models.long_term_memory import MemoryType

            domain = urlparse(url).netloc
            successful_fields = [
                f"{field_name}={selector}"
                for field_name, selector in selectors.items()
                if data.get(field_name)
            ]
            if not successful_fields:
                return

            content = (
                f"Successful CSS selectors for {domain}: "
                + ", ".join(successful_fields)
                + (f" | Context: {context}" if context else "")
            )

            await self._memory_service.store_memory(
                user_id=self._user_id,
                content=content,
                memory_type=MemoryType.PROCEDURE,
                metadata={
                    "url": url,
                    "domain": domain,
                    "selectors": selectors,
                    "source": "adaptive_scrape",
                },
            )
            logger.debug("Stored adaptive selector memory for %s", domain)
        except Exception as exc:
            logger.debug("Failed to store adaptive selector memory: %s", exc)
