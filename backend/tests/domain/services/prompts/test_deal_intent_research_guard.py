"""Tests for deal intent detection — research context guard.

Validates that research/analytical queries are NOT falsely classified
as deal intent even when they contain price-related keywords.
"""

import pytest

from app.domain.services.prompts.deal_finding import detect_deal_intent


class TestResearchContextGuard:
    """Research context should suppress deal intent false positives."""

    @pytest.mark.parametrize(
        "query",
        [
            "create a comprehensive research report about: price comparison between EVs and traditional combustion vehicles across major markets",
            "research report about the global electric vehicle market including price comparison",
            "comprehensive analysis of EV market pricing trends across major markets",
            "market research on battery technology and price comparison in the automotive industry",
            "investigate the market landscape for renewable energy pricing",
            "examine the economic impact of EV pricing on consumer adoption",
            "comparative analysis of electric vehicle costs vs gasoline vehicles",
            "industry report on semiconductor pricing trends",
            "study the market for AI chips and compare prices across vendors",
            "analyze the trend of smartphone prices across major markets",
        ],
    )
    def test_research_queries_not_classified_as_deal(self, query: str):
        """Research/analytical queries should NOT trigger deal intent."""
        assert detect_deal_intent(query) is False, f"False positive: {query!r}"

    @pytest.mark.parametrize(
        "query",
        [
            "find me the best deal on a laptop",
            "cheapest iPhone 16 Pro Max",
            "compare prices for AirPods Pro",
            "any coupons for Best Buy?",
            "Amazon price for Kindle Paperwhite",
            "where to buy RTX 5090 cheapest",
            "show me deals on gaming headsets",
            "promo code for Nike shoes",
            "best price for Samsung Galaxy S26",
            "flash sale on electronics today",
        ],
    )
    def test_genuine_deal_queries_still_detected(self, query: str):
        """Genuine deal/shopping queries should still trigger deal intent."""
        assert detect_deal_intent(query) is True, f"Missed deal intent: {query!r}"

    def test_empty_input(self):
        """Empty input returns False."""
        assert detect_deal_intent("") is False
        assert detect_deal_intent("   ") is False

    def test_none_like_input(self):
        """None-like input returns False."""
        assert detect_deal_intent(None) is False  # type: ignore[arg-type]

    def test_ambiguous_but_research_context_wins(self):
        """When both research and deal signals exist, research context suppresses."""
        query = "market analysis of price comparison trends for consumer electronics across major markets"
        assert detect_deal_intent(query) is False

    def test_deal_intent_without_research_context(self):
        """Price comparison without research framing IS deal intent."""
        assert detect_deal_intent("price comparison for MacBook Pro") is True
        assert detect_deal_intent("compare prices of gaming laptops") is True
