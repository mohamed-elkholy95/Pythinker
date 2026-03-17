"""Coupon aggregation from RSS feeds and coupon sites.

Sources:
- Slickdeals RSS feeds (frontpage, popular)
- RetailMeNot pages via Scraper
- Coupons.com pages via Scraper

Features deduplication, code validation, and confidence scoring.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING, Any

from app.domain.external.deal_finder import CouponInfo
from app.infrastructure.external.deal_finder.item_classifier import (
    classify_item_category,
    normalize_domain,
)

if TYPE_CHECKING:
    from app.domain.external.scraper import Scraper
    from app.domain.external.search import SearchEngine

logger = logging.getLogger(__name__)

# Slickdeals RSS feed URLs
SLICKDEALS_FEEDS: dict[str, str] = {
    "frontpage": "https://slickdeals.net/newsearch.php?mode=frontpage&searcharea=deals&searchin=first&rss=1",
    "popular": "https://slickdeals.net/newsearch.php?mode=popdeals&searcharea=deals&searchin=first&rss=1",
}

# Coupon code format validation
COUPON_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{3,30}$")
WEB_COUPON_CODE_PATTERN = re.compile(
    r"(?:coupon|promo|discount)\s*(?:code)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-]{2,20})",
    re.IGNORECASE,
)

_IGNORED_WEB_CODES: set[str] = {
    "OFF",
    "SAVE",
    "DEAL",
    "CODE",
    "PROMO",
    "COUPON",
    "SHOP",
    "NOW",
    "FREE",
}

# Curated web-research sources validated from current live coupon/deal sites.
WEB_RESEARCH_SOURCE_DOMAINS: dict[str, dict[str, str]] = {
    "dealnews": {"domain": "dealnews.com", "item_category": "physical"},
    "couponfollow": {"domain": "couponfollow.com", "item_category": "mixed"},
    "groupon": {"domain": "groupon.com", "item_category": "physical"},
    "appsumo": {"domain": "appsumo.com", "item_category": "digital"},
    "stacksocial": {"domain": "stacksocial.com", "item_category": "digital"},
    "slickdeals": {"domain": "slickdeals.net", "item_category": "physical"},
}

# Words that are noise in LLM-generated store names — strip these to extract
# just the store/brand name.  Kept as a set for O(1) lookup.
_STORE_NOISE_WORDS: set[str] = {
    "coupon",
    "coupons",
    "code",
    "codes",
    "promo",
    "promos",
    "promotion",
    "discount",
    "discounts",
    "deal",
    "deals",
    "offer",
    "offers",
    "sale",
    "free",
    "trial",
    "subscription",
    "annual",
    "monthly",
    "pricing",
    "plan",
    "plans",
    "student",
    "top",
    "latest",
    "new",
    "online",
    "2024",
    "2025",
    "2026",
    "2027",
}


def _extract_store_name(raw: str) -> str:
    """Extract the core store/brand name from a verbose LLM-generated string.

    Examples:
        "Cursor AI IDE Subscription Discount Promo Code 2026" → "cursor"
        "Best Buy"                                            → "best buy"
        "retailmenot.com/view/amazon"                         → "amazon"
        "Amazon"                                              → "amazon"
    """
    name = raw.strip().lower()

    # If it already looks like a domain (e.g. "cursor.sh"), extract the base
    domain_match = re.match(r"^(?:https?://)?(?:www\.)?([a-z0-9-]+)\.[a-z]{2,}", name)
    if domain_match:
        return domain_match.group(1)

    # Strip noise words and keep the first 1-3 meaningful tokens
    tokens = re.split(r"[\s,\-/]+", name)
    meaningful = [t for t in tokens if t and t not in _STORE_NOISE_WORDS and len(t) > 1]
    if not meaningful:
        # All words were noise — fall back to first non-empty token
        meaningful = [t for t in tokens if t][:1]

    # Keep at most 3 tokens (enough for "best buy electronics" but not verbose junk)
    return " ".join(meaningful[:3])


# Simple in-memory cache for coupon results
_coupon_cache: dict[str, tuple[float, list[CouponInfo]]] = {}

# Feed-level cache for Slickdeals RSS — keyed by feed URL, stores parsed entries.
# Prevents redundant HTTP fetches when the same feed is queried for different stores.
_feed_cache: dict[str, tuple[float, list[Any]]] = {}

# Per-URL asyncio locks prevent concurrent coroutines from fetching the same
# RSS feed simultaneously (race condition when aggregate_coupons() runs 10 stores
# concurrently via asyncio.gather — without locks, 36 duplicate requests instead of 2).
_feed_cache_locks: dict[str, asyncio.Lock] = {}
_feed_cache_lock_guard = asyncio.Lock()  # protects _feed_cache_locks dict itself


async def _get_feed_lock(url: str) -> asyncio.Lock:
    """Get or create a per-URL lock for feed cache."""
    async with _feed_cache_lock_guard:
        if url not in _feed_cache_locks:
            _feed_cache_locks[url] = asyncio.Lock()
        return _feed_cache_locks[url]


# Negative result cache — remembers sources that returned 404 / no page.
# Keyed by "source:store", value is (timestamp, reason_string).
# 2-hour TTL so we don't permanently block a source if the page appears later.
_NEGATIVE_CACHE_TTL = 7200  # 2 hours
_negative_cache: dict[str, tuple[float, str]] = {}


def _negative_cache_check(key: str) -> str | None:
    """Return the cached failure reason if the key is negatively cached, else None."""
    entry = _negative_cache.get(key)
    if entry is None:
        return None
    ts, reason = entry
    if time.time() - ts >= _NEGATIVE_CACHE_TTL:
        del _negative_cache[key]
        return None
    return reason


def _negative_cache_set(key: str, reason: str) -> None:
    """Record a negative cache entry with the current timestamp."""
    _negative_cache[key] = (time.time(), reason)


def _cache_get(key: str, ttl: int) -> list[CouponInfo] | None:
    """Get cached coupon results if not expired."""
    if key in _coupon_cache:
        timestamp, coupons = _coupon_cache[key]
        if time.time() - timestamp < ttl:
            return coupons
        del _coupon_cache[key]
    return None


def _cache_set(key: str, coupons: list[CouponInfo]) -> None:
    """Cache coupon results with current timestamp."""
    _coupon_cache[key] = (time.time(), coupons)


def _is_valid_coupon_code(code: str) -> bool:
    """Validate that a coupon code matches expected format."""
    return bool(COUPON_CODE_PATTERN.match(code.strip()))


def _score_coupon_confidence(code: str, verified: bool) -> float:
    """Assign a confidence score to a coupon based on code validity and verification.

    - Valid code + verified source → 0.9
    - Valid code + unverified → 0.6
    - No code / invalid code (deal description only) → 0.3
    """
    if not code or not _is_valid_coupon_code(code):
        return 0.3
    return 0.9 if verified else 0.6


def _extract_web_coupon_code(text: str) -> str:
    """Extract a coupon code candidate from search result text."""
    match = WEB_COUPON_CODE_PATTERN.search(text)
    if not match:
        return ""
    code = match.group(1).strip().upper()
    if code in _IGNORED_WEB_CODES:
        return ""
    return code


def _source_name_from_domain(domain: str) -> str:
    """Map domain to a known source name when possible."""
    for source_name, meta in WEB_RESEARCH_SOURCE_DOMAINS.items():
        if domain.endswith(meta["domain"]):
            return source_name
    return "web_research"


# Known slug overrides for stores whose names don't slugify correctly.
# Maps lowercase store name → (retailmenot_slug, couponscom_slug).
_STORE_SLUG_OVERRIDES: dict[str, tuple[str, str]] = {
    "best buy": ("bestbuy", "best-buy"),
    "b&h photo": ("bhphotovideo", "bh-photo"),
    "b&h": ("bhphotovideo", "bh-photo"),
    "micro center": ("microcenter", "micro-center"),
    "home depot": ("homedepot", "home-depot"),
    "macy's": ("macys", "macys"),
}


def _source_url_for_store(store: str, source_name: str) -> list[str]:
    """Build source-specific diagnostic URLs for a store."""
    clean_name = _extract_store_name(store)

    # Use known-slug override when available
    override = _STORE_SLUG_OVERRIDES.get(clean_name)
    if override:
        store_slug_dot, store_slug_dash = override
    else:
        sanitized = clean_name.replace("&", "and").replace("'", "")
        store_slug_dot = sanitized.replace(" ", "")
        store_slug_dash = sanitized.replace(" ", "-")

    if source_name == "retailmenot":
        return [f"https://www.retailmenot.com/view/{store_slug_dot}.com"]
    if source_name == "couponscom":
        return [f"https://www.coupons.com/coupon-codes/{store_slug_dash}"]
    if source_name == "slickdeals":
        return [
            "https://slickdeals.net/newsearch.php?mode=frontpage&searcharea=deals&searchin=first&rss=1",
            "https://slickdeals.net/newsearch.php?mode=popdeals&searcharea=deals&searchin=first&rss=1",
        ]
    if source_name == "web_research":
        return [f"https://www.{meta['domain']}" for meta in WEB_RESEARCH_SOURCE_DOMAINS.values()]
    return []


def build_coupon_source_urls(store: str, sources: list[str] | None) -> list[str]:
    """Build a deduplicated list of coupon source URLs for diagnostics."""
    sources = sources or ["slickdeals", "retailmenot", "couponscom", "web_research"]
    urls: list[str] = []
    seen: set[str] = set()
    for source in sources:
        source_lower = source.lower().strip()
        for url in _source_url_for_store(store, source_lower):
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def _deduplicate_coupons(coupons: list[CouponInfo]) -> list[CouponInfo]:
    """Deduplicate coupons by normalized code or description prefix.

    When duplicates are found, keeps the version with the highest confidence.
    """
    seen: dict[str, CouponInfo] = {}

    for coupon in coupons:
        # Normalize key: uppercase code or first 50 chars of description
        if coupon.code and coupon.code.strip():
            key = f"code:{coupon.code.strip().upper()}"
        else:
            key = f"desc:{coupon.description[:50].strip().lower()}"

        existing = seen.get(key)
        if existing is None or coupon.confidence > existing.confidence:
            seen[key] = coupon

    return list(seen.values())


async def fetch_slickdeals_coupons(
    scraper: Scraper,
    store: str | None = None,
    ttl: int = 3600,
) -> list[CouponInfo]:
    """Fetch deals from Slickdeals RSS feeds.

    Args:
        scraper: Scraper service for HTTP fetching.
        store: Optional store name to filter results.
        ttl: Cache TTL in seconds.

    Returns:
        List of CouponInfo from Slickdeals.
    """
    clean_store = _extract_store_name(store) if store else "all"
    cache_key = f"slickdeals:{clean_store}"
    cached = _cache_get(cache_key, ttl)
    if cached is not None:
        return cached

    coupons: list[CouponInfo] = []
    try:
        import feedparser
    except ImportError:
        logger.warning("feedparser not installed — Slickdeals RSS unavailable")
        return coupons

    for feed_name, feed_url in SLICKDEALS_FEEDS.items():
        try:
            # Acquire a per-URL lock before checking/populating the feed cache.
            # This ensures only one coroutine fetches each RSS feed even when
            # aggregate_coupons() is called concurrently for many stores via
            # asyncio.gather — without this lock, N stores x 2 feeds = 2N duplicate requests.
            feed_lock = await _get_feed_lock(feed_url)
            async with feed_lock:
                # Use feed-level cache to avoid re-fetching the same RSS feed
                # for different store-name queries
                feed_cached = _feed_cache.get(feed_url)
                if feed_cached and time.time() - feed_cached[0] < ttl:
                    entries = feed_cached[1]
                else:
                    result = await scraper.fetch(feed_url)
                    if not result.success or not result.text:
                        continue

                    feed = feedparser.parse(result.text)
                    entries = feed.entries[:20]
                    _feed_cache[feed_url] = (time.time(), list(entries))

                for entry in entries:
                    title = getattr(entry, "title", "")
                    summary = getattr(entry, "summary", "")
                    entry_link = getattr(entry, "link", None)

                    # Filter by store name if provided
                    if store:
                        store_lower = store.lower()
                        if store_lower not in title.lower() and store_lower not in summary.lower():
                            continue

                    code = ""  # Slickdeals RSS doesn't always include codes
                    confidence = _score_coupon_confidence(code, verified=False)

                    coupons.append(
                        CouponInfo(
                            code=code,
                            description=title,
                            store=store or "Various",
                            expiry=None,
                            verified=False,
                            source="slickdeals",
                            confidence=confidence,
                            item_category=classify_item_category(
                                text=f"{title} {summary}", url=entry_link, store=store
                            ),
                            source_url=entry_link,
                        )
                    )

        except Exception as exc:
            logger.debug("Failed to parse Slickdeals %s feed: %s", feed_name, exc)

    _cache_set(cache_key, coupons)
    return coupons


async def fetch_retailmenot_coupons(
    scraper: Scraper,
    store: str,
    ttl: int = 3600,
) -> list[CouponInfo]:
    """Fetch coupons from RetailMeNot for a specific store.

    Args:
        scraper: Scraper service for HTTP fetching.
        store: Store name (used to construct URL).
        ttl: Cache TTL in seconds.

    Returns:
        List of CouponInfo from RetailMeNot.
    """
    # Normalize cache key using extracted store name for consistent caching
    clean_name = _extract_store_name(store)
    cache_key = f"retailmenot:{clean_name}"

    # Short-circuit on negative cache (previous 404 / no-page)
    neg_reason = _negative_cache_check(cache_key)
    if neg_reason is not None:
        logger.debug("RetailMeNot negative cache hit for %s: %s", clean_name, neg_reason)
        return []

    cached = _cache_get(cache_key, ttl)
    if cached is not None:
        return cached

    coupons: list[CouponInfo] = []
    store_slug = clean_name.replace(" ", "").replace("'", "")
    url = f"https://www.retailmenot.com/view/{store_slug}.com"

    try:
        result = await scraper.fetch_with_escalation(url)

        # Detect HTTP 404 — store has no RetailMeNot page
        if hasattr(result, "status") and result.status == 404:
            reason = f"RetailMeNot has no page for '{clean_name}' (HTTP 404)"
            _negative_cache_set(cache_key, reason)
            logger.debug(reason)
            return coupons

        if not result.success or not result.text:
            return coupons

        from scrapling.parser import Adaptor

        page = Adaptor(result.text)

        # Look for coupon code elements
        for offer in page.css("[data-offer-id], .offer-card, .coupon-card"):
            code_el = offer.css(".coupon-code, .code, [data-code]").first
            desc_el = offer.css(".offer-title, .description, h3").first

            code = ""
            if code_el:
                code = code_el.text
                if not code and "data-code" in code_el.attrib:
                    code = code_el.attrib["data-code"]

            description = desc_el.text if desc_el else "Unknown deal"

            # Validate code format
            verified = bool(code) and _is_valid_coupon_code(code)
            if code and not _is_valid_coupon_code(code):
                verified = False

            confidence = _score_coupon_confidence(code, verified)

            # Extract expiry if available
            expiry = None
            expiry_el = offer.css(".expiry, .expiration-date, .expires").first
            if expiry_el:
                expiry = expiry_el.text

            coupons.append(
                CouponInfo(
                    code=code,
                    description=description,
                    store=store,
                    expiry=expiry,
                    verified=verified,
                    source="retailmenot",
                    confidence=confidence,
                    item_category=classify_item_category(text=description, url=url, store=store),
                    source_url=url,
                )
            )

    except Exception as exc:
        logger.debug("Failed to fetch RetailMeNot coupons for %s: %s", store, exc)

    _cache_set(cache_key, coupons)
    return coupons


async def fetch_couponscom_coupons(
    scraper: Scraper,
    store: str,
    ttl: int = 3600,
) -> list[CouponInfo]:
    """Fetch coupons from Coupons.com for a specific store.

    Args:
        scraper: Scraper service for HTTP fetching.
        store: Store name (used to construct URL slug).
        ttl: Cache TTL in seconds.

    Returns:
        List of CouponInfo from Coupons.com.
    """
    # Normalize cache key using extracted store name for consistent caching
    clean_name = _extract_store_name(store)
    cache_key = f"couponscom:{clean_name}"

    # Short-circuit on negative cache (previous 404 / no-page)
    neg_reason = _negative_cache_check(cache_key)
    if neg_reason is not None:
        logger.debug("Coupons.com negative cache hit for %s: %s", clean_name, neg_reason)
        return []

    cached = _cache_get(cache_key, ttl)
    if cached is not None:
        return cached

    coupons: list[CouponInfo] = []
    store_slug = clean_name.replace(" ", "-").replace("'", "")
    url = f"https://www.coupons.com/coupon-codes/{store_slug}"

    try:
        result = await scraper.fetch_with_escalation(url)

        # Detect HTTP 404 — store has no Coupons.com page
        if hasattr(result, "status") and result.status == 404:
            reason = f"Coupons.com has no page for '{clean_name}' (HTTP 404)"
            _negative_cache_set(cache_key, reason)
            logger.debug(reason)
            return coupons

        if not result.success or not result.text:
            return coupons

        from scrapling.parser import Adaptor

        page = Adaptor(result.text)

        for offer in page.css("[data-coupon-id], .coupon-offer, .offer-card"):
            code_el = offer.css(".coupon-code, .code, [data-code]").first
            desc_el = offer.css(".offer-description, .offer-title, h3, p").first

            code = ""
            if code_el:
                code = code_el.text
                if not code and "data-code" in code_el.attrib:
                    code = code_el.attrib["data-code"]

            description = desc_el.text if desc_el else "Unknown deal"

            verified = bool(code) and _is_valid_coupon_code(code)
            if code and not _is_valid_coupon_code(code):
                verified = False

            confidence = _score_coupon_confidence(code, verified)

            # Extract expiry
            expiry = None
            expiry_el = offer.css(".expiry, .expiration-date, .expires").first
            if expiry_el:
                expiry = expiry_el.text

            coupons.append(
                CouponInfo(
                    code=code,
                    description=description,
                    store=store,
                    expiry=expiry,
                    verified=verified,
                    source="couponscom",
                    confidence=confidence,
                    item_category=classify_item_category(text=description, url=url, store=store),
                    source_url=url,
                )
            )

    except Exception as exc:
        logger.debug("Failed to fetch Coupons.com coupons for %s: %s", store, exc)

    _cache_set(cache_key, coupons)
    return coupons


async def fetch_web_research_coupons(
    search_engine: SearchEngine | None,
    store: str,
    ttl: int = 1800,
    max_results: int = 10,
) -> list[CouponInfo]:
    """Fetch coupons by searching latest web sources for store promo pages."""
    if search_engine is None:
        return []

    clean_store = _extract_store_name(store)
    cache_key = f"web_research:{clean_store}"
    cached = _cache_get(cache_key, ttl)
    if cached is not None:
        return cached

    queries = [
        f"{clean_store} coupon code promo code latest",
        f"{clean_store} sale deals online latest",
        f"{clean_store} software subscription discount",
    ]

    tasks = [search_engine.search(query, date_range="past_month") for query in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    coupons: list[CouponInfo] = []
    seen_links: set[str] = set()

    for result in results:
        if isinstance(result, BaseException) or not result or not result.success or not result.data:
            continue
        search_results = result.data.results
        for item in search_results[:max_results]:
            if not item.link or item.link in seen_links:
                continue
            seen_links.add(item.link)

            domain = normalize_domain(item.link)
            source_name = _source_name_from_domain(domain)
            text = f"{item.title} {item.snippet}".strip()
            lowered = text.lower()
            if source_name == "web_research" and not any(
                token in lowered for token in ("coupon", "promo", "discount", "sale", "deal")
            ):
                continue

            code = _extract_web_coupon_code(text)
            verified = bool(code) and _is_valid_coupon_code(code)
            confidence = _score_coupon_confidence(code, verified)
            if source_name != "web_research":
                confidence = min(0.95, confidence + 0.1)

            coupons.append(
                CouponInfo(
                    code=code,
                    description=item.title or item.snippet or "Web coupon mention",
                    store=store,
                    expiry=None,
                    verified=verified,
                    source=source_name,
                    confidence=confidence,
                    item_category=classify_item_category(text=text, url=item.link, store=store),
                    source_url=item.link,
                )
            )

    _cache_set(cache_key, coupons)
    return coupons


def _partition_coupons(
    coupons: list[CouponInfo],
) -> tuple[list[CouponInfo], list[CouponInfo]]:
    """Split coupons into those with actual codes and those without.

    Returns (with_code, without_code) lists preserving input order.
    """
    with_code: list[CouponInfo] = []
    without_code: list[CouponInfo] = []
    for c in coupons:
        if c.code and c.code.strip():
            with_code.append(c)
        else:
            without_code.append(c)
    return with_code, without_code


async def aggregate_coupons(
    scraper: Scraper,
    store: str,
    sources: list[str] | None = None,
    search_engine: SearchEngine | None = None,
    ttl: int = 3600,
) -> tuple[list[CouponInfo], list[dict[str, str]]]:
    """Aggregate coupons from multiple sources with deduplication.

    Args:
        scraper: Scraper service.
        store: Store name to search for.
        sources: Coupon sources to check (default includes web_research).
        search_engine: Optional search engine used by ``web_research`` source.
        ttl: Cache TTL in seconds.

    Returns:
        Tuple of (deduplicated coupons sorted by confidence, source_failures).
        Each source_failure is ``{"source": str, "reason": str}``.
    """
    if sources is None:
        sources = ["slickdeals", "retailmenot", "couponscom", "web_research"]

    # Normalize store name once at entry so all sources use the same cache keys
    store = _extract_store_name(store) if store else store

    # Map source names to their fetch coroutines
    _fetchers: dict[str, Any] = {
        "slickdeals": lambda: fetch_slickdeals_coupons(scraper, store=store, ttl=ttl),
        "retailmenot": lambda: fetch_retailmenot_coupons(scraper, store, ttl=ttl),
        "couponscom": lambda: fetch_couponscom_coupons(scraper, store, ttl=ttl),
        "web_research": lambda: fetch_web_research_coupons(search_engine, store, ttl=min(ttl, 1800)),
    }

    # Build tasks for known sources only
    source_failures: list[dict[str, str]] = []
    tasks: list[tuple[str, Any]] = []
    for source in sources:
        source_lower = source.lower().strip()
        if source_lower == "web_research" and search_engine is None:
            source_failures.append({"source": "web_research", "reason": "Search engine unavailable for web_research"})
            continue
        fetcher = _fetchers.get(source_lower)
        if fetcher is None:
            logger.debug("Unknown coupon source: %s", source_lower)
            continue
        tasks.append((source_lower, fetcher()))

    all_coupons: list[CouponInfo] = []

    if not tasks:
        return all_coupons, source_failures

    # Fetch all sources concurrently
    results = await asyncio.gather(
        *(coro for _, coro in tasks),
        return_exceptions=True,
    )

    for (source_lower, _), result in zip(tasks, results, strict=True):
        if isinstance(result, BaseException):
            logger.debug("Coupon aggregation error for %s/%s: %s", source_lower, store, result)
            source_failures.append({"source": source_lower, "reason": str(result)})
        elif result:
            all_coupons.extend(result)
        else:
            # Empty result — check if there's a negative cache reason
            neg_key = f"{source_lower}:{store}"
            neg_reason = _negative_cache_check(neg_key)
            reason = neg_reason or f"No coupons found for '{store}' on {source_lower}"
            source_failures.append({"source": source_lower, "reason": reason})

    # Deduplicate and sort by confidence (highest first)
    deduplicated = _deduplicate_coupons(all_coupons)
    deduplicated.sort(key=lambda c: c.confidence, reverse=True)

    # Partition: prioritize coupons with actual codes
    with_code, without_code = _partition_coupons(deduplicated)
    # Backfill from no-code coupons only when very few real codes exist
    result = with_code + without_code[: max(0, 3 - len(with_code))] if len(with_code) < 3 else with_code
    return result, source_failures
