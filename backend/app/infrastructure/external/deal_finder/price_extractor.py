"""Multi-strategy price extraction from HTML pages.

Strategies (in priority order):
1. JSON-LD: Parse <script type="application/ld+json"> for schema.org/Product → offers.price
2. Store-specific CSS: Per-store selectors for known retailers
3. Generic regex: $XX.XX patterns near product titles (proximity-based)

Each strategy assigns a confidence score (0-1) reflecting reliability:
- json_ld: 0.95 (machine-readable structured data)
- css: 0.80 (known DOM selectors, can break on layout changes)
- generic: 0.30 (regex-based, unreliable)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Confidence scores per strategy
CONFIDENCE_JSON_LD = 0.95
CONFIDENCE_CSS = 0.80
CONFIDENCE_GENERIC = 0.30

# Store-specific CSS selectors for price extraction
STORE_SELECTORS: dict[str, list[str]] = {
    "amazon.com": [
        ".a-price .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        ".a-price-whole",
        "#corePrice_feature_div .a-offscreen",
    ],
    "walmart.com": [
        "[itemprop='price']",
        ".price-characteristic",
        "[data-automation-id='product-price']",
    ],
    "bestbuy.com": [
        ".priceView-customer-price span",
        ".priceView-hero-price span",
        "[data-testid='customer-price'] span",
    ],
    "target.com": [
        "[data-test='product-price']",
        ".styles__CurrentPriceFontSize",
    ],
    "ebay.com": [
        ".x-price-primary span",
        "#prcIsum",
        ".s-item__price",
    ],
    "newegg.com": [
        ".price-current",
        ".product-price",
    ],
    "costco.com": [
        ".price",
        "[automation-id='productPrice']",
        ".your-price",
    ],
    "macys.com": [
        ".lowest-sale-price",
        ".price .discount",
        "[data-auto='product-price']",
    ],
    "homedepot.com": [
        ".price__dollars",
        ".price-format__main-price",
        "[data-price]",
    ],
}

# Original price CSS selectors (strikethrough / was-price elements)
ORIGINAL_PRICE_SELECTORS: dict[str, list[str]] = {
    "amazon.com": [
        ".a-text-price .a-offscreen",
        ".basisPrice .a-offscreen",
        "#listPrice",
    ],
    "walmart.com": [
        "[data-automation-id='was-price']",
        ".was-line-through",
    ],
    "bestbuy.com": [
        ".priceView-original-price span",
    ],
    "target.com": [
        "[data-test='product-regular-price']",
    ],
    "ebay.com": [
        ".x-price-primary .ux-textspans--STRIKETHROUGH",
    ],
    "newegg.com": [
        ".price-was",
    ],
    "costco.com": [
        ".you-save",
    ],
    "macys.com": [
        ".regular-price",
    ],
    "homedepot.com": [
        ".price-format__was-price",
    ],
}

# Regex for $XX.XX price patterns
PRICE_PATTERN = re.compile(r"\$\s*(\d{1,6}(?:,\d{3})*(?:\.\d{2})?)")

# Price validation bounds
_MIN_VALID_PRICE = 0.50
_MAX_VALID_PRICE = 50_000


@dataclass
class ExtractedPrice:
    """Result of price extraction."""

    price: float | None = None
    original_price: float | None = None
    currency: str = "USD"
    product_name: str | None = None
    in_stock: bool = True
    image_url: str | None = None
    strategy_used: str | None = None
    confidence: float = 0.0


def _get_store_domain(url: str) -> str:
    """Extract domain from URL, stripping www. prefix."""
    domain = urlparse(url).netloc.lower()
    return domain.removeprefix("www.")


def _parse_price_string(price_str: str) -> float | None:
    """Parse a price string like '$12.99' or '12,999.00' into a float."""
    match = PRICE_PATTERN.search(price_str)
    if match:
        raw = match.group(1).replace(",", "")
        try:
            return float(raw)
        except ValueError:
            return None
    # Try bare number
    cleaned = re.sub(r"[^\d.]", "", price_str)
    if cleaned:
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _validate_price(price: float) -> bool:
    """Validate that a price is within reasonable bounds.

    Rejects phone numbers, SKUs, shipping costs, and other
    non-product-price numbers that regex might pick up.
    """
    return _MIN_VALID_PRICE <= price <= _MAX_VALID_PRICE


def extract_price_from_jsonld(html: str) -> ExtractedPrice:
    """Extract price from JSON-LD structured data (schema.org/Product).

    This is the most reliable method — works on ~70% of major retailers.
    Also extracts original price from offers.highPrice and priceSpecification.
    """
    result = ExtractedPrice(strategy_used="json_ld", confidence=CONFIDENCE_JSON_LD)
    try:
        # Find all JSON-LD blocks
        pattern = re.compile(
            r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            re.DOTALL | re.IGNORECASE,
        )
        for match in pattern.finditer(html):
            try:
                data = json.loads(match.group(1))
            except (json.JSONDecodeError, ValueError):
                continue

            # Handle @graph arrays
            items = data if isinstance(data, list) else [data]
            if isinstance(data, dict) and "@graph" in data:
                items = data["@graph"]

            for item in items:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("@type", "")
                if isinstance(item_type, list):
                    item_type = item_type[0] if item_type else ""
                if item_type not in ("Product", "IndividualProduct"):
                    continue

                result.product_name = item.get("name")
                image = item.get("image")
                if isinstance(image, list) and image:
                    result.image_url = image[0]
                elif isinstance(image, str):
                    result.image_url = image

                offers = item.get("offers", {})
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}

                price = offers.get("price") or offers.get("lowPrice")
                if price is not None:
                    try:
                        result.price = float(price)
                    except (ValueError, TypeError):
                        parsed = _parse_price_string(str(price))
                        if parsed:
                            result.price = parsed

                # Extract original price from JSON-LD
                if result.price is not None:
                    _extract_jsonld_original_price(result, offers)

                # Check availability
                avail = offers.get("availability", "")
                if "OutOfStock" in str(avail):
                    result.in_stock = False

                if result.price is not None and _validate_price(result.price):
                    return result
                # Reset invalid price
                if result.price is not None and not _validate_price(result.price):
                    result.price = None

    except Exception as exc:
        logger.debug("JSON-LD extraction error: %s", exc)

    return result


def _extract_jsonld_original_price(result: ExtractedPrice, offers: dict) -> None:
    """Extract original/list price from JSON-LD offers data.

    Checks offers.highPrice and priceSpecification with ListPrice type.
    Only sets original_price if it's greater than the current price.
    """
    import contextlib

    original: float | None = None

    # Check highPrice
    high_price = offers.get("highPrice")
    if high_price is not None:
        with contextlib.suppress(ValueError, TypeError):
            original = float(high_price)

    # Check priceSpecification for ListPrice
    if original is None:
        price_specs = offers.get("priceSpecification", [])
        if isinstance(price_specs, dict):
            price_specs = [price_specs]
        if isinstance(price_specs, list):
            for spec in price_specs:
                if not isinstance(spec, dict):
                    continue
                price_type = spec.get("priceType", "")
                if price_type in ("ListPrice", "MSRP", "SRP"):
                    spec_price = spec.get("price")
                    if spec_price is not None:
                        try:
                            original = float(spec_price)
                            break
                        except (ValueError, TypeError):
                            continue

    # Only set if original > current price
    if original is not None and result.price is not None and original > result.price:
        result.original_price = original


def extract_price_from_css(html: str, url: str) -> ExtractedPrice:
    """Extract price using store-specific CSS selectors via BeautifulSoup.

    Also attempts to extract original price from strikethrough/was-price elements.
    """
    result = ExtractedPrice(strategy_used="css", confidence=CONFIDENCE_CSS)
    domain = _get_store_domain(url)

    selectors = STORE_SELECTORS.get(domain)
    if not selectors:
        return result

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        for selector in selectors:
            elements = soup.select(selector)
            for el in elements:
                text = el.get_text(strip=True)
                price = _parse_price_string(text)
                if price and price > 0 and _validate_price(price):
                    result.price = price
                    break
            if result.price is not None:
                break

        # Extract original price from strikethrough selectors
        if result.price is not None:
            orig_selectors = ORIGINAL_PRICE_SELECTORS.get(domain, [])
            for selector in orig_selectors:
                elements = soup.select(selector)
                for el in elements:
                    text = el.get_text(strip=True)
                    orig_price = _parse_price_string(text)
                    if orig_price and orig_price > 0 and _validate_price(orig_price) and orig_price > result.price:
                        result.original_price = orig_price
                        break
                if result.original_price is not None:
                    break

    except Exception as exc:
        logger.debug("CSS extraction error for %s: %s", domain, exc)

    return result


def extract_price_generic(html: str) -> ExtractedPrice:
    """Fallback: proximity-based extraction of $XX.XX patterns.

    Instead of blindly picking the first price on the page, we find the
    product title (<h1> or <title>) and pick the closest valid price match.
    Falls back to first valid price if title detection fails.
    """
    result = ExtractedPrice(strategy_used="generic", confidence=CONFIDENCE_GENERIC)

    matches = list(PRICE_PATTERN.finditer(html))
    if not matches:
        return result

    # Try proximity-based approach: find title position, pick closest price
    title_pos = _find_title_position(html)

    if title_pos is not None:
        # Score matches by proximity to title
        best_match: tuple[float, float] | None = None  # (distance, price)
        for m in matches:
            try:
                val = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if not _validate_price(val):
                continue
            distance = abs(m.start() - title_pos)
            if best_match is None or distance < best_match[0]:
                best_match = (distance, val)

        if best_match is not None:
            result.price = best_match[1]
            return result

    # Fallback: first valid price on the page
    for m in matches:
        try:
            val = float(m.group(1).replace(",", ""))
            if _validate_price(val):
                result.price = val
                return result
        except ValueError:
            continue

    return result


def _find_title_position(html: str) -> int | None:
    """Find the character position of the product title element.

    Looks for <h1> first (most common product title), then <title>.
    Returns the position of the opening tag, or None if not found.
    """
    # Try <h1> first (product page title)
    h1_match = re.search(r"<h1[^>]*>", html, re.IGNORECASE)
    if h1_match:
        return h1_match.start()

    # Fallback to <title>
    title_match = re.search(r"<title[^>]*>", html, re.IGNORECASE)
    if title_match:
        return title_match.start()

    return None


def extract_price(html: str, url: str) -> ExtractedPrice:
    """Extract price using multi-strategy approach.

    Tries JSON-LD → Store CSS → Generic regex, returns first success.
    Each strategy sets a confidence score reflecting reliability.
    """
    # Strategy 1: JSON-LD
    result = extract_price_from_jsonld(html)
    if result.price is not None:
        return result

    # Strategy 2: Store-specific CSS
    result = extract_price_from_css(html, url)
    if result.price is not None:
        return result

    # Strategy 3: Proximity-based generic regex
    return extract_price_generic(html)
