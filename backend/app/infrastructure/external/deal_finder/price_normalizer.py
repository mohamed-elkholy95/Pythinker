"""Price normalization pipeline for cleaning extracted prices.

Handles common e-commerce price pitfalls:
1. Marketing noise removal ("Was $X", "Save Y%", "From $X/mo")
2. Financing/subscription detection ($49/mo ≠ $49 product price)
3. Bundle/quantity normalization ("2-pack" → per-unit price)
4. Locale-aware number parsing (€1.299,00 → 1299.00)
5. Currency symbol detection

Inspired by HasData/ecommerce-price-scraper toolkit patterns.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Marketing noise patterns — matched BEFORE price extraction
# ──────────────────────────────────────────────────────────────

# Patterns that indicate the number is NOT the selling price
_NOISE_PATTERNS: list[re.Pattern[str]] = [
    # "Save $200", "You save $50"
    re.compile(r"(?:you\s+)?save\s+\$\s*[\d,.]+", re.IGNORECASE),
    # "Was $499", "Reg. $299"
    re.compile(r"(?:was|were|reg\.?|regular|original|list)\s+\$\s*[\d,.]+", re.IGNORECASE),
    # "$49/mo", "$19.99/month", "$5/yr"
    re.compile(r"\$\s*[\d,.]+\s*/\s*(?:mo(?:nth)?|yr|year|week|wk|day)", re.IGNORECASE),
    # "From $19/mo", "Starting at $29"
    re.compile(r"(?:from|starting\s+at|as\s+low\s+as)\s+\$\s*[\d,.]+", re.IGNORECASE),
    # "FREE shipping", "$0.00 shipping"
    re.compile(r"(?:free|no)\s+(?:shipping|delivery)", re.IGNORECASE),
    re.compile(r"\$\s*0\.00\s+(?:shipping|delivery)", re.IGNORECASE),
    # Shipping cost patterns: "+ $5.99 shipping"
    re.compile(r"\+\s*\$\s*[\d,.]+\s*(?:shipping|delivery|s&h)", re.IGNORECASE),
    # "Earn $20 back", "Get $50 gift card"
    re.compile(r"(?:earn|get|receive)\s+\$\s*[\d,.]+\s*(?:back|reward|gift|cashback)", re.IGNORECASE),
    # "Up to $100 off"
    re.compile(r"up\s+to\s+\$\s*[\d,.]+\s*off", re.IGNORECASE),
]

# Patterns that indicate a financing/monthly price (not product price)
_FINANCING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\$\s*[\d,.]+\s*/\s*mo(?:nth)?", re.IGNORECASE),
    re.compile(r"\$\s*[\d,.]+\s+(?:per|a)\s+month", re.IGNORECASE),
    re.compile(r"(?:pay|finance|lease)\s+\$\s*[\d,.]+", re.IGNORECASE),
    re.compile(r"\$\s*[\d,.]+\s*x\s*\d+\s*months?", re.IGNORECASE),
    re.compile(r"\d+\s*(?:monthly\s+)?payments?\s+of\s+\$\s*[\d,.]+", re.IGNORECASE),
]

# Bundle/multi-pack detection
_BUNDLE_PATTERN = re.compile(
    r"(\d+)\s*[-\u2013]?\s*(?:pack|count|ct|pcs?|pieces?|set|units?|pair)",
    re.IGNORECASE,
)

# ──────────────────────────────────────────────────────────────
# Currency detection
# ──────────────────────────────────────────────────────────────

CURRENCY_SYMBOLS: dict[str, str] = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
    "₩": "KRW",
    "₽": "RUB",
    "R$": "BRL",
    "C$": "CAD",
    "A$": "AUD",
    "HK$": "HKD",
    "S$": "SGD",
    "₺": "TRY",
    "kr": "SEK",  # Also NOK/DKK — disambiguated by domain
    "zł": "PLN",
    "฿": "THB",
    "₫": "VND",
    "Rp": "IDR",
    "RM": "MYR",
    "₱": "PHP",
}

# Domain → currency override (for ambiguous symbols like kr, $)
_DOMAIN_CURRENCY: dict[str, str] = {
    ".co.uk": "GBP",
    ".de": "EUR",
    ".fr": "EUR",
    ".it": "EUR",
    ".es": "EUR",
    ".nl": "EUR",
    ".ca": "CAD",
    ".com.au": "AUD",
    ".co.jp": "JPY",
    ".co.kr": "KRW",
    ".com.br": "BRL",
    ".in": "INR",
    ".se": "SEK",
    ".no": "NOK",
    ".dk": "DKK",
    ".pl": "PLN",
    ".com.tr": "TRY",
    ".co.th": "THB",
    ".com.mx": "MXN",
    ".sg": "SGD",
    ".hk": "HKD",
}

# EU-style number format: 1.299,00 (dot as thousands separator, comma as decimal)
_EU_PRICE_PATTERN = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})")
# US-style: 1,299.00 (comma as thousands separator, dot as decimal)
_US_PRICE_PATTERN = re.compile(r"(\d{1,3}(?:,\d{3})*\.\d{2})")
# Plain integer: 1299
_INT_PRICE_PATTERN = re.compile(r"(\d{1,6})")


@dataclass
class NormalizedPrice:
    """Result of price normalization."""

    amount: float
    currency: str = "USD"
    is_financing: bool = False  # True if detected as monthly/financing price
    is_bundle: bool = False  # True if from a multi-pack
    bundle_quantity: int = 1  # Number of items in bundle
    per_unit_price: float | None = None  # amount / bundle_quantity
    raw_text: str = ""  # Original price text before normalization


def detect_currency(price_text: str, url: str = "") -> str:
    """Detect currency from price text and URL domain.

    Priority: domain TLD → explicit symbol → default USD.
    """
    # Check domain first (most reliable)
    for suffix, currency in _DOMAIN_CURRENCY.items():
        if suffix in url.lower():
            return currency

    # Check for explicit currency symbols in text
    for symbol, currency in sorted(CURRENCY_SYMBOLS.items(), key=lambda x: -len(x[0])):
        if symbol in price_text:
            return currency

    return "USD"


def is_financing_price(text: str) -> bool:
    """Check if text describes a financing/monthly payment, not a product price."""
    return any(p.search(text) for p in _FINANCING_PATTERNS)


def is_noise_price(text: str) -> bool:
    """Check if text is marketing noise (savings, shipping, rewards)."""
    return any(p.search(text) for p in _NOISE_PATTERNS)


def detect_bundle_quantity(text: str) -> int:
    """Detect multi-pack quantity from product text.

    Returns 1 if not a bundle/multi-pack.
    """
    match = _BUNDLE_PATTERN.search(text)
    if match:
        qty = int(match.group(1))
        if 2 <= qty <= 100:  # Reasonable bundle sizes
            return qty
    return 1


def parse_price_amount(price_text: str, currency: str = "USD") -> float | None:
    """Parse a price string into a float, handling locale-specific formats.

    EU format: 1.299,00 → 1299.00
    US format: 1,299.00 → 1299.00
    Plain: 1299 → 1299.0
    """
    # Strip currency symbols and whitespace
    cleaned = price_text.strip()
    for symbol in CURRENCY_SYMBOLS:
        cleaned = cleaned.replace(symbol, "")
    cleaned = cleaned.strip()

    # Try EU format first (only if comma appears as decimal separator)
    if currency in ("EUR", "BRL", "PLN", "TRY", "SEK", "NOK", "DKK"):
        eu_match = _EU_PRICE_PATTERN.search(cleaned)
        if eu_match:
            raw = eu_match.group(1).replace(".", "").replace(",", ".")
            try:
                return float(raw)
            except ValueError:
                pass

    # Try US format
    us_match = _US_PRICE_PATTERN.search(cleaned)
    if us_match:
        raw = us_match.group(1).replace(",", "")
        try:
            return float(raw)
        except ValueError:
            pass

    # Try plain number
    plain = re.sub(r"[^\d.]", "", cleaned)
    if plain:
        try:
            return float(plain)
        except ValueError:
            pass

    return None


def normalize_price(
    price_text: str,
    url: str = "",
    product_title: str = "",
) -> NormalizedPrice | None:
    """Full normalization pipeline for a price string.

    Steps:
    1. Detect currency from URL domain and price text
    2. Check for marketing noise → reject
    3. Check for financing/monthly → flag
    4. Parse amount with locale awareness
    5. Detect bundle quantity from product title
    6. Calculate per-unit price if bundle

    Returns None if price cannot be parsed or is noise.
    """
    if not price_text or not price_text.strip():
        return None

    # Step 1: Detect currency
    currency = detect_currency(price_text, url)

    # Step 2: Marketing noise check
    if is_noise_price(price_text):
        logger.debug("Rejected noise price: %s", price_text[:50])
        return None

    # Step 3: Financing detection
    financing = is_financing_price(price_text)

    # Step 4: Parse amount
    amount = parse_price_amount(price_text, currency)
    if amount is None or amount <= 0:
        return None

    # Step 5: Bundle detection (from product title, not price text)
    bundle_qty = detect_bundle_quantity(product_title) if product_title else 1

    # Step 6: Calculate per-unit price
    per_unit = amount / bundle_qty if bundle_qty > 1 else None

    return NormalizedPrice(
        amount=amount,
        currency=currency,
        is_financing=financing,
        is_bundle=bundle_qty > 1,
        bundle_quantity=bundle_qty,
        per_unit_price=per_unit,
        raw_text=price_text.strip(),
    )


def clean_html_price_context(html_snippet: str) -> str:
    """Strip marketing noise from HTML around a price element.

    Used to clean context before feeding to the price voting system.
    Removes known noise patterns while preserving the actual price.
    """
    cleaned = html_snippet
    for pattern in _NOISE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    # Collapse whitespace
    return re.sub(r"\s{2,}", " ", cleaned).strip()
