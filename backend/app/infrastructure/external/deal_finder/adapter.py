"""DealFinderAdapter — infrastructure implementation of the DealFinder Protocol.

Composes existing Scraper and SearchEngine services to:
1. Search for products across stores via search engine
2. Scrape each result page for price via multi-strategy extraction
3. Aggregate coupons from RSS feeds and coupon sites
4. Score and rank deals (with store reliability and extraction confidence)

Never creates HTTP clients directly — uses Scraper (HTTPClientPool-backed).
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from app.core.config import get_settings
from app.domain.external.deal_finder import (
    CouponInfo,
    DealComparison,
    DealProgressCallback,
    DealResult,
)
from app.infrastructure.external.deal_finder.coupon_aggregator import aggregate_coupons
from app.infrastructure.external.deal_finder.price_extractor import extract_price

if TYPE_CHECKING:
    from app.domain.external.scraper import Scraper
    from app.domain.external.search import SearchEngine

logger = logging.getLogger(__name__)

# Major retailers to search by default
DEFAULT_STORES = [
    "amazon.com",
    "walmart.com",
    "bestbuy.com",
    "target.com",
    "ebay.com",
    "newegg.com",
]

# Store reliability ratings (0-1) — reflects return policy, price accuracy, trust
STORE_RELIABILITY: dict[str, float] = {
    "Amazon": 0.95,
    "Best Buy": 0.92,
    "Costco": 0.93,
    "Walmart": 0.90,
    "Target": 0.90,
    "Newegg": 0.85,
    "Macy's": 0.85,
    "Home Depot": 0.88,
    "eBay": 0.70,
}

# Regex to strip color/year modifiers for query simplification
_QUERY_SIMPLIFY_PATTERN = re.compile(
    r"\b(black|white|silver|gold|blue|red|green|gray|grey|pink|purple|"
    r"orange|brown|beige|navy|midnight|space\s*gray|20\d{2})\b",
    re.IGNORECASE,
)


def _domain_from_url(url: str) -> str:
    """Extract clean domain from URL."""
    domain = urlparse(url).netloc.lower()
    return domain.removeprefix("www.")


def _store_from_url(url: str) -> str:
    """Extract human-readable store name from URL."""
    domain = _domain_from_url(url)
    store_names = {
        "amazon.com": "Amazon",
        "walmart.com": "Walmart",
        "bestbuy.com": "Best Buy",
        "target.com": "Target",
        "ebay.com": "eBay",
        "newegg.com": "Newegg",
        "costco.com": "Costco",
        "macys.com": "Macy's",
        "homedepot.com": "Home Depot",
    }
    return store_names.get(domain, domain)


def _simplify_query(query: str) -> str:
    """Remove color/year modifiers from a query for retry.

    E.g. "Sony WH-1000XM5 Black 2025" → "Sony WH-1000XM5"
    """
    simplified = _QUERY_SIMPLIFY_PATTERN.sub("", query).strip()
    # Collapse whitespace
    return re.sub(r"\s{2,}", " ", simplified)


def _score_deal(
    deal: DealResult,
    all_prices: list[float],
    has_coupon: bool,
    extraction_confidence: float = 0.0,
) -> int:
    """Score a deal 0-100 based on multiple factors.

    Scoring breakdown (100 total):
    - Discount % from original price: 0-30 pts
    - Lowest cross-store price: 0-25 pts
    - Store reliability: 0-15 pts
    - Coupon available: +10 pts
    - In-stock bonus: +10 pts
    - Extraction confidence: 0-10 pts
    """
    score = 0

    # Discount percentage (0-30 pts)
    if deal.original_price and deal.original_price > deal.price:
        discount = (deal.original_price - deal.price) / deal.original_price * 100
        score += min(30, int(discount * 0.6))  # Cap at 30

    # Lowest price bonus (0-25 pts)
    if all_prices:
        min_price = min(all_prices)
        if deal.price <= min_price:
            score += 25
        elif len(all_prices) > 1:
            max_price = max(all_prices)
            price_range = max_price - min_price
            if price_range > 0:
                position = (max_price - deal.price) / price_range
                score += int(position * 25)

    # Store reliability (0-15 pts)
    reliability = STORE_RELIABILITY.get(deal.store, 0.75)
    score += int(reliability * 15)

    # Coupon bonus (+10 pts)
    if has_coupon or deal.coupon_code:
        score += 10

    # In-stock bonus (+10 pts)
    if deal.in_stock:
        score += 10

    # Extraction confidence (0-10 pts)
    score += int(extraction_confidence * 10)

    return min(100, score)


class DealFinderAdapter:
    """Infrastructure adapter that implements the DealFinder Protocol.

    Uses Scraper for HTTP fetching and SearchEngine for product discovery.
    """

    def __init__(
        self,
        scraper: Scraper,
        search_engine: SearchEngine | None = None,
    ) -> None:
        self._scraper = scraper
        self._search_engine = search_engine

    async def search_deals(
        self,
        query: str,
        stores: list[str] | None = None,
        max_results: int = 10,
        progress: DealProgressCallback | None = None,
    ) -> DealComparison:
        """Search for deals across multiple stores.

        Uses the search engine to find product listings, then scrapes
        each result page for price data. Collects structured errors
        for stores that fail.
        """
        settings = get_settings()
        timeout = settings.deal_scraper_timeout
        target_stores = stores or DEFAULT_STORES
        active_stores = target_stores[: settings.deal_scraper_max_stores]
        searched_stores: list[str] = []
        deals: list[DealResult] = []
        store_errors: list[dict[str, str]] = []

        if not self._search_engine:
            return DealComparison(
                query=query,
                error="Search engine not available",
                searched_stores=[],
            )

        # steps: 1 (init) + N stores + 1 (coupons) + 1 (scoring)
        total_steps = len(active_stores) + 2
        step = 0

        async def _report(msg: str) -> None:
            nonlocal step
            step += 1
            if progress:
                await progress(msg, step, total_steps)

        await _report(f'Searching {len(active_stores)} stores for "{query}"')

        # Search for products with store-specific queries
        search_tasks = []
        for store_domain in active_stores:
            search_query = f"{query} site:{store_domain}"
            search_tasks.append(self._search_store(search_query, store_domain, timeout))

        results = await asyncio.gather(*search_tasks, return_exceptions=True)

        for store_domain, result in zip(active_stores, results, strict=False):
            store_name = _store_from_url(f"https://{store_domain}")
            if isinstance(result, Exception):
                error_msg = str(result) or type(result).__name__
                logger.warning("Search failed for %s: %s", store_domain, error_msg)
                store_errors.append({"store": store_name, "error": error_msg})
                await _report(f"Searched {store_name} (failed)")
                continue
            count = len(result) if result else 0
            if result:
                deals.extend(result)
                searched_stores.append(store_name)
            elif count == 0:
                # Try simplified query as retry
                simplified = _simplify_query(query)
                if simplified and simplified != query:
                    retry_query = f"{simplified} site:{store_domain}"
                    try:
                        retry_result = await self._search_store(retry_query, store_domain, timeout)
                        if retry_result:
                            deals.extend(retry_result)
                            searched_stores.append(store_name)
                            count = len(retry_result)
                    except Exception as exc:
                        logger.debug("Retry search failed for %s: %s", store_domain, exc)
            await _report(f"Searched {store_name} ({count} results)")

        # Find coupons for the query
        await _report("Aggregating coupons")
        coupon_sources = settings.deal_scraper_coupon_sources.split(",")
        coupons: list[CouponInfo] = []
        try:
            coupons = await aggregate_coupons(
                self._scraper,
                store=query,  # Use query as store for broad coupon search
                sources=coupon_sources,
                ttl=settings.deal_scraper_cache_ttl,
            )
        except Exception as exc:
            logger.warning("Coupon aggregation failed: %s", exc)

        # Score all deals
        await _report(f"Scoring and ranking {len(deals)} deals")
        all_prices = [d.price for d in deals if d.price > 0]
        for deal in deals:
            deal.score = _score_deal(
                deal,
                all_prices,
                bool(deal.coupon_code),
                extraction_confidence=deal.extraction_confidence,
            )

        # Sort by score (descending)
        deals.sort(key=lambda d: d.score, reverse=True)

        # Trim to max_results
        deals = deals[:max_results]

        best_deal = deals[0] if deals else None

        return DealComparison(
            query=query,
            deals=deals,
            best_deal=best_deal,
            coupons_found=coupons[:10],
            searched_stores=searched_stores,
            store_errors=store_errors,
        )

    async def _search_store(
        self,
        search_query: str,
        store_domain: str,
        timeout: int,  # noqa: ASYNC109
    ) -> list[DealResult]:
        """Search a single store and extract prices from results."""
        deals: list[DealResult] = []

        if not self._search_engine:
            return deals

        try:
            search_results = await asyncio.wait_for(
                self._search_engine.search(search_query),
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning("Search timed out for %s after %ds", store_domain, timeout)
            return deals
        except Exception as exc:
            logger.warning("Search error for %s: %s", store_domain, exc)
            return deals

        # Extract prices from search result URLs
        if not search_results or not hasattr(search_results, "results"):
            return deals

        urls_to_scrape = []
        for item in search_results.results[:3]:  # Top 3 results per store
            url = getattr(item, "url", None) or getattr(item, "link", "")
            if url and store_domain in _domain_from_url(url):
                urls_to_scrape.append((url, getattr(item, "title", "")))

        for url, title in urls_to_scrape:
            try:
                scraped = await asyncio.wait_for(
                    self._scraper.fetch_with_escalation(url),
                    timeout=timeout,
                )
                if not scraped.success or not scraped.text:
                    continue

                html = scraped.html or scraped.text
                price_data = extract_price(html, url)

                if price_data.price is not None and price_data.price > 0:
                    deals.append(
                        DealResult(
                            product_name=price_data.product_name or title,
                            store=_store_from_url(url),
                            price=price_data.price,
                            original_price=price_data.original_price,
                            discount_percent=(
                                round(
                                    (price_data.original_price - price_data.price) / price_data.original_price * 100,
                                    1,
                                )
                                if price_data.original_price and price_data.original_price > price_data.price
                                else None
                            ),
                            url=url,
                            in_stock=price_data.in_stock,
                            image_url=price_data.image_url,
                            extraction_strategy=price_data.strategy_used,
                            extraction_confidence=price_data.confidence,
                        )
                    )

            except TimeoutError:
                logger.warning("Price scrape timed out for %s", url)
            except Exception as exc:
                logger.warning("Price extraction failed for %s: %s", url, exc)

        return deals

    async def find_coupons(
        self,
        store: str,
        product_url: str | None = None,
        progress: DealProgressCallback | None = None,
    ) -> list[CouponInfo]:
        """Find coupons for a specific store."""
        if progress:
            await progress(f"Searching coupons for {store}", 1, 2)
        settings = get_settings()
        sources = settings.deal_scraper_coupon_sources.split(",")
        coupons = await aggregate_coupons(
            self._scraper,
            store=store,
            sources=sources,
            ttl=settings.deal_scraper_cache_ttl,
        )
        if progress:
            await progress(f"Found {len(coupons)} coupons", 2, 2)
        return coupons

    async def compare_prices(
        self,
        product_urls: list[str],
        progress: DealProgressCallback | None = None,
    ) -> DealComparison:
        """Compare prices across specific product URLs.

        Collects structured errors for URLs that fail extraction.
        """
        settings = get_settings()
        timeout = settings.deal_scraper_timeout
        deals: list[DealResult] = []
        searched_stores: list[str] = []
        store_errors: list[dict[str, str]] = []
        capped_urls = product_urls[:10]
        # steps: N urls + 1 (comparing)
        total_steps = len(capped_urls) + 1
        step = 0

        for url in capped_urls:
            step += 1
            store = _store_from_url(url)
            if progress:
                await progress(f"Fetching price from {store}", step, total_steps)
            try:
                scraped = await asyncio.wait_for(
                    self._scraper.fetch_with_escalation(url),
                    timeout=timeout,
                )
                if not scraped.success or not scraped.text:
                    store_errors.append({"store": store, "error": "Page fetch failed"})
                    continue

                html = scraped.html or scraped.text
                price_data = extract_price(html, url)

                if price_data.price is not None and price_data.price > 0:
                    deals.append(
                        DealResult(
                            product_name=price_data.product_name or f"Product from {store}",
                            store=store,
                            price=price_data.price,
                            original_price=price_data.original_price,
                            discount_percent=(
                                round(
                                    (price_data.original_price - price_data.price) / price_data.original_price * 100,
                                    1,
                                )
                                if price_data.original_price and price_data.original_price > price_data.price
                                else None
                            ),
                            url=url,
                            in_stock=price_data.in_stock,
                            image_url=price_data.image_url,
                            extraction_strategy=price_data.strategy_used,
                            extraction_confidence=price_data.confidence,
                        )
                    )
                    if store not in searched_stores:
                        searched_stores.append(store)
                else:
                    store_errors.append({"store": store, "error": "Could not extract price"})

            except TimeoutError:
                logger.warning("Price comparison timed out for %s", url)
                store_errors.append({"store": store, "error": f"Timed out after {timeout}s"})
            except Exception as exc:
                logger.warning("Price comparison failed for %s: %s", url, exc)
                store_errors.append({"store": store, "error": str(exc)})

        # Score deals
        if progress:
            await progress(f"Comparing {len(deals)} prices", total_steps, total_steps)
        all_prices = [d.price for d in deals if d.price > 0]
        for deal in deals:
            deal.score = _score_deal(
                deal,
                all_prices,
                False,
                extraction_confidence=deal.extraction_confidence,
            )

        deals.sort(key=lambda d: d.price)
        best_deal = deals[0] if deals else None

        return DealComparison(
            query="Price comparison",
            deals=deals,
            best_deal=best_deal,
            searched_stores=searched_stores,
            store_errors=store_errors,
        )
