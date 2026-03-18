"""Scraper service gateway interface (domain layer).

Follows the same Protocol pattern as domain/external/browser.py.
The domain layer depends only on this abstraction — never imports Scrapling directly.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ScrapedContent:
    """Result of a scraping operation."""

    success: bool
    url: str
    text: str  # Cleaned text content
    html: str | None = None  # Raw HTML (for paywall detection)
    title: str | None = None
    status_code: int | None = None
    tier_used: str | None = None  # "http" | "dynamic" | "stealthy"
    error: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class StructuredData:
    """Result of structured CSS/XPath extraction."""

    success: bool
    url: str
    data: dict  # field_name → extracted value(s)
    selectors_used: dict | None = None
    error: str | None = None


class Scraper(Protocol):
    """Scraper service gateway interface.

    Defines the contract for web scraping implementations.
    Supports tiered fetching, structured extraction, and escalation.
    """

    async def fetch(self, url: str, **kwargs: object) -> ScrapedContent:
        """Fetch page content using Tier 1 (HTTP with TLS impersonation)."""
        ...

    async def fetch_with_escalation(self, url: str, **kwargs: object) -> ScrapedContent:
        """Fetch with automatic tier escalation on failure (HTTP → Dynamic → Stealthy)."""
        ...

    async def extract_structured(self, url: str, selectors: dict[str, str], **kwargs: object) -> StructuredData:
        """Extract structured data using CSS selectors."""
        ...

    async def fetch_batch(self, urls: list[str], concurrency: int = 5, **kwargs: object) -> list[ScrapedContent]:
        """Fetch multiple URLs concurrently."""
        ...
