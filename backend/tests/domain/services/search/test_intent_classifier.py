"""Tests for rule-based query intent classification."""

import pytest

from app.domain.services.search.intent_classifier import (
    QueryIntentClassifier,
    SearchIntent,
)


class TestSearchIntent:
    """Verify SearchIntent enum values."""

    def test_intent_values(self):
        assert SearchIntent.QUICK == "quick"
        assert SearchIntent.STANDARD == "standard"
        assert SearchIntent.DEEP == "deep"


class TestQueryIntentClassifier:
    """Test rule-based intent classification."""

    @pytest.fixture()
    def classifier(self):
        return QueryIntentClassifier()

    # --- QUICK intent ---
    @pytest.mark.parametrize(
        "query",
        [
            "what is Python",
            "define machine learning",
            "who is Linus Torvalds",
            "when did WW2 end",
            "where is Tokyo",
            "meaning of API",
        ],
    )
    def test_quick_intent(self, classifier, query):
        assert classifier.classify(query) == SearchIntent.QUICK

    # --- STANDARD intent ---
    @pytest.mark.parametrize(
        "query",
        [
            "compare React vs Vue",
            "best laptop 2026",
            "latest Python release",
            "how to deploy FastAPI",
            "MacBook Pro price",
            "current GPU performance benchmarks",
        ],
    )
    def test_standard_intent(self, classifier, query):
        assert classifier.classify(query) == SearchIntent.STANDARD

    # --- DEEP intent ---
    @pytest.mark.parametrize(
        "query",
        [
            "research quantum computing applications",
            "comprehensive analysis of transformer architectures",
            "pros and cons of microservices vs monolith",
            "in-depth review of cloud providers",
        ],
    )
    def test_deep_intent(self, classifier, query):
        assert classifier.classify(query) == SearchIntent.DEEP

    # --- Default to STANDARD for ambiguous ---
    def test_ambiguous_defaults_to_standard(self, classifier):
        assert classifier.classify("something random about tech") == SearchIntent.STANDARD

    # --- Budget-aware downgrade ---
    def test_budget_downgrade_deep_to_standard(self, classifier):
        result = classifier.classify("comprehensive analysis of AI", quota_remaining_ratio=0.15)
        assert result == SearchIntent.STANDARD

    def test_budget_downgrade_standard_to_quick(self, classifier):
        result = classifier.classify("compare React vs Vue", quota_remaining_ratio=0.08)
        assert result == SearchIntent.QUICK

    def test_budget_downgrade_all_to_quick(self, classifier):
        result = classifier.classify("comprehensive analysis of AI", quota_remaining_ratio=0.03)
        assert result == SearchIntent.QUICK

    def test_no_downgrade_when_budget_healthy(self, classifier):
        result = classifier.classify("comprehensive analysis of AI", quota_remaining_ratio=0.8)
        assert result == SearchIntent.DEEP

    def test_budget_downgrade_at_exact_deep_threshold(self, classifier):
        # ratio exactly equal to threshold → no downgrade (strict < not <=)
        result = classifier.classify("comprehensive analysis of AI", quota_remaining_ratio=0.20)
        assert result == SearchIntent.DEEP

    def test_budget_downgrade_at_exact_standard_threshold(self, classifier):
        result = classifier.classify("compare React vs Vue", quota_remaining_ratio=0.10)
        assert result == SearchIntent.STANDARD

    def test_quick_intent_never_downgraded(self, classifier):
        result = classifier.classify("what is Python", quota_remaining_ratio=0.01)
        assert result == SearchIntent.QUICK

    def test_invalid_ratio_raises(self, classifier):
        with pytest.raises(ValueError, match="quota_remaining_ratio"):
            classifier.classify("test query", quota_remaining_ratio=1.5)

        with pytest.raises(ValueError, match="quota_remaining_ratio"):
            classifier.classify("test query", quota_remaining_ratio=-0.1)
