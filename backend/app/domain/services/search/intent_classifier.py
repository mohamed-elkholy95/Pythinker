"""Rule-based query intent classification.

Classifies search queries into QUICK/STANDARD/DEEP tiers using
pure regex pattern matching (no LLM calls, <1ms per classification).

Budget-aware downgrade logic automatically lowers intent tier when
the provider quota remaining ratio drops below configured thresholds.
"""

import re
from enum import StrEnum
from typing import ClassVar

from app.core.config import get_settings


class SearchIntent(StrEnum):
    """Search intent tier determining credit allocation."""

    QUICK = "quick"  # 1 API call, basic depth, 10 results
    STANDARD = "standard"  # 1 API call, basic/advanced depth, 20 results
    DEEP = "deep"  # wide_research, advanced depth


class QueryIntentClassifier:
    """Rule-based query intent classification.

    Classifies queries into QUICK/STANDARD/DEEP tiers
    to determine appropriate search depth and credit allocation.
    """

    QUICK_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"\b(what is|define|who is|when did|where is)\b", re.IGNORECASE),
        re.compile(r"\b(meaning of|definition of)\b", re.IGNORECASE),
    ]

    DEEP_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"\b(research|analyze|comprehensive|in-depth|thorough)\b", re.IGNORECASE),
        re.compile(r"\b(pros and cons|advantages and disadvantages)\b", re.IGNORECASE),
    ]

    STANDARD_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"\b(compare|vs|versus|best|latest|review|how to)\b", re.IGNORECASE),
        re.compile(r"\b(current|recent|2025|2026|this year|this month)\b", re.IGNORECASE),
        re.compile(r"\b(price|cost|spec|feature|release|performance)\b", re.IGNORECASE),
    ]

    def classify(
        self,
        query: str,
        quota_remaining_ratio: float = 1.0,
    ) -> SearchIntent:
        """Classify a search query into an intent tier.

        Args:
            query: The search query string.
            quota_remaining_ratio: Fraction of monthly quota remaining (0.0-1.0).
                Used for budget-aware downgrade logic.

        Returns:
            SearchIntent tier (QUICK, STANDARD, or DEEP).
        """
        raw_intent = self._match_patterns(query)
        return self._apply_budget_downgrade(raw_intent, quota_remaining_ratio)

    def _match_patterns(self, query: str) -> SearchIntent:
        """Match query against pattern lists. Order: QUICK → DEEP → STANDARD → default STANDARD."""
        for pattern in self.QUICK_PATTERNS:
            if pattern.search(query):
                return SearchIntent.QUICK

        for pattern in self.DEEP_PATTERNS:
            if pattern.search(query):
                return SearchIntent.DEEP

        for pattern in self.STANDARD_PATTERNS:
            if pattern.search(query):
                return SearchIntent.STANDARD

        # Default: STANDARD (safest middle ground)
        return SearchIntent.STANDARD

    def _apply_budget_downgrade(
        self,
        intent: SearchIntent,
        quota_remaining_ratio: float,
    ) -> SearchIntent:
        """Downgrade intent tier when budget is running low.

        Thresholds from settings:
        - <20% remaining: DEEP → STANDARD
        - <10% remaining: STANDARD → QUICK
        - <5% remaining:  all → QUICK (free scrapers only at router level)
        """
        settings = get_settings()

        # Most restrictive first
        if quota_remaining_ratio < settings.search_budget_degrade_scraper_threshold:
            return SearchIntent.QUICK

        if quota_remaining_ratio < settings.search_budget_degrade_standard_threshold and intent in (
            SearchIntent.STANDARD,
            SearchIntent.DEEP,
        ):
            return SearchIntent.QUICK

        if (
            quota_remaining_ratio < settings.search_budget_degrade_deep_threshold
            and intent == SearchIntent.DEEP
        ):
            return SearchIntent.STANDARD

        return intent
