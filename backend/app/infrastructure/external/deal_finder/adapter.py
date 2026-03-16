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
import datetime
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
    fetch_slickdeals_coupons,
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

# Editorial/review domains that publish articles about products but do not sell them.
# Results from these domains are re-classified as source_type="community" so they
# are filtered out by the existing community-exclusion pass in search_deals().
# This prevents review articles and YouTube videos from appearing as purchasable deal cards.
EDITORIAL_REVIEW_DOMAINS: frozenset[str] = frozenset(
    {
        "cnn.com",
        "cnet.com",
        "tomsguide.com",
        "techradar.com",
        "pcmag.com",
        "theverge.com",
        "engadget.com",
        "soundguys.com",
        "rtings.com",
        "notebookcheck.net",
        "gizmodo.com",
        "9to5mac.com",
        "9to5toys.com",
        "mashable.com",
        "zdnet.com",
        "howtogeek.com",
        "businessinsider.com",
        "youtube.com",
        "cabletv.com",
        "merazoo.com",
        "checkthat.ai",
        "toolmentors.com",
        "agoodmovietowatch.com",
        "dealnews.com",
    }
)

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
    3. Key product word check: at least ONE of the first 2 significant query words
       must appear in the title — prevents generic-word-only overlaps (e.g.
       "Netflix Premium" matching "3-Piece Cutting Set" via "premium").
    4. Word overlap: >= 60% of non-stop query words must appear in title
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

    # Signal 3: Key product word check
    # At least ONE of the first 2 significant query words must appear in the title.
    # This prevents a result like "3-Piece Cutting Set" from matching a query like
    # "Netflix Premium annual subscription" just because "annual" overlaps.
    key_words = query_words[:2]
    if not any(kw in title_lower for kw in key_words):
        return False

    # Signal 4: Word overlap threshold — at least 60% of non-stop query words
    matched = sum(1 for word in query_words if word in title_lower)
    threshold = 0.6
    return matched / len(query_words) >= threshold


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


