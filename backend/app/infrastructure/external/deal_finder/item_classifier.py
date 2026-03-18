"""Heuristics for classifying deals/coupons as digital vs physical items."""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Sources that are primarily software, subscriptions, or downloadable products.
_DIGITAL_FOCUS_DOMAINS: frozenset[str] = frozenset(
    {
        "appsumo.com",
        "stacksocial.com",
        "humblebundle.com",
        "udemy.com",
        "coursera.org",
        "codecademy.com",
        "gumroad.com",
        "itch.io",
        "envato.com",
        "steampowered.com",
    }
)

# Sources that are primarily physical goods or retail inventory.
_PHYSICAL_FOCUS_DOMAINS: frozenset[str] = frozenset(
    {
        "amazon.com",
        "walmart.com",
        "target.com",
        "bestbuy.com",
        "costco.com",
        "newegg.com",
        "microcenter.com",
        "bhphotovideo.com",
        "homedepot.com",
        "lowes.com",
        "macys.com",
        "ebay.com",
        "groupon.com",
    }
)

_DIGITAL_KEYWORDS: frozenset[str] = frozenset(
    {
        "software",
        "subscription",
        "license",
        "activation key",
        "saas",
        "cloud",
        "vpn",
        "hosting",
        "domain",
        "apps",
        "plugin",
        "template",
        "course",
        "ebook",
        "e-book",
        "streaming",
        "ai tool",
        "digital",
        "download",
    }
)

_PHYSICAL_KEYWORDS: frozenset[str] = frozenset(
    {
        "in-store",
        "in store",
        "pickup",
        "shipping",
        "ship",
        "warehouse",
        "furniture",
        "appliance",
        "electronics",
        "headphones",
        "laptop",
        "monitor",
        "phone",
        "grocery",
        "clothing",
        "shoes",
        "toys",
        "physical",
        "hardware",
    }
)


def normalize_domain(url: str | None) -> str:
    """Extract and normalize domain from URL."""
    if not url:
        return ""
    return urlparse(url).netloc.lower().removeprefix("www.")


def _keyword_hits(haystack: str, keywords: frozenset[str]) -> int:
    """Count keyword occurrences in the haystack string."""
    return sum(1 for kw in keywords if kw in haystack)


def classify_item_category(
    *,
    text: str = "",
    url: str | None = None,
    store: str | None = None,
) -> str:
    """Classify item type as ``digital``, ``physical``, or ``unknown``."""
    domain = normalize_domain(url)
    if domain in _DIGITAL_FOCUS_DOMAINS:
        return "digital"
    if domain in _PHYSICAL_FOCUS_DOMAINS:
        return "physical"

    normalized_text = re.sub(r"\s+", " ", " ".join([text, store or "", domain]).strip().lower())
    if not normalized_text:
        return "unknown"

    digital_score = _keyword_hits(normalized_text, _DIGITAL_KEYWORDS)
    physical_score = _keyword_hits(normalized_text, _PHYSICAL_KEYWORDS)

    if digital_score > physical_score and digital_score > 0:
        return "digital"
    if physical_score > digital_score and physical_score > 0:
        return "physical"
    if digital_score > 0 and "subscription" in normalized_text:
        return "digital"
    return "unknown"
