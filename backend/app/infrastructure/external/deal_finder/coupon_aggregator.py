"""Coupon aggregation from RSS feeds and coupon sites.

Sources:
- Slickdeals RSS feeds (frontpage, popular)
- RetailMeNot pages via Scraper
- Coupons.com pages via Scraper

Features deduplication, code validation, and confidence scoring.
"""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING

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

# Simple in-memory cache for coupon results
_coupon_cache: dict[str, tuple[float, list[CouponInfo]]] = {}


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
    cache_key = f"slickdeals:{store or 'all'}"
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
            result = await scraper.fetch(feed_url)
            if not result.success or not result.text:
                continue

            feed = feedparser.parse(result.text)
            for entry in feed.entries[:20]:
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
    cache_key = f"retailmenot:{store.lower()}"
    cached = _cache_get(cache_key, ttl)
    if cached is not None:
        return cached

    coupons: list[CouponInfo] = []
    # Normalize store name for URL
    store_slug = store.lower().replace(" ", "").replace("'", "")
    url = f"https://www.retailmenot.com/view/{store_slug}.com"

    try:
        result = await scraper.fetch_with_escalation(url)
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
    cache_key = f"couponscom:{store.lower()}"
    cached = _cache_get(cache_key, ttl)
    if cached is not None:
        return cached

    coupons: list[CouponInfo] = []
    store_slug = store.lower().replace(" ", "-").replace("'", "")
    url = f"https://www.coupons.com/coupon-codes/{store_slug}"

    try:
        result = await scraper.fetch_with_escalation(url)
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
) -> list[CouponInfo]:
    """Aggregate coupons from multiple sources with deduplication.

    Args:
        scraper: Scraper service.
        store: Store name to search for.
        sources: Coupon sources to check (default: slickdeals, retailmenot, couponscom).
        ttl: Cache TTL in seconds.

    Returns:
        Deduplicated list of CouponInfo from all sources, sorted by confidence.
    """
    if sources is None:
        sources = ["slickdeals", "retailmenot", "couponscom"]

    all_coupons: list[CouponInfo] = []

    for source in sources:
        source_lower = source.lower().strip()
        try:
            if source_lower == "slickdeals":
                coupons = await fetch_slickdeals_coupons(scraper, store=store, ttl=ttl)
                all_coupons.extend(coupons)
            elif source_lower == "retailmenot":
                coupons = await fetch_retailmenot_coupons(scraper, store, ttl=ttl)
                all_coupons.extend(coupons)
            elif source_lower == "couponscom":
                coupons = await fetch_couponscom_coupons(scraper, store, ttl=ttl)
                all_coupons.extend(coupons)
            else:
                logger.debug("Unknown coupon source: %s", source_lower)
        except Exception as exc:
            logger.debug("Coupon aggregation error for %s/%s: %s", source_lower, store, exc)

    # Deduplicate and sort by confidence (highest first)
    deduplicated = _deduplicate_coupons(all_coupons)
    deduplicated.sort(key=lambda c: c.confidence, reverse=True)
    return deduplicated
