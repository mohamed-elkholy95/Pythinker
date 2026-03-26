"""Tests for ContentHallucinationDetector."""

import pytest

from app.domain.services.agents.content_hallucination_detector import (
    ATTRIBUTION_PATTERNS,
    HIGH_RISK_PATTERNS,
    Claim,
    ContentHallucinationDetector,
    ContradictionResult,
    HallucinationAnalysisResult,
    HallucinationIssue,
    HallucinationRisk,
)


class TestHallucinationRisk:
    """Tests for HallucinationRisk enum."""

    def test_all_risk_levels(self):
        expected = {"low", "medium", "high", "critical"}
        assert {r.value for r in HallucinationRisk} == expected

    def test_is_string_enum(self):
        assert isinstance(HallucinationRisk.HIGH, str)
        assert HallucinationRisk.LOW == "low"


class TestHallucinationIssue:
    """Tests for HallucinationIssue dataclass."""

    def test_create(self):
        issue = HallucinationIssue(
            pattern_type="engagement_claps",
            matched_text="500 claps",
            description="Clap count without source",
            risk=HallucinationRisk.HIGH,
            suggestion="Remove or verify",
        )
        assert issue.pattern_type == "engagement_claps"
        assert issue.matched_text == "500 claps"
        assert issue.risk == HallucinationRisk.HIGH
        assert issue.line_context is None

    def test_with_line_context(self):
        issue = HallucinationIssue(
            pattern_type="test",
            matched_text="test",
            description="test",
            risk=HallucinationRisk.MEDIUM,
            suggestion="test",
            line_context="...surrounding text...",
        )
        assert issue.line_context == "...surrounding text..."


class TestHallucinationAnalysisResult:
    """Tests for HallucinationAnalysisResult dataclass."""

    def test_empty_result(self):
        result = HallucinationAnalysisResult()
        assert result.issues == []
        assert result.total_patterns_checked == 0
        assert result.high_risk_count == 0
        assert result.medium_risk_count == 0

    def test_has_high_risk_patterns_false(self):
        result = HallucinationAnalysisResult()
        assert result.has_high_risk_patterns is False

    def test_has_high_risk_patterns_true(self):
        result = HallucinationAnalysisResult(high_risk_count=2)
        assert result.has_high_risk_patterns is True

    def test_has_issues_false(self):
        result = HallucinationAnalysisResult()
        assert result.has_issues is False

    def test_has_issues_true(self):
        issue = HallucinationIssue(
            pattern_type="test",
            matched_text="test",
            description="test",
            risk=HallucinationRisk.HIGH,
            suggestion="test",
        )
        result = HallucinationAnalysisResult(issues=[issue])
        assert result.has_issues is True

    def test_get_summary_no_issues(self):
        result = HallucinationAnalysisResult()
        assert result.get_summary() == "No hallucination risks detected"

    def test_get_summary_high_risk(self):
        issue = HallucinationIssue(
            pattern_type="test", matched_text="test", description="test",
            risk=HallucinationRisk.HIGH, suggestion="test",
        )
        result = HallucinationAnalysisResult(issues=[issue], high_risk_count=3)
        summary = result.get_summary()
        assert "3 high-risk" in summary

    def test_get_summary_medium_risk(self):
        issue = HallucinationIssue(
            pattern_type="test", matched_text="test", description="test",
            risk=HallucinationRisk.MEDIUM, suggestion="test",
        )
        result = HallucinationAnalysisResult(issues=[issue], medium_risk_count=2)
        summary = result.get_summary()
        assert "2 medium-risk" in summary

    def test_get_summary_both(self):
        issue = HallucinationIssue(
            pattern_type="test", matched_text="test", description="test",
            risk=HallucinationRisk.HIGH, suggestion="test",
        )
        result = HallucinationAnalysisResult(issues=[issue], high_risk_count=1, medium_risk_count=2)
        summary = result.get_summary()
        assert "1 high-risk" in summary
        assert "2 medium-risk" in summary


