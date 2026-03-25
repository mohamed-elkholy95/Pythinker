"""Tests for source quality assessment models."""

import pytest

from app.domain.models.source_quality import (
    ContentFreshness,
    FilteredSourceResult,
    SourceFilterConfig,
    SourceQualityScore,
    SourceReliability,
)


class TestSourceReliability:
    def test_values(self) -> None:
        assert SourceReliability.HIGH == "high"
        assert SourceReliability.UNKNOWN == "unknown"


class TestContentFreshness:
    def test_values(self) -> None:
        assert ContentFreshness.CURRENT == "current"
        assert ContentFreshness.STALE == "stale"


class TestSourceQualityScore:
    def test_defaults(self) -> None:
        s = SourceQualityScore(url="https://example.com", domain="example.com")
        assert s.reliability_score == 0.5
        assert s.relevance_score == 0.5
        assert s.is_paywalled is False

    def test_composite_score(self) -> None:
        s = SourceQualityScore(
            url="https://example.com",
            domain="example.com",
            reliability_score=1.0,
            relevance_score=1.0,
            freshness_score=1.0,
            content_depth_score=1.0,
        )
        assert s.composite_score == pytest.approx(1.0)

    def test_composite_score_weights(self) -> None:
        s = SourceQualityScore(
            url="https://example.com",
            domain="example.com",
            reliability_score=1.0,
            relevance_score=0.0,
            freshness_score=0.0,
            content_depth_score=0.0,
        )
        # reliability weight = 0.35
        assert s.composite_score == pytest.approx(0.35)

    def test_passes_threshold_good(self) -> None:
        s = SourceQualityScore(
            url="https://example.com",
            domain="example.com",
            reliability_score=0.8,
            relevance_score=0.8,
        )
        assert s.passes_threshold is True

    def test_fails_threshold_paywalled(self) -> None:
        s = SourceQualityScore(
            url="https://example.com",
            domain="example.com",
            reliability_score=0.9,
            relevance_score=0.9,
            is_paywalled=True,
        )
        assert s.passes_threshold is False

    def test_fails_threshold_low_scores(self) -> None:
        s = SourceQualityScore(
            url="https://example.com",
            domain="example.com",
            reliability_score=0.1,
            relevance_score=0.1,
            freshness_score=0.1,
            content_depth_score=0.1,
        )
        assert s.passes_threshold is False


class TestSourceFilterConfig:
    def test_defaults(self) -> None:
        c = SourceFilterConfig()
        assert c.min_composite_score == 0.4
        assert c.max_age_days == 365 * 2


class TestFilteredSourceResult:
    def test_defaults(self) -> None:
        r = FilteredSourceResult()
        assert r.accepted_sources == []
        assert r.rejected_sources == []
        assert r.rejection_reasons == {}
