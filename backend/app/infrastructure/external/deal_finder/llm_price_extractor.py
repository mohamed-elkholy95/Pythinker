"""LLM-powered price extraction fallback.

Uses the project's LLM Protocol to extract prices from HTML when
traditional methods (JSON-LD, CSS, regex) fail or disagree.

Cost: ~$0.001 per extraction with fast-tier models (Haiku, GPT-4o-mini).
Only triggered as fallback — never on first pass.

Design:
- Accepts an LLM instance via parameter (no global state)
- Sends a small HTML context window (~2000 chars around price area)
- Returns a PriceVote that integrates with the voting system
- Rate-limited by the caller (adapter caps at 5 LLM extractions per search)
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from app.infrastructure.external.deal_finder.price_voter import PriceVote

if TYPE_CHECKING:
    from app.domain.external.llm import LLM

logger = logging.getLogger(__name__)

# Confidence for LLM-extracted prices
CONFIDENCE_LLM = 0.85  # Between JSON-LD (0.95) and CSS (0.80)

# Maximum HTML context sent to LLM (chars)
_MAX_CONTEXT_CHARS = 3000

# Regex to find the price-dense area of a page
_PRICE_AREA_PATTERN = re.compile(
    r"(?:<[^>]*(?:price|offer|cost|buy|cart|checkout)[^>]*>)",
    re.IGNORECASE,
)


def _extract_price_context(html: str, url: str) -> str:
    """Extract the most price-relevant portion of HTML for LLM analysis.

    Strategy:
    1. Find price-related DOM areas (price, offer, buy, cart)
    2. Extract surrounding context (500 chars before + after)
    3. If no price area found, use first 3000 chars (usually has product info)
    """
    # Find price-related areas
    matches = list(_PRICE_AREA_PATTERN.finditer(html))
    if matches:
        # Use the first match as anchor, extract surrounding context
        match = matches[0]
        start = max(0, match.start() - 500)
        end = min(len(html), match.end() + 2500)
        context = html[start:end]
    else:
        # Fallback: head of document (product info usually near top)
        context = html[:_MAX_CONTEXT_CHARS]

    # Strip script/style tags to reduce noise
    context = re.sub(r"<script[^>]*>.*?</script>", "", context, flags=re.DOTALL | re.IGNORECASE)
    context = re.sub(r"<style[^>]*>.*?</style>", "", context, flags=re.DOTALL | re.IGNORECASE)
    # Strip excessive whitespace
    context = re.sub(r"\s{3,}", " ", context)

    return context[:_MAX_CONTEXT_CHARS]


async def extract_price_with_llm(
    html: str,
    url: str,
    llm: LLM,
    product_hint: str = "",
) -> PriceVote:
    """Extract price from HTML using LLM as fallback.

    Args:
        html: Full page HTML
        url: Product page URL
        llm: LLM service instance (injected by caller)
        product_hint: Optional product name hint for context

    Returns:
        PriceVote with extracted price data
    """
    context = _extract_price_context(html, url)
    hint_text = f"\nProduct hint: {product_hint}" if product_hint else ""

    messages = [
        {
            "role": "system",
            "content": (
                "You are a price extraction specialist. Extract the current selling price "
                "from the HTML snippet. Return ONLY valid JSON, no markdown."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Extract the product price from this e-commerce page HTML.\n"
                f"URL: {url}\n"
                f"{hint_text}\n\n"
                f"HTML context:\n{context}\n\n"
                f"Return JSON with these fields:\n"
                f'{{"price": <float|null>, "original_price": <float|null>, '
                f'"currency": "<str>", "in_stock": <bool>, '
                f'"product_name": "<str|null>", "confidence": <float 0-1>}}\n\n'
                f"Rules:\n"
                f"- Return the ACTUAL current selling price, not monthly/financing\n"
                f"- Ignore shipping costs, rewards, and savings amounts\n"
                f"- If multiple prices, return the main product price\n"
                f"- Set confidence based on how clear the price is (0.9 if obvious, 0.5 if ambiguous)\n"
                f"- Return null for price if truly cannot determine"
            ),
        },
    ]

    try:
        # Use fast model for cost efficiency
        settings_model = None
        try:
            from app.core.config import get_settings

            settings = get_settings()
            if settings.adaptive_model_selection_enabled and settings.fast_model:
                settings_model = settings.fast_model
        except Exception:
            logger.debug("Settings unavailable for model selection, using default")

        response = await llm.ask(
            messages=messages,
            model=settings_model,
            temperature=0.1,  # Low temperature for deterministic extraction
            max_tokens=200,  # Small response expected
            enable_caching=False,  # Each page is unique
        )

        # Parse response content
        content = response.get("content", "") if isinstance(response, dict) else str(response)

        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'\{[^{}]*"price"[^{}]*\}', content, re.DOTALL)
        if not json_match:
            # Try broader match for nested JSON
            json_match = re.search(r"\{.*\}", content, re.DOTALL)

        if not json_match:
            logger.debug("LLM price extraction: no JSON in response for %s", url[:60])
            return PriceVote(price=None, method="llm", confidence=0.0)

        data = json.loads(json_match.group())

        price = data.get("price")
        if price is not None:
            price = float(price)
            if price <= 0 or price > 50_000:
                price = None

        original_price = data.get("original_price")
        if original_price is not None:
            original_price = float(original_price)
            if original_price <= 0:
                original_price = None

        llm_confidence = float(data.get("confidence", 0.7))
        # Scale LLM's self-reported confidence by our base confidence
        final_confidence = CONFIDENCE_LLM * llm_confidence

        return PriceVote(
            price=price,
            method="llm",
            confidence=final_confidence,
            original_price=original_price,
            product_name=data.get("product_name"),
            in_stock=data.get("in_stock", True),
        )

    except json.JSONDecodeError as exc:
        logger.debug("LLM price extraction: JSON parse error for %s: %s", url[:60], exc)
        return PriceVote(price=None, method="llm", confidence=0.0)
    except Exception as exc:
        logger.warning("LLM price extraction failed for %s: %s", url[:60], exc)
        return PriceVote(price=None, method="llm", confidence=0.0)