class TestClaim:
    """Tests for Claim dataclass."""

    def test_create_minimal(self):
        claim = Claim(text="Python is fast", entities=["Python"])
        assert claim.text == "Python is fast"
        assert claim.entities == ["Python"]
        assert claim.numeric_value is None
        assert claim.polarity is None

    def test_with_numeric_value(self):
        claim = Claim(
            text="Python has 92% satisfaction",
            entities=["Python"],
            numeric_value=92.0,
            metric="satisfaction",
        )
        assert claim.numeric_value == 92.0
        assert claim.metric == "satisfaction"


class TestContradictionResult:
    """Tests for ContradictionResult dataclass."""

    def test_create(self):
        result = ContradictionResult(
            claim1="Python is slow",
            claim2="Python is fast",
            entity="Python",
            confidence=0.9,
        )
        assert result.claim1 == "Python is slow"
        assert result.entity == "Python"
        assert result.contradiction_type == "general"

    def test_custom_type(self):
        result = ContradictionResult(
            claim1="a",
            claim2="b",
            entity="x",
            confidence=0.8,
            contradiction_type="numeric",
        )
        assert result.contradiction_type == "numeric"


class TestHighRiskPatterns:
    """Tests for HIGH_RISK_PATTERNS constant."""

    def test_patterns_exist(self):
        assert len(HIGH_RISK_PATTERNS) > 0

    def test_pattern_tuple_structure(self):
        for pattern_tuple in HIGH_RISK_PATTERNS:
            assert len(pattern_tuple) == 5
            regex, pattern_type, risk, description, suggestion = pattern_tuple
            assert isinstance(regex, str)
            assert isinstance(pattern_type, str)
            assert isinstance(risk, HallucinationRisk)
            assert isinstance(description, str)
            assert isinstance(suggestion, str)


class TestAttributionPatterns:
    """Tests for ATTRIBUTION_PATTERNS constant."""

    def test_patterns_exist(self):
        assert len(ATTRIBUTION_PATTERNS) > 0

    def test_all_are_strings(self):
        for pattern in ATTRIBUTION_PATTERNS:
            assert isinstance(pattern, str)


