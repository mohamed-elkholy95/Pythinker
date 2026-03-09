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
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from app.core.config import get_settings
from app.domain.external.deal_finder import (
    CouponInfo,
    CouponSearchResult,
    DealComparison,
    DealProgressCallback,
    DealResult,
    EmptyReason,
)
from app.domain.models.search import SearchResults
from app.infrastructure.external.deal_finder.coupon_aggregator import (
    aggregate_coupons,
    build_coupon_source_urls,
)
from app.infrastructure.external.deal_finder.item_classifier import classify_item_category
from app.infrastructure.external.deal_finder.price_extractor import extract_price
from app.infrastructure.external.deal_finder.price_voter import VotingResult, vote_on_price

if TYPE_CHECKING:
    from app.domain.external.llm import LLM
    from app.domain.external.scraper import Scraper
    from app.domain.external.search import SearchEngine

logger = logging.getLogger(__name__)

# Major retailers to search by default (expanded for broader coverage)
DEFAULT_STORES = [
    "amazon.com",
    "walmart.com",
    "bestbuy.com",
    "target.com",
    "ebay.com",
    "newegg.com",
    "costco.com",
    "bhphotovideo.com",
    "adorama.com",
    "microcenter.com",
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
    "B&H Photo": 0.92,
    "Adorama": 0.88,
    "Micro Center": 0.90,
    "eBay": 0.70,
}

# Community search query templates — {query} is replaced with the product query
COMMUNITY_QUERY_TEMPLATES = [
    "{query} deal reddit",
    "{query} best price slickdeals OR dealnews OR techbargains",
    "{query} discount coupon",
]

# Known community/deal domains → human-readable names
COMMUNITY_DOMAINS: dict[str, str] = {
    "reddit.com": "Reddit",
    "slickdeals.net": "Slickdeals",
    "dealnews.com": "DealNews",
    "techbargains.com": "TechBargains",
    "wirecutter.com": "Wirecutter",
    "bensbargains.com": "Ben's Bargains",
    "bradsdeals.com": "Brad's Deals",
}

# Confidence for snippet-extracted prices (moderate — from search result text, not structured page data)
CONFIDENCE_SNIPPET = 0.35

# Regex to find $XX.XX prices in search snippets
_SNIPPET_PRICE_PATTERN = re.compile(r"\$\s*(\d{1,6}(?:,\d{3})*(?:\.\d{2})?)")

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
        "bhphotovideo.com": "B&H Photo",
        "adorama.com": "Adorama",
        "microcenter.com": "Micro Center",
    }
    return store_names.get(domain, domain)


_TITLE_STOP_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "for",
        "in",
        "on",
        "at",
        "to",
        "of",
        "is",
        "it",
        "by",
        "with",
        "from",
        "as",
        "not",
        "no",
        "all",
        "best",
        "new",
        "buy",
        "get",
        "top",
        "hot",
        "pro",
        "vs",
        "how",
        "what",
        "find",
        "deal",
        "deals",
        "price",
        "sale",
        "off",
        "coupon",
        "promo",
        "discount",
    }
)