def _score_deal_static(deal: DealResult, query: str) -> int:
    """Score a deal 0-100. Works for any store, not just known ones.

    Scoring breakdown (100 total):
    - Discount %: 0-35 pts  (capped; uses deal.discount_percent when available)
    - Title relevance to query: 0-25 pts
    - Source type bonus: 0-15 pts  (store > community)
    - Store reliability bonus: 0-10 pts  (known stores get exact value, unknown 7)
    - In-stock bonus: 0-5 pts
    - Price sanity: 0-10 pts  (price > 0; and original_price present + higher)

    Designed for web-wide results where most stores will NOT be in
    STORE_RELIABILITY — unknown stores get a fair default of 7/10 instead
    of the old 0.75 * 15 = ~11 which unfairly penalised any unknown store.
    """
    score = 0

    # Discount (0-35 points)
    discount_pct = deal.discount_percent if deal.discount_percent is not None else 0.0
    if discount_pct > 0:
        score += min(35, int(discount_pct * 0.7))

    # Title relevance (0-25 points)
    if _title_matches_query(deal.product_name, query):
        score += 25
    elif any(w.lower() in deal.product_name.lower() for w in query.split()[:3]):
        score += 15

    # Source type (0-15 points)
    if deal.source_type == "store":
        score += 15
    elif deal.source_type == "community":
        score += 5

    # Store reliability (0-10 points) — known stores get exact bonus, unknown get 7
    reliability = STORE_RELIABILITY.get(deal.store, 0.70)
    score += int(reliability * 10)

    # In stock bonus (0-5 points)
    if deal.in_stock:
        score += 5

    # Price sanity (0-10 points)
    if deal.price > 0:
        score += 5
        if deal.original_price is not None and deal.original_price > 0 and deal.price < deal.original_price:
            score += 5

    return min(100, score)


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

    For web-wide scoring independent of cross-store price context, use
    ``_score_deal_static`` which works fairly for unknown stores.
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

        # Editorial/review domains are not purchasable storefronts — classify them
        # as "community" so they are filtered out by the community-exclusion pass.
        effective_source_type = (
            "community"
            if any(ed in domain for ed in EDITORIAL_REVIEW_DOMAINS)
            else source_type
        )

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
                    source_type=effective_source_type,
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
                    source_type=effective_source_type,
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
        """Search for deals using Shopping API or web scraping, with smart routing.

        Single unified path — all searches go through the Shopping API / web-scrape
        routing regardless of whether ``stores`` is provided.  When the LLM passes
        an explicit store list those stores are used as search-query hints for
        Shopping mode (appended to the query) rather than triggering per-store
        ``site:`` scraping.

        When ``deal_search_mode`` is ``"auto"`` (the default) the item category is
        detected via ``classify_item_category``:
        - "digital" → ``_search_via_web`` (subscriptions / software have no Shopping listing)
        - "physical" / "unknown" → ``_search_via_shopping``, fallback to ``_search_via_web``

        ``deal_search_mode="shopping"`` forces the Shopping path.
        ``deal_search_mode="web"`` forces the web-scrape path.

        After collecting candidates the top ``deal_verify_top_n`` deals are
        verified by scraping the actual product page.  Coupon search runs in
        parallel with verification.  Results are scored, sorted, and trimmed.
        """
        settings = get_settings()

        if not self._search_engine:
            return DealComparison(
                query=query,
                searched_stores=[],
                empty_reason=EmptyReason.SEARCH_UNAVAILABLE,
            )

        # ------------------------------------------------------------------ #
        # Single v2 path: Shopping API / web-scrape routing                   #
        # When the LLM passes explicit stores, append them as search hints    #
        # for the Shopping API instead of doing per-store site: scraping.     #
        # ------------------------------------------------------------------ #
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
                await progress(msg, step, None, partial_data)

        # Determine search mode
        mode = settings.deal_search_mode  # "auto" | "shopping" | "web"

        if mode == "auto":
            item_category = classify_item_category(text=query)
            effective_mode = "web" if item_category == "digital" else "shopping"
            logger.debug(
                "search_deals auto-mode: query=%r category=%s -> mode=%s",
                query,
                item_category,
                effective_mode,
            )
        else:
            effective_mode = mode

        # When explicit stores are provided and mode is shopping, append the
        # store names as search hints so the Shopping API can scope results
        # without per-store site: filtering.
        search_query = query
        if stores and effective_mode == "shopping":
            store_hints = " ".join(
                s.replace(".com", "").replace("www.", "").split(".")[0]
                for s in stores[:3]
            )
            search_query = f"{query} {store_hints}"
            logger.debug(
                "search_deals: appending store hints to query: %r -> %r",
                query,
                search_query,
            )

        await _report(f'Searching for "{query}" via {effective_mode} mode')

        deals: list[DealResult] = []
        searched_stores: list[str] = []

        if effective_mode == "shopping":
            deals = await self._search_via_shopping(search_query, progress=None)
            if not deals:
                logger.debug("search_deals: Shopping returned 0 results, falling back to web for: %s", query)
                deals = await self._search_via_web(query, progress=None)
        else:
            deals = await self._search_via_web(search_query, progress=None)

        # Collect searched stores for reporting
        seen_stores: set[str] = set()
        for deal in deals:
            if deal.store and deal.store not in seen_stores:
                seen_stores.add(deal.store)
                searched_stores.append(deal.store)

        # Parallel: verify top deals + search for coupons
        await _report(f"Verifying top {settings.deal_verify_top_n} deals and searching coupons")

        verify_coro = self._verify_top_deals(
            deals=deals,
            top_n=settings.deal_verify_top_n,
            timeout=settings.deal_verify_timeout,
        )

        async def _noop_coupons() -> list[CouponInfo]:
            return []

        coupon_coro = self._search_coupons_web(query) if settings.deal_coupon_search_enabled else _noop_coupons()

        verify_result, coupon_result = await asyncio.gather(
            verify_coro,
            coupon_coro,
            return_exceptions=True,
        )

        if isinstance(verify_result, BaseException):
            logger.warning("search_deals: verification gather error: %s", verify_result)
        else:
            deals = verify_result  # type: ignore[assignment]

        coupons: list[CouponInfo] = []
        if isinstance(coupon_result, BaseException):
            logger.debug("search_deals: coupon gather error: %s", coupon_result)
        elif isinstance(coupon_result, list):
            # Filter out empty-code coupons — they show as coupon cards in the frontend
            # with no actual code, causing a confusing badge/card mismatch.
            coupons = [c for c in coupon_result if c.code and c.code.strip()]  # type: ignore[union-attr]

        # Filter out community mentions — they are not purchasable listings.
        # Community sources (Reddit, review sites) should not appear as scored
        # deal cards; they can still surface as mentions in the report text.
        deals = [d for d in deals if d.source_type != "community"]

        # Score all deals using the web-wide static scorer (no cross-store price
        # context is available in the v2 path, so _score_deal_static is correct here).
        await _report(f"Scoring and ranking {len(deals)} deals", deals[:5] if deals else None)
        for deal in deals:
            deal.score = _score_deal_static(deal, query)

        deals.sort(key=lambda d: d.score, reverse=True)
        deals = deals[:max_results]

        best_deal = deals[0] if deals else None

        # Persist price history (fire-and-forget)
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
            empty_reason = EmptyReason.NO_MATCHES

        return DealComparison(
            query=query,
            deals=deals,
            best_deal=best_deal,
            coupons_found=coupons[:10],
            searched_stores=searched_stores,
            empty_reason=empty_reason,
        )

    # DEPRECATED: Legacy per-store scraping. Kept for reference only.
    # All searches now go through _search_via_shopping / _search_via_web.
    async def _search_deals_legacy(
        self,
        query: str,
        stores: list[str],
        max_results: int,
        progress: DealProgressCallback | None,
        settings: Any,
    ) -> DealComparison:
        """Legacy per-store site: search flow (DEPRECATED — no longer called).

        Previously used when an explicit ``stores`` list was provided to
        ``search_deals``.  Retained for reference only.  The active code path
        is the unified v2 path in ``search_deals``.
        """
        timeout = settings.deal_scraper_timeout
        active_stores = stores[: settings.deal_scraper_max_stores]
        searched_stores: list[str] = []
        deals: list[DealResult] = []
        store_errors: list[dict[str, str]] = []

        community_enabled = settings.deal_scraper_community_search or settings.deal_scraper_open_web_search
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

        async def _search_and_report(store_domain: str) -> list[DealResult]:
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

        store_tasks = [_search_and_report(sd) for sd in active_stores]
        community_deals: list[DealResult] = []
        community_task = asyncio.create_task(self._search_community(query, timeout)) if community_enabled else None

        await asyncio.gather(*store_tasks, return_exceptions=True)

        if community_task is not None:
            try:
                community_result = await community_task
                if isinstance(community_result, list):
                    community_deals = community_result
            except Exception as exc:
                logger.warning("Community search failed: %s", exc)

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

        # Filter out community mentions before scoring — they are not purchasable
        # listings and should not appear as scored deal cards.
        deals = [d for d in deals if d.source_type != "community"]

        await _report("Aggregating coupons")
        coupon_sources = settings.deal_scraper_coupon_sources.split(",")
        coupons: list[CouponInfo] = []
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
                    found_coupons, _failures = result
                    coupons.extend(found_coupons)
        except Exception as exc:
            logger.warning("Coupon aggregation failed: %s", exc)

        await _report(f"Scoring and ranking {len(deals)} deals")
        all_prices = [d.price for d in deals if d.price > 0]
        for deal in deals:
            deal.score = _score_deal(
                deal,
                all_prices,
                bool(deal.coupon_code),
                extraction_confidence=deal.extraction_confidence,
            )

        deals.sort(key=lambda d: d.score, reverse=True)
        deals = deals[:max_results]
        best_deal = deals[0] if deals else None

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

    # DEPRECATED: Legacy per-store scraping. Kept for reference only.
    # All searches now go through _search_via_shopping / _search_via_web.
    async def _search_store(
        self,
        search_query: str,
        store_domain: str,
        timeout: int,  # noqa: ASYNC109
        original_query: str = "",
    ) -> list[DealResult]:
        """Search a single store using a site: operator query (DEPRECATED — no longer called).

        Previously called by ``_search_deals_legacy`` to fetch per-store results.
        Retained for reference only.
        """
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

    async def _search_via_shopping(
        self,
        query: str,
        progress: DealProgressCallback | None = None,
    ) -> list[DealResult]:
        """Search Google Shopping via Serper and convert results to DealResult objects.

        Uses ``SerperSearchEngine.search_shopping()`` when available on the injected
        search engine.  Falls back to an empty list when the engine does not support
        the Shopping API, keeping backward-compatibility with other search backends.

        Args:
            query: Product search query.
            progress: Optional progress callback invoked after results are fetched.

        Returns:
            List of DealResult objects with price > 0, sorted by Shopping position.
        """
        if not self._search_engine or not hasattr(self._search_engine, "search_shopping"):
            logger.debug("_search_via_shopping: search engine does not support search_shopping()")
            return []

        settings = get_settings()
        timeout = settings.deal_scraper_timeout

        try:
            tool_result = await asyncio.wait_for(
                self._search_engine.search_shopping(query, num=20),  # type: ignore[attr-defined]
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning("Serper Shopping timed out for query: %s", query)
            return []
        except Exception as exc:
            logger.warning("Serper Shopping error for query '%s': %s", query, exc)
            return []

        if not tool_result or not tool_result.success or not tool_result.data:
            logger.debug("_search_via_shopping: empty or failed ToolResult for query: %s", query)
            return []

        shopping_items = tool_result.data
        deals: list[DealResult] = []

        for item in shopping_items:
            if item.price <= 0:
                continue

            store_name = item.source or _store_from_url(item.link)

            discount_pct: float | None = None

            deals.append(
                DealResult(
                    product_name=item.title,
                    store=store_name,
                    price=item.price,
                    original_price=None,
                    discount_percent=discount_pct,
                    url=item.link,
                    in_stock=True,
                    image_url=item.image_url or None,
                    extraction_strategy="shopping_api",
                    extraction_confidence=0.80,  # Shopping API is highly structured
                    source_type="store",
                    item_category=classify_item_category(
                        text=item.title,
                        url=item.link,
                        store=store_name,
                    ),
                )
            )

        logger.debug(
            "_search_via_shopping: %d shopping results → %d priced deals for query: %s",
            len(shopping_items),
            len(deals),
            query,
        )

        if progress and deals:
            store_counts: dict[str, int] = {}
            for d in deals:
                store_counts[d.store] = store_counts.get(d.store, 0) + 1

            checkpoint_data = {
                "store_statuses": [
                    {"store": store, "status": "found", "result_count": count}
                    for store, count in store_counts.items()
                ],
                "partial_deals": [],
                "query": query,
            }
            await progress(
                f"Found {len(deals)} deals from {len(store_counts)} stores",
                len(deals),
                len(deals),
                checkpoint_data,
            )

        return deals

    async def _verify_top_deals(
        self,
        deals: list[DealResult],
        top_n: int,
        timeout: float,  # noqa: ASYNC109
    ) -> list[DealResult]:
        """Verify price accuracy for the top N deals by scraping their product pages.

        Fetches each URL in parallel using ``asyncio.gather``.  When the scraped
        page yields a confident price (confidence >= 0.5), the deal's price,
        original_price, and discount are updated in-place.  Deals that fail
        verification (network error, no price, low confidence) are kept unchanged.
        Deals beyond ``top_n`` are appended to the result unmodified.

        Args:
            deals: Sorted list of deals (best first).
            top_n: Number of top deals to verify.
            timeout: Per-page fetch timeout in seconds.

        Returns:
            Full list of deals (top_n verified + remainder unchanged).
        """
        to_verify = deals[:top_n]
        remainder = deals[top_n:]

        seen_urls: set[str] = set()

        async def _verify_one(deal: DealResult) -> DealResult:
            url = deal.url
            # Skip Google Shopping redirect URLs — not directly scrapable
            if not url or "google.com/search" in url or "google.com/aclk" in url:
                return deal
            # Skip duplicate URLs — same page already scheduled for scraping
            if url in seen_urls:
                return deal
            seen_urls.add(url)
            try:
                scraped = await asyncio.wait_for(
                    self._scraper.fetch(url),
                    timeout=timeout,
                )
                if not scraped.success or not scraped.html:
                    return deal

                voting = vote_on_price(scraped.html, url)

                if voting.price and voting.price > 0 and voting.confidence >= 0.5:
                    discount_pct: float | None = None
                    if voting.original_price and voting.original_price > voting.price:
                        discount_pct = round((voting.original_price - voting.price) / voting.original_price * 100, 1)

                    # Update the deal with verified data (return new instance for safety)
                    deal.price = voting.price
                    deal.original_price = voting.original_price
                    deal.discount_percent = discount_pct
                    deal.in_stock = voting.in_stock
                    deal.extraction_strategy = voting.winning_strategy or "shopping_api+verify"
                    deal.extraction_confidence = max(deal.extraction_confidence, voting.confidence)
                    if voting.image_url:
                        deal.image_url = voting.image_url

            except TimeoutError:
                logger.debug("_verify_top_deals: page fetch timed out for %s", url)
            except Exception as exc:
                logger.debug("_verify_top_deals: verification failed for %s: %s", url, exc)

            return deal

        verified = await asyncio.gather(*[_verify_one(d) for d in to_verify], return_exceptions=True)

        result: list[DealResult] = []
        for i, item in enumerate(verified):
            if isinstance(item, BaseException):
                logger.debug("_verify_top_deals: unexpected error in gather: %s", item)
                result.append(to_verify[i])  # Keep original deal rather than dropping it
            else:
                result.append(item)

        result.extend(remainder)
        return result

    async def _search_via_web(
        self,
        query: str,
        progress: DealProgressCallback | None = None,
    ) -> list[DealResult]:
        """Search the open web for deals using two targeted query variants.

        Runs two web search queries concurrently, scrapes non-editorial result
        pages, and extracts prices via the price voting engine.  Deduplicates
        by URL.  Used for digital products (subscriptions, software) and as a
        Shopping fallback.

        Args:
            query: Product or service name query.
            progress: Optional progress callback.

        Returns:
            Deduplicated list of DealResult objects with price > 0.
        """
        if not self._search_engine:
            return []

        settings = get_settings()
        timeout = settings.deal_scraper_timeout

        web_queries = [
            f"{query} buy price deal",
            f"{query} best price discount",
        ]

        async def _run_query(web_query: str) -> list[DealResult]:
            try:
                tool_result = await asyncio.wait_for(
                    self._search_engine.search(web_query),
                    timeout=timeout,
                )
            except (TimeoutError, Exception) as exc:
                logger.debug("_search_via_web query failed ('%s'): %s", web_query, exc)
                return []

            if not tool_result or not tool_result.success or not tool_result.data:
                return []

            search_results: SearchResults = tool_result.data
            if not search_results.results:
                return []

            page_deals: list[DealResult] = []
            for item in search_results.results[:8]:
                url = item.link
                if not url or _is_editorial_url(url):
                    continue

                # Skip known editorial/review domains before scraping — they publish
                # articles, not product listings, so scraping them wastes time and
                # would produce source_type="open_web" cards that are not purchasable.
                item_domain = _domain_from_url(url)
                if any(ed in item_domain for ed in EDITORIAL_REVIEW_DOMAINS):
                    logger.debug("_search_via_web: skipping editorial domain %s", item_domain)
                    continue

                store_name = _store_from_url(url) or item_domain
                title = item.title or query

                try:
                    scraped = await asyncio.wait_for(
                        self._scraper.fetch(url),
                        timeout=timeout,
                    )
                    if not scraped.success or not scraped.html:
                        continue

                    voting = vote_on_price(scraped.html, url)
                    if not voting.price or voting.price <= 0:
                        continue

                    discount_pct: float | None = None
                    if voting.original_price and voting.original_price > voting.price:
                        discount_pct = round((voting.original_price - voting.price) / voting.original_price * 100, 1)

                    page_deals.append(
                        DealResult(
                            product_name=voting.product_name or title,
                            store=store_name,
                            price=voting.price,
                            original_price=voting.original_price,
                            discount_percent=discount_pct,
                            url=url,
                            in_stock=voting.in_stock,
                            image_url=voting.image_url,
                            extraction_strategy=voting.winning_strategy or "web_scrape",
                            extraction_confidence=voting.confidence,
                            source_type="open_web",
                            item_category=classify_item_category(
                                text=voting.product_name or title,
                                url=url,
                                store=store_name,
                            ),
                        )
                    )
                except TimeoutError:
                    logger.debug("_search_via_web: fetch timed out for %s", url)
                except Exception as exc:
                    logger.debug("_search_via_web: fetch/vote failed for %s: %s", url, exc)

            return page_deals

        query_results = await asyncio.gather(*[_run_query(q) for q in web_queries], return_exceptions=True)

        seen_urls: set[str] = set()
        combined: list[DealResult] = []
        for result in query_results:
            if isinstance(result, BaseException):
                logger.debug("_search_via_web: gather exception: %s", result)
                continue
            for deal in result:
                if deal.url not in seen_urls:
                    seen_urls.add(deal.url)
                    combined.append(deal)

        logger.debug(
            "_search_via_web: %d unique priced deals for query: %s",
            len(combined),
            query,
        )

        if progress:
            await progress(
                f'Found {len(combined)} web results for "{query}"',
                0,
                None,
                None,
            )

        return combined

    async def _search_coupons_web(self, query: str) -> list[CouponInfo]:
        """Search the web for coupon codes and merge Slickdeals results.

        Runs a web search for coupon/promo codes and converts the top 5 results
        to ``CouponInfo`` objects.  Additionally fetches Slickdeals RSS coupons
        (fire-and-forget style — failures are silently swallowed).

        Args:
            query: Product or store query (e.g. "Adobe Creative Cloud").

        Returns:
            Combined list of CouponInfo objects (may be empty).
        """
        coupons: list[CouponInfo] = []

        if self._search_engine:
            current_year = datetime.datetime.now(tz=datetime.UTC).year
            coupon_query = f"{query} coupon code promo discount {current_year}"

            try:
                settings = get_settings()
                tool_result = await asyncio.wait_for(
                    self._search_engine.search(coupon_query),
                    timeout=settings.deal_scraper_timeout,
                )
                if tool_result and tool_result.success and tool_result.data:
                    search_results: SearchResults = tool_result.data
                    for item in (search_results.results or [])[:5]:
                        if not item.link:
                            continue
                        store_name = _store_from_url(item.link) or _domain_from_url(item.link)
                        coupons.append(
                            CouponInfo(
                                code="",
                                description=item.title or item.snippet or coupon_query,
                                store=store_name,
                                expiry=None,
                                verified=False,
                                source="web_search",
                                confidence=0.3,
                                source_url=item.link,
                            )
                        )
            except Exception as exc:
                logger.debug("_search_coupons_web: web search failed: %s", exc)

        # Slickdeals RSS coupons — best-effort, never blocks the deal search
        try:
            sd_coupons = await fetch_slickdeals_coupons(self._scraper, store=query)
            coupons.extend(sd_coupons)
        except Exception as exc:
            logger.debug("_search_coupons_web: Slickdeals fetch failed: %s", exc)

        return coupons

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
