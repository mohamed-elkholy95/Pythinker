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

if TYPE_CHECKING:
    from app.domain.external.scraper import Scraper

logger = logging.getLogger(__name__)

# Slickdeals RSS feed URLs
SLICKDEALS_FEEDS: dict[str, str] = {
    "frontpage": "https://slickdeals.net/newsearch.php?mode=frontpage&searcharea=deals&searchin=first&rss=1",
    "popular": "https://slickdeals.net/newsearch.php?mode=popdeals&searcharea=deals&searchin=first&rss=1",
}

# Coupon code format validation
COUPON_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{3,30}$")

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
    "best",
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

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(result.text, "html.parser")

        # Look for coupon code elements
        for offer in soup.select("[data-offer-id], .offer-card, .coupon-card"):
            code_el = offer.select_one(".coupon-code, .code, [data-code]")
            desc_el = offer.select_one(".offer-title, .description, h3")

            code = ""
            if code_el:
                code = code_el.get_text(strip=True)
                if not code and code_el.has_attr("data-code"):
                    code = code_el["data-code"]

            description = desc_el.get_text(strip=True) if desc_el else "Unknown deal"

            # Validate code format
            verified = bool(code) and _is_valid_coupon_code(code)
            if code and not _is_valid_coupon_code(code):
                verified = False

            confidence = _score_coupon_confidence(code, verified)

            # Extract expiry if available
            expiry = None
            expiry_el = offer.select_one(".expiry, .expiration-date, .expires")
            if expiry_el:
                expiry = expiry_el.get_text(strip=True)

            coupons.append(
                CouponInfo(
                    code=code,
                    description=description,
                    store=store,
                    expiry=expiry,
                    verified=verified,
                    source="retailmenot",
                    confidence=confidence,
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

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(result.text, "html.parser")

        for offer in soup.select("[data-coupon-id], .coupon-offer, .offer-card"):
            code_el = offer.select_one(".coupon-code, .code, [data-code]")
            desc_el = offer.select_one(".offer-description, .offer-title, h3, p")

            code = ""
            if code_el:
                code = code_el.get_text(strip=True)
                if not code and code_el.has_attr("data-code"):
                    code = code_el["data-code"]

            description = desc_el.get_text(strip=True) if desc_el else "Unknown deal"

            verified = bool(code) and _is_valid_coupon_code(code)
            if code and not _is_valid_coupon_code(code):
                verified = False

            confidence = _score_coupon_confidence(code, verified)

            # Extract expiry
            expiry = None
            expiry_el = offer.select_one(".expiry, .expiration-date, .expires")
            if expiry_el:
                expiry = expiry_el.get_text(strip=True)

            coupons.append(
                CouponInfo(
                    code=code,
                    description=description,
                    store=store,
                    expiry=expiry,
                    verified=verified,
                    source="couponscom",
                    confidence=confidence,
                )
            )

    except Exception as exc:
        logger.debug("Failed to fetch Coupons.com coupons for %s: %s", store, exc)

    _cache_set(cache_key, coupons)
    return coupons


async def aggregate_coupons(
    scraper: Scraper,
    store: str,
    sources: list[str] | None = None,
    ttl: int = 3600,
) -> tuple[list[CouponInfo], list[dict[str, str]]]:
    """Aggregate coupons from multiple sources with deduplication.

    Args:
        scraper: Scraper service.
        store: Store name to search for.
        sources: Coupon sources to check (default: slickdeals, retailmenot, couponscom).
        ttl: Cache TTL in seconds.

    Returns:
        Tuple of (deduplicated coupons sorted by confidence, source_failures).
        Each source_failure is ``{"source": str, "reason": str}``.
    """
    if sources is None:
        sources = ["slickdeals", "retailmenot", "couponscom"]

    # Normalize store name once at entry so all sources use the same cache keys
    store = _extract_store_name(store) if store else store

    # Map source names to their fetch coroutines
    _fetchers: dict[str, Any] = {
        "slickdeals": lambda: fetch_slickdeals_coupons(scraper, store=store, ttl=ttl),
        "retailmenot": lambda: fetch_retailmenot_coupons(scraper, store, ttl=ttl),
        "couponscom": lambda: fetch_couponscom_coupons(scraper, store, ttl=ttl),
    }

    # Build tasks for known sources only
    tasks: list[tuple[str, Any]] = []
    for source in sources:
        source_lower = source.lower().strip()
        fetcher = _fetchers.get(source_lower)
        if fetcher is None:
            logger.debug("Unknown coupon source: %s", source_lower)
            continue
        tasks.append((source_lower, fetcher()))

    all_coupons: list[CouponInfo] = []
    source_failures: list[dict[str, str]] = []

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
    return deduplicated, source_failures