def _title_matches_query(title: str, query: str) -> bool:
    """Check if a search result title is relevant to the original query.

    Multi-signal relevance filter:
    1. Exact phrase: full query as substring → always pass
    2. Numeric enforcement: if query has numbers, title must contain at least one
    3. Word overlap: >= 50% of non-stop query words must appear in title
    """
    if not title or not query:
        return False
    title_lower = title.lower()
    query_lower = query.lower()

    query_words = [
        w
        for w in re.split(r"[\s\-/]+", query_lower)
        if w and w not in _TITLE_STOP_WORDS and (len(w) > 1 or w.isdigit())
    ]
    if not query_words:
        return False

    # Signal 1: Exact phrase match — always relevant
    if query_lower in title_lower:
        return True

    # Signal 2: Numeric token enforcement
    # If the query contains numbers (e.g. "5" in "GLM 5 AI"), at least one
    # must appear in the title. Prevents "GLM 400C" matching "GLM 5".
    query_nums = [w for w in query_words if w.isdigit()]
    if query_nums:
        title_tokens = re.split(r"[\s\-/,]+", title_lower)
        if not any(num in token for token in title_tokens for num in query_nums):
            return False

    # Signal 3: Word overlap threshold — at least 50% of query words
    matched = sum(1 for word in query_words if word in title_lower)
    threshold = max(1, len(query_words) // 2)  # At least 1, at least 50%
    return matched >= threshold


# URL path segments that indicate non-purchasable pages (news, blogs, reviews)
_EDITORIAL_PATH_SEGMENTS = frozenset(
    {
        "news",
        "blog",
        "blogs",
        "article",
        "articles",
        "press",
        "press-release",
        "press-releases",
        "editorial",
        "editorials",
        "review",
        "reviews",
        "opinion",
        "opinions",
        "story",
        "stories",
        "post",
        "posts",
        "magazine",
        "journal",
        "about",
        "careers",
        "help",
        "support",
        "faq",
        "contact",
        "privacy",
        "terms",
    }
)


def _is_editorial_url(url: str) -> bool:
    """Detect URLs that are likely editorial/news rather than product pages.

    Checks URL path segments against known non-commerce patterns.
    Product URLs like /dp/, /product/, /p/ are NOT flagged.
    """
    try:
        path = urlparse(url).path.lower().strip("/")
    except Exception:
        return False
    segments = path.split("/")
    # Only check first 2 path segments (deeper paths less indicative)
    return any(seg in _EDITORIAL_PATH_SEGMENTS for seg in segments[:2])


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

    # Discount outlier penalty: >85% discount without coupon is suspicious
    if deal.original_price and deal.original_price > deal.price:
        discount = (deal.original_price - deal.price) / deal.original_price * 100
        if discount > 85 and not has_coupon:
            score = max(0, score - 30)  # Heavy penalty
        elif discount > 70 and extraction_confidence < 0.5:
            score = max(0, score - 15)  # Moderate penalty for unconfident high discount

    return min(100, score)


def _extract_deals_from_snippets(
    search_results: SearchResults | None,
    query: str,
    source_type: str,
) -> list[DealResult]:
    """Extract deal information from search result snippets.

    Parses $XX.XX prices from title + snippet text. Returns one deal per
    unique URL. Items without a parseable price get price=0.0 and very
    low confidence (mention-only).
    """
    deals: list[DealResult] = []
    seen_urls: set[str] = set()

    if not search_results or not search_results.results:
        return deals

    for item in search_results.results[:10]:
        url = item.link
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        if _is_editorial_url(url):
            continue

        title = item.title or ""
        snippet = item.snippet or ""
        combined_text = f"{title} {snippet}"

        # Detect store name from URL or community domain map
        domain = _domain_from_url(url)
        store_name = COMMUNITY_DOMAINS.get(domain, _store_from_url(url))

        prices = _SNIPPET_PRICE_PATTERN.findall(combined_text)
        parsed_prices = []
        for p in prices:
            try:
                val = float(p.replace(",", ""))
                if 0.50 <= val <= 50_000:
                    parsed_prices.append(val)
            except ValueError:
                continue

        if parsed_prices:
            price = parsed_prices[0]
            # Second higher price is likely the original price
            original_price = None
            if len(parsed_prices) > 1:
                higher = [p for p in parsed_prices[1:] if p > price]
                if higher:
                    original_price = higher[0]

            discount_pct = None
            if original_price and original_price > price:
                discount_pct = round((original_price - price) / original_price * 100, 1)

            deals.append(
                DealResult(
                    product_name=title or query,
                    store=store_name,
                    price=price,
                    original_price=original_price,
                    discount_percent=discount_pct,
                    url=url,
                    extraction_strategy="snippet",
                    extraction_confidence=CONFIDENCE_SNIPPET,
                    source_type=source_type,
                    item_category=classify_item_category(
                        text=combined_text,
                        url=url,
                        store=store_name,
                    ),
                )
            )
        else:
            # Mention-only: deal referenced but no price found
            deals.append(
                DealResult(
                    product_name=title or query,
                    store=store_name,
                    price=0.0,
                    url=url,
                    extraction_strategy="snippet_mention",
                    extraction_confidence=0.10,
                    source_type=source_type,
                    item_category=classify_item_category(
                        text=combined_text,
                        url=url,
                        store=store_name,
                    ),
                )
            )

    return deals


def _voting_result_to_deal(
    voting: VotingResult,
    url: str,
    title: str = "",
) -> DealResult | None:
    """Convert a VotingResult to a DealResult, or None if no price."""
    if voting.price is None or voting.price <= 0:
        return None

    discount_pct = None
    if voting.original_price and voting.original_price > voting.price:
        discount_pct = round((voting.original_price - voting.price) / voting.original_price * 100, 1)

    return DealResult(
        product_name=voting.product_name or title,
        store=_store_from_url(url),
        price=voting.price,
        original_price=voting.original_price,
        discount_percent=discount_pct,
        url=url,
        in_stock=voting.in_stock,
        image_url=voting.image_url,
        extraction_strategy=voting.winning_strategy,
        extraction_confidence=voting.confidence,
        item_category=classify_item_category(
            text=voting.product_name or title,
            url=url,
            store=_store_from_url(url),
        ),
    )


class DealFinderAdapter:
    """Infrastructure adapter that implements the DealFinder Protocol.

    Uses Scraper for HTTP fetching and SearchEngine for product discovery.
    Supports price voting (multi-method consensus) and optional LLM fallback.
    """

    def __init__(
        self,
        scraper: Scraper,
        search_engine: SearchEngine | None = None,
        llm: LLM | None = None,
    ) -> None:
        self._scraper = scraper
        self._search_engine = search_engine
        self._llm = llm

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
                searched_stores=[],
                empty_reason=EmptyReason.SEARCH_UNAVAILABLE,
            )

        # Check if community search is enabled
        community_enabled = settings.deal_scraper_community_search or settings.deal_scraper_open_web_search

        # steps: 1 (init) + N stores + 1 (community, if enabled) + 1 (coupons) + 1 (scoring)
        total_steps = len(active_stores) + 3 + (1 if community_enabled else 0)
        step = 0

        async def _report(msg: str, partial_deals: list[DealResult] | None = None) -> None:
            nonlocal step
            step += 1
            if progress:
                partial_data: dict[str, Any] | None = None
                if partial_deals:
                    partial_data = {
                        "deals": [
                            {
                                "product_name": d.product_name,
                                "store": d.store,
                                "price": d.price,
                                "original_price": d.original_price,
                                "discount_percent": d.discount_percent,
                                "url": d.url,
                                "score": d.score,
                                "in_stock": d.in_stock,
                                "coupon_code": d.coupon_code,
                                "image_url": d.image_url,
                                "item_category": d.item_category,
                            }
                            for d in partial_deals[:5]
                        ],
                    }
                await progress(msg, step, total_steps, partial_data)

        await _report(f'Searching {len(active_stores)} stores for "{query}"')

        # Per-store wrapper: search + report progress as each store completes
        async def _search_and_report(store_domain: str) -> list[DealResult]:
            """Search a single store and report progress immediately on completion."""
            store_name = _store_from_url(f"https://{store_domain}")
            search_query = f"{query} price deal site:{store_domain}"
            try:
                result = await self._search_store(search_query, store_domain, timeout, original_query=query)
            except Exception as exc:
                error_msg = str(exc) or type(exc).__name__
                logger.warning("Search failed for %s: %s", store_domain, error_msg)
                store_errors.append({"store": store_name, "error": error_msg})
                await _report(f"Searched {store_name} (failed)")
                return []

            count = len(result) if result else 0
            if result:
                deals.extend(result)
                searched_stores.append(store_name)
                await _report(f"Searched {store_name} ({count} results)", result)
            else:
                # Try simplified query as retry
                simplified = _simplify_query(query)
                if simplified and simplified != query:
                    retry_query = f"{simplified} site:{store_domain}"
                    try:
                        retry_result = await self._search_store(
                            retry_query, store_domain, timeout, original_query=simplified
                        )
                        if retry_result:
                            deals.extend(retry_result)
                            searched_stores.append(store_name)
                            count = len(retry_result)
                    except Exception as exc:
                        logger.debug("Retry search failed for %s: %s", store_domain, exc)
                await _report(f"Searched {store_name} ({count} results)", result or [])
            return result or []

        # Run store searches + community concurrently; each store fires progress on completion
        store_tasks = [_search_and_report(sd) for sd in active_stores]

        community_deals: list[DealResult] = []
        community_task = asyncio.create_task(self._search_community(query, timeout)) if community_enabled else None

        # Gather stores (each reports individually as it finishes)
        await asyncio.gather(*store_tasks, return_exceptions=True)

        # Collect community results
        if community_task is not None:
            try:
                community_result = await community_task
                if isinstance(community_result, list):
                    community_deals = community_result
            except Exception as exc:
                logger.warning("Community search failed: %s", exc)

        # Merge community deals (dedup by URL against store results)
        community_sources_searched = 0
        if community_deals:
            store_urls = {d.url for d in deals}
            for cd in community_deals:
                if cd.url not in store_urls:
                    deals.append(cd)
                    community_sources_searched += 1
                    store_urls.add(cd.url)
            if community_enabled:
                await _report(f"Found {community_sources_searched} community/web mention(s)")

        # Find coupons for stores that returned results
        await _report("Aggregating coupons")
        coupon_sources = settings.deal_scraper_coupon_sources.split(",")
        coupons: list[CouponInfo] = []
        # Search coupons per store (not per product query) for meaningful matches
        coupon_stores = searched_stores or [_store_from_url(f"https://{d}") for d in active_stores[:3]]
        coupon_tasks = [
            aggregate_coupons(
                self._scraper,
                store=s,
                sources=coupon_sources,
                search_engine=self._search_engine,
                ttl=settings.deal_scraper_cache_ttl,
            )
            for s in coupon_stores
        ]
        try:
            coupon_results = await asyncio.gather(*coupon_tasks, return_exceptions=True)
            for result in coupon_results:
                if isinstance(result, BaseException):
                    logger.debug("Coupon fetch failed for a store: %s", result)
                elif isinstance(result, tuple):
                    # aggregate_coupons returns (coupons, source_failures)
                    found_coupons, _failures = result
                    coupons.extend(found_coupons)
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

        # Persist price history (fire-and-forget, never blocks search)
        if settings.deal_scraper_history_enabled and deals:
            try:
                from app.infrastructure.repositories.deal_history_repository import (
                    record_prices_bulk,
                )

                task = asyncio.create_task(record_prices_bulk(deals, query=query))
                task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
            except Exception as exc:
                logger.debug("Price history recording skipped: %s", exc)

        empty_reason: EmptyReason | None = None
        if not deals:
            if active_stores and len(store_errors) == len(active_stores):
                empty_reason = EmptyReason.ALL_STORE_FAILURES
            else:
                empty_reason = EmptyReason.NO_MATCHES

        return DealComparison(
            query=query,
            deals=deals,
            best_deal=best_deal,
            coupons_found=coupons[:10],
            searched_stores=searched_stores,
            store_errors=store_errors,
            community_sources_searched=community_sources_searched,
            empty_reason=empty_reason,
        )

    async def _search_store(
        self,
        search_query: str,
        store_domain: str,
        timeout: int,  # noqa: ASYNC109
        original_query: str = "",
    ) -> list[DealResult]:
        """Search a single store and extract prices from results."""
        deals: list[DealResult] = []

        if not self._search_engine:
            return deals

        try:
            tool_result = await asyncio.wait_for(
                self._search_engine.search(search_query),
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning("Search timed out for %s after %ds", store_domain, timeout)
            return deals
        except Exception as exc:
            logger.warning("Search error for %s: %s", store_domain, exc)
            return deals

        # Unwrap ToolResult envelope → SearchResults
        if not tool_result or not tool_result.success or not tool_result.data:
            logger.debug("Search returned no data for %s", store_domain)
            return deals
        search_results: SearchResults = tool_result.data

        # Extract prices from search result URLs
        if not search_results.results:
            logger.debug("Search returned 0 results for query: %s", search_query)
            return deals

        relevance_query = original_query or search_query
        urls_to_scrape = []
        skipped_irrelevant = 0
        skipped_editorial = 0
        for item in search_results.results[:10]:  # Top 10 results per store
            url = item.link
            if url and store_domain in _domain_from_url(url):
                if _is_editorial_url(url):
                    skipped_editorial += 1
                elif _title_matches_query(item.title or "", relevance_query):
                    urls_to_scrape.append((url, item.title))
                else:
                    skipped_irrelevant += 1

        logger.debug(
            "Store %s: %d search results → %d URLs matched domain+relevance (%d skipped irrelevant, %d skipped editorial)",
            store_domain,
            len(search_results.results),
            len(urls_to_scrape),
            skipped_irrelevant,
            skipped_editorial,
        )

        settings = get_settings()
        use_voting = settings.deal_scraper_price_voting_enabled
        use_llm = settings.deal_scraper_llm_extraction_enabled and self._llm is not None
        llm_budget = settings.deal_scraper_llm_max_per_search
        llm_used = 0

        for url, title in urls_to_scrape:
            try:
                scraped = await asyncio.wait_for(
                    self._scraper.fetch_with_escalation(url),
                    timeout=timeout,
                )
                if not scraped.success or not scraped.text:
                    continue

                html = scraped.html or scraped.text

                if use_voting:
                    # Multi-method consensus extraction
                    voting = vote_on_price(html, url)

                    # LLM fallback when no consensus and budget remains
                    if use_llm and voting.consensus_method == "best_confidence" and llm_used < llm_budget:
                        try:
                            from app.infrastructure.external.deal_finder.llm_price_extractor import (
                                extract_price_with_llm,
                            )
                            from app.infrastructure.external.deal_finder.price_voter import (
                                add_llm_vote,
                            )

                            llm_vote = await extract_price_with_llm(html, url, self._llm, product_hint=title)
                            voting = add_llm_vote(voting, llm_vote)
                            llm_used += 1
                        except Exception as exc:
                            logger.debug("LLM extraction skipped for %s: %s", url[:50], exc)

                    deal = _voting_result_to_deal(voting, url, title)
                    if deal:
                        deals.append(deal)
                else:
                    # Legacy waterfall extraction
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
                                        (price_data.original_price - price_data.price)
                                        / price_data.original_price
                                        * 100,
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
                                item_category=classify_item_category(
                                    text=price_data.product_name or title,
                                    url=url,
                                    store=_store_from_url(url),
                                ),
                            )
                        )

            except TimeoutError:
                logger.warning("Price scrape timed out for %s", url)
            except Exception as exc:
                logger.warning("Price extraction failed for %s: %s", url, exc)

        return deals

    async def _search_community(
        self,
        query: str,
        timeout: int,  # noqa: ASYNC109
    ) -> list[DealResult]:
        """Search community sites and open web for deal mentions.

        Builds queries from COMMUNITY_QUERY_TEMPLATES plus one open-web
        query (if enabled). Caps total queries at community_max_queries.
        Extracts prices from search snippets — no page scraping needed.
        """
        if not self._search_engine:
            return []

        settings = get_settings()
        max_queries = settings.deal_scraper_community_max_queries

        queries: list[tuple[str, str]] = []  # (search_query, source_type)

        # Community queries (Reddit, Slickdeals, forums)
        if settings.deal_scraper_community_search:
            for template in COMMUNITY_QUERY_TEMPLATES:
                if len(queries) >= max_queries:
                    break
                queries.append((template.format(query=query), "community"))

        # Open web query (unrestricted)
        if settings.deal_scraper_open_web_search and len(queries) < max_queries:
            queries.append((f"{query} deal best price", "open_web"))

        if not queries:
            return []

        async def _run_one(search_query: str, source_type: str) -> list[DealResult]:
            try:
                tool_result = await asyncio.wait_for(
                    self._search_engine.search(search_query),
                    timeout=timeout,
                )
                # Unwrap ToolResult envelope → SearchResults
                if not tool_result or not tool_result.success or not tool_result.data:
                    return []
                return _extract_deals_from_snippets(tool_result.data, query, source_type)
            except TimeoutError:
                logger.debug("Community search timed out for: %s", search_query)
                return []
            except Exception as exc:
                logger.debug("Community search failed for '%s': %s", search_query, exc)
                return []

        results = await asyncio.gather(
            *[_run_one(q, st) for q, st in queries],
            return_exceptions=True,
        )

        combined: list[DealResult] = []
        for result in results:
            if isinstance(result, BaseException):
                logger.debug("Community search exception: %s", result)
                continue
            combined.extend(result)

        return combined

    async def find_coupons(
        self,
        store: str,
        product_url: str | None = None,
        progress: DealProgressCallback | None = None,
    ) -> CouponSearchResult:
        """Find coupons for a specific store."""
        if progress:
            await progress(f"Searching coupons for {store}", 1, 2, None)
        settings = get_settings()
        sources = settings.deal_scraper_coupon_sources.split(",")
        coupons, source_failures = await aggregate_coupons(
            self._scraper,
            store=store,
            sources=sources,
            search_engine=self._search_engine,
            ttl=settings.deal_scraper_cache_ttl,
        )

        urls_checked = build_coupon_source_urls(store, sources)

        if progress:
            await progress(f"Found {len(coupons)} coupons", 2, 2, None)
        return CouponSearchResult(
            coupons=coupons,
            source_failures=source_failures,
            urls_checked=urls_checked,
        )

    async def compare_prices(
        self,
        product_urls: list[str],
        progress: DealProgressCallback | None = None,
    ) -> DealComparison:
        """Compare prices across specific product URLs.

        Fetches all URLs in parallel for speed, then scores and ranks.
        Collects structured errors for URLs that fail extraction.
        """
        settings = get_settings()
        timeout = settings.deal_scraper_timeout
        deals: list[DealResult] = []
        searched_stores: list[str] = []
        store_errors: list[dict[str, str]] = []
        capped_urls = product_urls[:10]
        total_steps = 2

        if progress:
            await progress(f"Fetching prices from {len(capped_urls)} stores", 1, total_steps, None)

        use_voting = settings.deal_scraper_price_voting_enabled

        async def _fetch_one(url: str) -> DealResult | dict[str, str] | None:
            """Fetch and extract price from a single URL.

            Returns DealResult on success, error dict on failure, None on skip.
            """
            store = _store_from_url(url)
            try:
                scraped = await asyncio.wait_for(
                    self._scraper.fetch_with_escalation(url),
                    timeout=timeout,
                )
                if not scraped.success or not scraped.text:
                    return {"store": store, "error": "Page fetch failed"}

                html = scraped.html or scraped.text

                if use_voting:
                    voting = vote_on_price(html, url)
                    deal = _voting_result_to_deal(voting, url, f"Product from {store}")
                    if deal:
                        return deal
                    return {"store": store, "error": "Could not extract price"}

                # Legacy waterfall
                price_data = extract_price(html, url)
                if price_data.price is not None and price_data.price > 0:
                    return DealResult(
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
                        item_category=classify_item_category(
                            text=price_data.product_name or f"Product from {store}",
                            url=url,
                            store=store,
                        ),
                    )
                return {"store": store, "error": "Could not extract price"}

            except TimeoutError:
                logger.warning("Price comparison timed out for %s", url)
                return {"store": store, "error": f"Timed out after {timeout}s"}
            except Exception as exc:
                logger.warning("Price comparison failed for %s: %s", url, exc)
                return {"store": store, "error": str(exc)}

        # Fetch all URLs in parallel
        results = await asyncio.gather(*[_fetch_one(url) for url in capped_urls], return_exceptions=True)

        for result in results:
            if isinstance(result, BaseException):
                logger.warning("Unexpected error in price comparison: %s", result)
                continue
            if isinstance(result, DealResult):
                deals.append(result)
                if result.store not in searched_stores:
                    searched_stores.append(result.store)
            elif isinstance(result, dict):
                store_errors.append(result)

        # Score deals
        if progress:
            await progress(f"Comparing {len(deals)} prices", total_steps, total_steps, None)
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