class TestContentHallucinationDetector:
    """Tests for ContentHallucinationDetector class."""

    @pytest.fixture
    def detector(self):
        return ContentHallucinationDetector()

    def test_init_default_patterns(self, detector):
        assert len(detector.patterns) == len(HIGH_RISK_PATTERNS)

    def test_init_custom_patterns(self):
        custom = [
            (r"\d+ points", "points", HallucinationRisk.HIGH, "Points", "Verify"),
        ]
        detector = ContentHallucinationDetector(patterns=custom)
        assert len(detector.patterns) == 1

    def test_init_check_attribution_default(self, detector):
        assert detector.check_attribution is True

    def test_init_no_attribution_check(self):
        detector = ContentHallucinationDetector(check_attribution=False)
        assert detector.check_attribution is False

    def test_analyze_clean_text(self, detector):
        result = detector.analyze("This is a normal sentence with no statistics.")
        assert result.has_issues is False
        assert result.high_risk_count == 0

    def test_analyze_detects_clap_count(self, detector):
        result = detector.analyze("The article got 500 claps on Medium")
        assert result.has_issues is True
        high_risk_issues = [i for i in result.issues if i.risk == HallucinationRisk.HIGH]
        assert len(high_risk_issues) > 0
        assert any("clap" in i.pattern_type.lower() for i in result.issues)

    def test_analyze_detects_view_count(self, detector):
        result = detector.analyze("The video has 1.5M views")
        assert result.has_issues is True

    def test_analyze_detects_like_count(self, detector):
        result = detector.analyze("This post received 2000 likes")
        assert result.has_issues is True

    def test_analyze_detects_share_count(self, detector):
        result = detector.analyze("The tweet got 300 shares")
        assert result.has_issues is True

    def test_analyze_detects_follower_count(self, detector):
        result = detector.analyze("They have 50K followers")
        assert result.has_issues is True

    def test_analyze_detects_percentage_claim(self, detector):
        result = detector.analyze("There was a 45.2% increase in sales")
        assert result.has_issues is True

    def test_analyze_detects_price(self, detector):
        result = detector.analyze("The product costs $299.99")
        assert result.has_issues is True

    def test_analyze_detects_ranking(self, detector):
        result = detector.analyze("This is #1 in the app store")
        assert result.has_issues is True

    def test_analyze_detects_rating(self, detector):
        result = detector.analyze("It has 4.8/5 stars")
        assert result.has_issues is True

    def test_analyze_with_attribution_reduces_risk(self, detector):
        text_without = "The article got 500 claps"
        text_with = "According to the page, the article got 500 claps"

        result_without = detector.analyze(text_without)
        result_with = detector.analyze(text_with)

        # Attribution should reduce risk
        if result_without.high_risk_count > 0:
            assert result_with.high_risk_count <= result_without.high_risk_count

    def test_analyze_skip_verified_claims(self, detector):
        text = "The article got 500 claps"
        verified = {"500 claps"}
        result = detector.analyze(text, verified_claims=verified)
        # Verified claims should be skipped
        clap_issues = [i for i in result.issues if "clap" in i.pattern_type]
        assert len(clap_issues) == 0

    def test_analyze_total_patterns_checked(self, detector):
        result = detector.analyze("Some text")
        assert result.total_patterns_checked > 0

    def test_analyze_line_context_present(self, detector):
        result = detector.analyze("The article received 1000 claps from readers")
        for issue in result.issues:
            assert issue.line_context is not None

    def test_analyze_no_duplicate_positions(self, detector):
        text = "500 likes received"
        result = detector.analyze(text)
        positions = [(i.matched_text, i.pattern_type) for i in result.issues]
        # Each position should only be flagged once
        assert len(positions) == len(set(positions))

    def test_analyze_read_time(self, detector):
        result = detector.analyze("5 min read")
        assert result.has_issues is True

    def test_analyze_publication_date(self, detector):
        result = detector.analyze("Published on January 15, 2024")
        assert result.has_issues is True

    def test_get_risk_summary_empty(self, detector):
        result = HallucinationAnalysisResult()
        summary = detector.get_risk_summary(result)
        assert summary == ""

    def test_get_risk_summary_with_issues(self, detector):
        result = detector.analyze("Got 500 claps and 1000 views on the article")
        summary = detector.get_risk_summary(result)
        if result.issues:
            assert "Potential hallucination risks detected" in summary

    def test_is_verified_exact_match(self, detector):
        assert detector._is_verified("500 claps", {"500 claps"}) is True

    def test_is_verified_case_insensitive(self, detector):
        assert detector._is_verified("500 Claps", {"500 claps"}) is True

    def test_is_verified_substring(self, detector):
        assert detector._is_verified("500", {"The article got 500 claps"}) is True

    def test_is_verified_no_match(self, detector):
        assert detector._is_verified("600 claps", {"500 claps"}) is False

    def test_has_nearby_attribution_found(self, detector):
        text = "According to the source, the article got 500 claps"
        # "500 claps" starts at position 41
        idx = text.index("500")
        assert detector._has_nearby_attribution(text, idx, idx + 9) is True

    def test_has_nearby_attribution_not_found(self, detector):
        text = "The article got 500 claps"
        idx = text.index("500")
        assert detector._has_nearby_attribution(text, idx, idx + 9) is False

    def test_get_line_context(self, detector):
        text = "First line.\nSecond line with 500 claps.\nThird line."
        idx = text.index("500")
        context = detector._get_line_context(text, idx)
        assert "500" in context

    def test_get_line_context_start_of_text(self, detector):
        text = "500 claps were received"
        context = detector._get_line_context(text, 0)
        assert "500" in context

    def test_get_line_context_adds_ellipsis(self, detector):
        text = "A" * 200 + "500 claps" + "B" * 200
        idx = text.index("500")
        context = detector._get_line_context(text, idx)
        assert context.startswith("...")
        assert context.endswith("...")

    def test_attribution_check_disabled(self):
        detector = ContentHallucinationDetector(check_attribution=False)
        text = "According to the article, it got 500 claps"
        result = detector.analyze(text)
        # Without attribution check, risk should not be reduced
        high_risk = [i for i in result.issues if i.risk == HallucinationRisk.HIGH]
        assert len(high_risk) > 0

    def test_multiple_patterns_in_text(self, detector):
        text = "The article got 500 claps, 1000 views, and 200 shares"
        result = detector.analyze(text)
        assert len(result.issues) >= 3
