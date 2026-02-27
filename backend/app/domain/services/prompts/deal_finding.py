"""Deal-finding prompt module.

Provides specialized prompt rules for deal-finding tasks so the agent
uses the dedicated deal tools (deal_search, deal_compare_prices,
deal_find_coupons) instead of generic browser browsing.
"""

from __future__ import annotations

import re

# ============================================================================
# DEAL INTENT DETECTION
# ============================================================================

# ---------------------------------------------------------------------------
# Two-tier detection: keyword presence + contextual patterns.
# Tier 1: High-confidence standalone keywords that always imply deal intent.
# Tier 2: Action + object patterns (e.g. "find cheapest laptop").
# ---------------------------------------------------------------------------

# Tier 1 — high-confidence multi-word phrases (any match → deal intent).
# Single words like "deal" or "coupon" are intentionally excluded to avoid
# false positives ("explain the deal with quantum computing").
_DEAL_KEYWORDS: frozenset[str] = frozenset(
    {
        "promo code",
        "promo codes",
        "coupon code",
        "coupon codes",
        "discount code",
        "discount codes",
        "voucher code",
        "voucher codes",
        "price match",
        "price check",
        "price drop",
        "price alert",
        "deal finder",
        "deal finding",
        "price compare",
        "price comparison",
        "cashback",
        "cash back",
        "best deal",
        "best deals",
        "best price",
        "lowest price",
        "cheapest price",
        "flash sale",
        "clearance sale",
        "black friday",
        "cyber monday",
        "prime day",
        "compare prices",
    }
)

# Tier 2 — contextual regex patterns
_DEAL_INTENT_PATTERNS: list[re.Pattern[str]] = [
    # ACTION + deal noun: "find deals", "search for bargains", "hunt for coupons"
    re.compile(
        r"\b(?:find|search|look\s+for|get|hunt|show|give)\b.{0,30}"
        r"\b(?:deal|deals|discount|coupon|bargain|offer|sale|promo)s?\b",
        re.IGNORECASE,
    ),
    # COMPARISON intent: "compare prices", "side by side comparison", "which is cheaper"
    re.compile(
        r"\b(?:compare|comparison|versus|vs\.?|side\s+by\s+side)\b.{0,20}\b(?:price|prices|cost|costs)\b",
        re.IGNORECASE,
    ),
    # SUPERLATIVE + price: "best price", "lowest price", "cheapest", "most affordable"
    re.compile(
        r"\b(?:best|lowest|cheapest|cheap|most\s+affordable|budget|inexpensive)\s+(?:price|cost|option|deal)\b",
        re.IGNORECASE,
    ),
    # PURCHASE intent: "where to buy", "how to get it cheaper", "buy for less"
    re.compile(
        r"\b(?:where|how)\s+(?:to\s+)?(?:buy|purchase|order|get\s+it\s+cheap)",
        re.IGNORECASE,
    ),
    # Standalone superlative product queries: "cheapest laptop", "cheapest headphones"
    re.compile(
        r"\b(?:cheapest|lowest[\s-]priced?|most\s+affordable|budget)\s+\w+",
        re.IGNORECASE,
    ),
    # SALE context: "on sale", "flash sale", "limited time", "black friday"
    re.compile(
        r"\b(?:on\s+sale|flash\s+sale|limited\s+time|black\s+friday|cyber\s+monday|prime\s+day)\b",
        re.IGNORECASE,
    ),
    # SAVINGS questions: "how much can I save", "any savings", "save money on"
    re.compile(
        r"\b(?:save|savings|saving)\s+(?:money\s+)?(?:on|for|with)?\b",
        re.IGNORECASE,
    ),
    # PRICE questions: "how much does X cost", "what's the price", "pricing for"
    re.compile(
        r"\b(?:how\s+much\s+(?:does|do|is|are|for|will)|what(?:'s|\s+is)\s+the\s+price)\b",
        re.IGNORECASE,
    ),
    # Explicit deal-related qualifiers: "best deal", "good deal", "any deals"
    re.compile(
        r"\b(?:best|good|great|top|amazing|any)\s+deals?\b",
        re.IGNORECASE,
    ),
    # "voucher(s) for [Store]", "any coupons for [Store]" (require preceding "any"/"find"/"get")
    re.compile(
        r"\b(?:any|find|get|have|got)\s+(?:vouchers?|coupons?|bargains?)\s+(?:for|at|on)\b",
        re.IGNORECASE,
    ),
    # Retailer + price context: "amazon price", "walmart deal", "bestbuy discount"
    re.compile(
        r"\b(?:amazon|walmart|bestbuy|best\s+buy|target|costco|ebay|newegg)\b.{0,15}"
        r"\b(?:price|deal|discount|coupon|sale|offer)\b",
        re.IGNORECASE,
    ),
    # "which is cheaper", "which costs less"
    re.compile(
        r"\bwhich\b.{0,20}\b(?:cheap|cheaper|cheapest|less|lowest|affordable)\b",
        re.IGNORECASE,
    ),
]

