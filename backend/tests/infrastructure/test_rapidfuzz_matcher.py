"""Tests for RapidFuzzMatcher."""

from __future__ import annotations

import pytest

from app.infrastructure.text.rapidfuzz_matcher import RapidFuzzMatcher


@pytest.fixture
def matcher() -> RapidFuzzMatcher:
    return RapidFuzzMatcher()


class TestRapidFuzzMatcherExactMatch:
    def test_exact_match_returns_tuple(self, matcher: RapidFuzzMatcher) -> None:
        choices = ["apple", "banana", "cherry"]
        result = matcher.extract_one("apple", choices, score_cutoff=80.0)
        assert result is not None
        assert result[0] == "apple"

    def test_exact_match_score_is_100(self, matcher: RapidFuzzMatcher) -> None:
        choices = ["python", "rust", "go"]
        result = matcher.extract_one("python", choices, score_cutoff=0.0)
        assert result is not None
        match, score = result
        assert match == "python"
        assert score == pytest.approx(100.0)


class TestRapidFuzzMatcherPartialMatch:
    def test_partial_match_returns_closest_choice(self, matcher: RapidFuzzMatcher) -> None:
        choices = ["FastAPI framework", "Django framework", "Flask framework"]
        result = matcher.extract_one("FastAPI", choices, score_cutoff=50.0)
        assert result is not None
        assert "FastAPI" in result[0]

    def test_partial_match_score_is_float(self, matcher: RapidFuzzMatcher) -> None:
        choices = ["machine learning", "deep learning", "reinforcement learning"]
        result = matcher.extract_one("deep learn", choices, score_cutoff=60.0)
        assert result is not None
        _, score = result
        assert isinstance(score, float)


class TestRapidFuzzMatcherNoMatch:
    def test_no_match_returns_none_when_below_cutoff(self, matcher: RapidFuzzMatcher) -> None:
        choices = ["banana", "cherry", "mango"]
        result = matcher.extract_one("xyxyx", choices, score_cutoff=90.0)
        assert result is None

    def test_empty_choices_returns_none(self, matcher: RapidFuzzMatcher) -> None:
        result = matcher.extract_one("anything", [], score_cutoff=0.0)
        assert result is None


class TestRapidFuzzMatcherScoreCutoff:
    def test_score_cutoff_filters_weak_matches(self, matcher: RapidFuzzMatcher) -> None:
        choices = ["completely different text", "nothing in common here"]
        # Use very high cutoff to force no match
        result = matcher.extract_one("python code", choices, score_cutoff=99.0)
        assert result is None

    def test_zero_score_cutoff_returns_best_available(self, matcher: RapidFuzzMatcher) -> None:
        choices = ["abc", "def", "ghi"]
        result = matcher.extract_one("abc", choices, score_cutoff=0.0)
        assert result is not None

    def test_result_score_meets_cutoff(self, matcher: RapidFuzzMatcher) -> None:
        choices = ["hello world", "goodbye world"]
        cutoff = 70.0
        result = matcher.extract_one("hello world", choices, score_cutoff=cutoff)
        assert result is not None
        _, score = result
        assert score >= cutoff
