"""Tests for enhanced two-tier query deduplication."""

import pytest

from app.domain.services.search.dedup_enhanced import EnhancedDedup


class TestJaccardSimilarity:
    """Test word-level Jaccard similarity."""

    def test_identical_sets(self):
        assert EnhancedDedup.jaccard_similarity({"a", "b", "c"}, {"a", "b", "c"}) == 1.0

    def test_disjoint_sets(self):
        assert EnhancedDedup.jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self):
        # Intersection: {b}, Union: {a, b, c} → 1/3
        result = EnhancedDedup.jaccard_similarity({"a", "b"}, {"b", "c"})
        assert abs(result - 1 / 3) < 0.01

    def test_empty_sets(self):
        assert EnhancedDedup.jaccard_similarity(set(), set()) == 0.0

    def test_one_empty(self):
        assert EnhancedDedup.jaccard_similarity({"a"}, set()) == 0.0


class TestEnhancedDedup:
    """Test two-tier dedup: normalized string + Jaccard similarity."""

    @pytest.fixture()
    def dedup(self):
        return EnhancedDedup(similarity_threshold=0.6)

    # --- Tier 1: Exact string match ---
    def test_exact_duplicate(self, dedup):
        queries = ["best laptop 2026"]
        assert dedup.is_duplicate("best laptop 2026", queries) is True

    def test_case_insensitive(self, dedup):
        queries = ["Best Laptop 2026"]
        assert dedup.is_duplicate("best laptop 2026", queries) is True

    def test_extra_whitespace(self, dedup):
        queries = ["best  laptop   2026"]
        assert dedup.is_duplicate("best laptop 2026", queries) is True

    # --- Tier 2: Jaccard similarity ---
    def test_paraphrased_catches_high_overlap(self, dedup):
        queries = ["best laptop 2026"]
        assert dedup.is_duplicate("top laptops this year 2026", queries) is True

    def test_different_query_passes(self, dedup):
        queries = ["best laptop 2026"]
        assert dedup.is_duplicate("Python asyncio tutorial", queries) is False

    def test_empty_session_never_duplicate(self, dedup):
        assert dedup.is_duplicate("any query", []) is False

    # --- Stopword filtering ---
    def test_stopwords_stripped(self, dedup):
        queries = ["what is the best laptop for programming"]
        assert dedup.is_duplicate("what is the best laptop for programming", queries) is True

    # --- Custom threshold ---
    def test_strict_threshold(self):
        strict_dedup = EnhancedDedup(similarity_threshold=0.9)
        queries = ["best laptop 2026"]
        # "top laptops this year" has low Jaccard with strict threshold
        assert strict_dedup.is_duplicate("top laptops this year", queries) is False
