"""Deal Finder infrastructure adapter package."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.infrastructure.external.deal_finder.adapter import DealFinderAdapter

if TYPE_CHECKING:
    from app.domain.external.scraper import Scraper
    from app.domain.external.search import SearchEngine


def get_deal_finder_adapter(
    scraper: Scraper,
    search_engine: SearchEngine | None = None,
) -> DealFinderAdapter:
    """Factory function for creating a DealFinderAdapter.

    Args:
        scraper: Scraper service for HTTP fetching.
        search_engine: Optional search engine for product discovery.

    Returns:
        Configured DealFinderAdapter instance.
    """
    return DealFinderAdapter(scraper=scraper, search_engine=search_engine)


__all__ = ["DealFinderAdapter", "get_deal_finder_adapter"]