# Pre-compiled lowercase keyword set for fast substring matching
_DEAL_KEYWORD_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(kw) for kw in sorted(_DEAL_KEYWORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def detect_deal_intent(text: str) -> bool:
    """Universal detection of deal / price / coupon / comparison intent.

    Two-tier approach:
    1. **Keyword match** — fast check for high-confidence deal terms.
    2. **Pattern match** — contextual regex for action+object combinations.

    Designed to catch all natural phrasings:
    - "find me the best deal on X"
    - "cheapest laptop under $500"
    - "any coupons for Best Buy?"
    - "compare prices for AirPods"
    - "where to buy iPhone 16"
    - "how much does RTX 4070 cost"
    - "Amazon price for Kindle"

    Used by agent_task_runner to auto-enable DealFinder even when
    ``deal_scraper_enabled`` is False in settings.

    Returns:
        True if the text matches any deal-intent signal.
    """
    if not text or not text.strip():
        return False

    # Tier 1: keyword match (fast, high-confidence)
    if _DEAL_KEYWORD_PATTERN.search(text):
        return True

    # Tier 2: contextual patterns
    return any(p.search(text) for p in _DEAL_INTENT_PATTERNS)


# ============================================================================
# DEAL-FINDING PROMPT RULES
# ============================================================================

DEAL_FINDING_RULES = """
<deal_finding>
## Deal-Finding Execution Protocol

### Tool Priority (MANDATORY ORDER):
1. **deal_search** — ALWAYS use first for product/price searches across retailers
2. **deal_compare_prices** — For comparing specific product URLs side-by-side
3. **deal_find_coupons** — After identifying stores with results (max 2 per task)
4. **info_search_web** — ONLY for supplementary research (e.g. product reviews)
5. **browser_navigate** — ONLY to verify a specific deal URL from tool results

### CRITICAL: Never Use Browser for Price Discovery
- Deal tools search 10+ stores via API instantly (structured, fast, invisible to user)
- Browser-based shopping is SLOW and shows the sandbox screen instead of results
- Only use browser_navigate to VERIFY a specific deal URL that deal_search returned

### Search Strategy:
1. Start broad: `deal_search(query="product name")`
2. If user specifies stores: `deal_search(query="product", stores=["amazon.com", "bestbuy.com"])`
3. Then coupons: `deal_find_coupons(store_name="Amazon")` for top 1-2 stores only
4. Session dedup: do NOT search coupons for the same store with name variants

### Report Deliverable:
1. **Best Deal** callout: price + store + savings percentage
2. Price comparison table (Markdown — enables auto Plotly chart):
   | Store | Price ($) | Original ($) | Discount (%) | Score | Stock |
3. Coupons section: verified first, then unverified, with expiry dates
4. Disclaimer: "Prices checked at [time] and may change. Verify before purchasing."
5. Save as .md file when user asked for a report or comparison

### Freshness Rules:
- Same-day deals: highlight as fresh
- Last 7 days: include normally
- 1-2 months old: flag as possibly expired
- 2+ months old: label as likely expired
- Always show deal age/date when available

### What NOT to Do:
- Do NOT navigate to google.com to search for deals
- Do NOT browse amazon.com manually — deal_search handles it via API
- Do NOT call deal_find_coupons more than twice per task
- Do NOT re-search a store with a different name variant (dedup handles it)
- Do NOT validate deals against the manufacturer's official website
</deal_finding>
"""

# ============================================================================
# DEAL-FINDING PLANNER TEMPLATE
# ============================================================================

DEAL_PLAN_TEMPLATE = """
### Deal-Finding Tasks (price search, deal hunting, coupon finding):
Structure as 3-4 steps using deal-specific tools:

1. "Search for deals on [product] across major retailers" (uses deal_search tool)
2. "Find coupons for top stores with results" (uses deal_find_coupons tool)
3. "Compile deal comparison report with best recommendation"

CRITICAL: Steps MUST use deal_search/deal_compare_prices/deal_find_coupons tools.
Do NOT create steps that browse shopping sites manually via browser.
"""
