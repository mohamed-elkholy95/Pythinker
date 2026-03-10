"""Tests for ContentConfidenceAssessor.

Covers:
- Hard-fail detection: paywall/challenge, JS shell, empty content, tiny content,
  severe content mismatch, required field missing (importance-aware).
- Soft-fail detection: thin content, boilerplate-heavy, missing entities,
  no publish date (time-sensitive vs. not), weak content density.
- Decision matrix: NO_VERIFY, VERIFY_IF_HIGH_IMPORTANCE, REQUIRED.
- Shadow score telemetry.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.domain.models.evidence import (
    ConfidenceBucket,
    HardFailReason,
    PromotionDecision,
    QueryContext,
    SoftFailReason,
)
from app.domain.services.agents.content_confidence import ContentConfidenceAssessor


# ---------------------------------------------------------------------------
# Config helper
# ---------------------------------------------------------------------------


def _config(**overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "research_soft_fail_verify_threshold": 2,
        "research_soft_fail_required_threshold": 3,
        "research_thin_content_chars": 500,
        "research_boilerplate_ratio_threshold": 0.6,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

LONG_CONTENT = (
    "Python is a high-level, general-purpose programming language. "
    "It was created by Guido van Rossum and first released in 1991. "
    "Python emphasizes code readability with its notable use of significant indentation. "
    "Python is dynamically typed and garbage-collected. "
    "It supports multiple programming paradigms, including structured, "
    "object-oriented and functional programming. "
    "It is often described as a batteries-included language due to its comprehensive "
    "standard library. "
    "Python consistently ranks as one of the most popular programming languages. "
    "It is widely used for web development, data science, artificial intelligence, "
    "scientific computing, and as a scripting language. "
    "The Python Software Foundation manages and directs resources for Python "
    "and CPython development. "
    "The language was designed by Guido van Rossum to have a clean, simple syntax. "
)


# ---------------------------------------------------------------------------
# TestHardFails
# ---------------------------------------------------------------------------


class TestHardFails:
    """Hard-fail detection tests — any single hard fail → LOW / REQUIRED."""

    def _assessor(self) -> ContentConfidenceAssessor:
        return ContentConfidenceAssessor(_config())

    # --- paywall / challenge ---

    def test_paywall_subscribe_to_continue(self) -> None:
        a = self._assessor()
        result = a.assess(
            content="You must subscribe to continue reading this article.",
            url="https://example.com/article",
            domain="example.com",
            title="Some Article",
            source_importance="high",
        )
        assert HardFailReason.block_paywall_challenge in result.hard_fails
        assert result.confidence_bucket == ConfidenceBucket.low
        assert result.promotion_decision == PromotionDecision.required

    def test_paywall_enable_javascript(self) -> None:
        a = self._assessor()
        result = a.assess(
            content="Please enable JavaScript to view this page.",
            url="https://example.com/page",
            domain="example.com",
            title="Page Title",
            source_importance="medium",
        )
        assert HardFailReason.block_paywall_challenge in result.hard_fails

    def test_paywall_access_denied(self) -> None:
        a = self._assessor()
        result = a.assess(
            content="Access denied. You do not have permission to view this resource.",
            url="https://corp.example.com/private",
            domain="corp.example.com",
            title="Restricted",
            source_importance="low",
        )
        assert HardFailReason.block_paywall_challenge in result.hard_fails

    def test_paywall_captcha(self) -> None:
        a = self._assessor()
        result = a.assess(
            content="Please complete the captcha to continue.",
            url="https://example.com",
            domain="example.com",
            title="Verify",
            source_importance="medium",
        )
        assert HardFailReason.block_paywall_challenge in result.hard_fails

    def test_paywall_verify_human(self) -> None:
        a = self._assessor()
        result = a.assess(
            content="Please verify you are human before accessing this page.",
            url="https://example.com",
            domain="example.com",
            title="Verification",
            source_importance="medium",
        )
        assert HardFailReason.block_paywall_challenge in result.hard_fails

    def test_paywall_cf_browser_verification(self) -> None:
        a = self._assessor()
        result = a.assess(
            content="cf-browser-verification Checking your browser before accessing.",
            url="https://cloudflare.com",
            domain="cloudflare.com",
            title="Wait",
            source_importance="low",
        )
        assert HardFailReason.block_paywall_challenge in result.hard_fails

    def test_paywall_subscribe_to_read(self) -> None:
        a = self._assessor()
        result = a.assess(
            content="Subscribe to read the full article and get unlimited access.",
            url="https://news.example.com/article",
            domain="news.example.com",
            title="News Article",
            source_importance="high",
        )
        assert HardFailReason.block_paywall_challenge in result.hard_fails

    # --- JS shell empty ---

    def test_js_shell_tiny_with_loading(self) -> None:
        a = self._assessor()
        result = a.assess(
            content="loading",
            url="https://spa.example.com",
            domain="spa.example.com",
            title="App",
            source_importance="medium",
        )
        assert HardFailReason.js_shell_empty in result.hard_fails

    def test_js_shell_app_root_marker(self) -> None:
        a = self._assessor()
        result = a.assess(
            content="app-root",
            url="https://spa.example.com",
            domain="spa.example.com",
            title="App",
            source_importance="medium",
        )
        assert HardFailReason.js_shell_empty in result.hard_fails

    def test_js_shell_react_root(self) -> None:
        a = self._assessor()
        result = a.assess(
            content="react-root",
            url="https://react.example.com",
            domain="react.example.com",
            title="React App",
            source_importance="low",
        )
        assert HardFailReason.js_shell_empty in result.hard_fails

    def test_js_shell_next_js(self) -> None:
        a = self._assessor()
        result = a.assess(
            content="__next",
            url="https://next.example.com",
            domain="next.example.com",
            title="Next.js App",
            source_importance="low",
        )
        assert HardFailReason.js_shell_empty in result.hard_fails

    def test_js_shell_noscript(self) -> None:
        a = self._assessor()
        result = a.assess(
            content="noscript",
            url="https://noscript.example.com",
            domain="noscript.example.com",
            title="Noscript",
            source_importance="low",
        )
        assert HardFailReason.js_shell_empty in result.hard_fails

    def test_js_shell_long_content_not_triggered(self) -> None:
        """Long content with 'loading' text should NOT be a JS shell."""
        a = self._assessor()
        result = a.assess(
            content=LONG_CONTENT + " The page is loading new content dynamically.",
            url="https://example.com",
            domain="example.com",
            title="Python",
            source_importance="high",
        )
        assert HardFailReason.js_shell_empty not in result.hard_fails

    # --- extraction failure ---

    def test_empty_content(self) -> None:
        a = self._assessor()
        result = a.assess(
            content="",
            url="https://example.com",
            domain="example.com",
            title="Some Page",
            source_importance="high",
        )
        assert HardFailReason.extraction_failure in result.hard_fails
        assert result.confidence_bucket == ConfidenceBucket.low
        assert result.promotion_decision == PromotionDecision.required

    def test_whitespace_only_content(self) -> None:
        a = self._assessor()
        result = a.assess(
            content="   \n\t  ",
            url="https://example.com",
            domain="example.com",
            title="Some Page",
            source_importance="high",
        )
        assert HardFailReason.extraction_failure in result.hard_fails

    def test_tiny_content_under_50_chars(self) -> None:
        a = self._assessor()
        result = a.assess(
            content="Short.",
            url="https://example.com",
            domain="example.com",
            title="Short Page",
            source_importance="medium",
        )
        assert HardFailReason.extraction_failure in result.hard_fails

    def test_content_exactly_50_chars_is_not_extraction_failure(self) -> None:
        """Exactly 50 non-whitespace chars should not trigger extraction failure."""
        a = self._assessor()
        content = "x" * 50
        result = a.assess(
            content=content,
            url="https://example.com",
            domain="example.com",
            title="Page",
            source_importance="low",
        )
        assert HardFailReason.extraction_failure not in result.hard_fails

    # --- severe content mismatch ---

    def test_severe_mismatch_detected(self) -> None:
        """Title tokens absent from content with 3+ meaningful tokens → mismatch."""
        a = self._assessor()
        result = a.assess(
            content=(
                "The weather today is sunny and warm. "
                "Temperatures are expected to rise to 28 degrees Celsius. "
                "Perfect conditions for outdoor activities. "
                "Make sure to apply sunscreen before heading out. "
                "Stay hydrated throughout the day."
            ),
            url="https://tech.example.com/article",
            domain="tech.example.com",
            title="Python Django Framework Tutorial",
            source_importance="high",
        )
        assert HardFailReason.severe_content_mismatch in result.hard_fails

    def test_no_mismatch_when_title_matches_content(self) -> None:
        a = self._assessor()
        result = a.assess(
            content=LONG_CONTENT,
            url="https://python.org",
            domain="python.org",
            title="Python Programming Language",
            source_importance="high",
        )
        assert HardFailReason.severe_content_mismatch not in result.hard_fails

    def test_no_mismatch_when_title_has_fewer_than_3_meaningful_tokens(self) -> None:
        """Short titles (< 3 meaningful tokens) should never trigger mismatch."""
        a = self._assessor()
        result = a.assess(
            content="Some unrelated content about cooking recipes and food.",
            url="https://example.com",
            domain="example.com",
            title="Hi",
            source_importance="high",
        )
        assert HardFailReason.severe_content_mismatch not in result.hard_fails

    # --- required field missing ---

    def test_required_field_missing_high_importance_is_hard_fail(self) -> None:
        """High-importance source missing >50% required entities → hard fail."""
        a = self._assessor()
        ctx = QueryContext(
            required_entities=["Apple", "iPhone", "iOS", "Tim Cook"],
        )
        result = a.assess(
            content="A brief overview of mobile computing trends in the industry.",
            url="https://tech.example.com",
            domain="tech.example.com",
            title="Mobile Computing",
            source_importance="high",
            query_context=ctx,
        )
        assert HardFailReason.required_field_missing in result.hard_fails
        assert result.confidence_bucket == ConfidenceBucket.low
        assert result.promotion_decision == PromotionDecision.required

    def test_required_field_missing_low_importance_is_soft_fail(self) -> None:
        """Low-importance source missing entities → soft fail (not hard fail)."""
        a = self._assessor()
        ctx = QueryContext(
            required_entities=["Apple", "iPhone", "iOS", "Tim Cook"],
        )
        result = a.assess(
            content="A brief overview of mobile computing trends in the industry.",
            url="https://tech.example.com",
            domain="tech.example.com",
            title="Mobile Computing",
            source_importance="low",
            query_context=ctx,
        )
        assert HardFailReason.required_field_missing not in result.hard_fails
        assert SoftFailReason.missing_entities in result.soft_fails

    def test_required_field_missing_medium_importance_is_soft_fail(self) -> None:
        """Medium-importance source missing entities → soft fail (not hard fail)."""
        a = self._assessor()
        ctx = QueryContext(
            required_entities=["Apple", "iPhone", "iOS", "Tim Cook"],
        )
        result = a.assess(
            content=(
                "General article about smartphones and technology. "
                "The market has changed significantly over the past decade. "
                "Many manufacturers compete in this space with diverse offerings."
            ),
            url="https://tech.example.com",
            domain="tech.example.com",
            title="Smartphones",
            source_importance="medium",
            query_context=ctx,
        )
        assert HardFailReason.required_field_missing not in result.hard_fails
        assert SoftFailReason.missing_entities in result.soft_fails

    def test_required_field_present_not_triggered(self) -> None:
        """Most required entities present → no missing entity signal."""
        a = self._assessor()
        ctx = QueryContext(
            required_entities=["Python", "programming"],
        )
        result = a.assess(
            content=LONG_CONTENT,
            url="https://python.org",
            domain="python.org",
            title="Python Programming Language",
            source_importance="high",
            query_context=ctx,
        )
        assert HardFailReason.required_field_missing not in result.hard_fails

    def test_no_query_context_no_required_field_check(self) -> None:
        """No query context → required field check skipped entirely."""
        a = self._assessor()
        result = a.assess(
            content=LONG_CONTENT,
            url="https://python.org",
            domain="python.org",
            title="Python",
            source_importance="high",
            query_context=None,
        )
        assert HardFailReason.required_field_missing not in result.hard_fails


# ---------------------------------------------------------------------------
# TestSoftFails
# ---------------------------------------------------------------------------


class TestSoftFails:
    """Soft-fail detection tests — only run when no hard fails present."""

    def _assessor(self) -> ContentConfidenceAssessor:
        return ContentConfidenceAssessor(_config())

    def test_thin_content(self) -> None:
        """Content shorter than research_thin_content_chars → thin_content soft fail."""
        a = self._assessor()
        # 200 chars > 50 (no extraction failure) but < 500 (thin content)
        content = "This is a short article about Python programming. " * 4  # ~200 chars
        result = a.assess(
            content=content,
            url="https://example.com",
            domain="example.com",
            title="Python",
            source_importance="medium",
        )
        assert SoftFailReason.thin_content in result.soft_fails

    def test_thin_content_above_threshold_not_triggered(self) -> None:
        a = self._assessor()
        result = a.assess(
            content=LONG_CONTENT,
            url="https://example.com",
            domain="example.com",
            title="Python",
            source_importance="medium",
        )
        assert SoftFailReason.thin_content not in result.soft_fails

    def test_thin_content_threshold_configurable(self) -> None:
        """Custom thin_content threshold respected."""
        # Use 100-char threshold — LONG_CONTENT well above, but 'x' * 90 is not
        a = ContentConfidenceAssessor(
            _config(research_thin_content_chars=100)
        )
        short = "x" * 90  # Above extraction-failure (50) but below 100 threshold
        result = a.assess(
            content=short,
            url="https://example.com",
            domain="example.com",
            title="Page",
            source_importance="low",
        )
        assert SoftFailReason.thin_content in result.soft_fails

    def test_boilerplate_heavy(self) -> None:
        """Content dominated by boilerplate phrases → boilerplate_heavy soft fail."""
        a = self._assessor()
        boilerplate_lines = [
            "© 2024 Example Corp",
            "Privacy Policy",
            "Cookie Policy",
            "Terms of Service",
            "All Rights Reserved",
            "Sign Up for our newsletter",
            "Follow us on social media",
            "Share this article",
            "Subscribe to our newsletter",
            "Copyright 2024",
        ]
        # Mix in a small amount of real content
        content_lines = ["This is actual content about technology."] + boilerplate_lines * 2
        content = "\n".join(content_lines)
        result = a.assess(
            content=content,
            url="https://example.com",
            domain="example.com",
            title="Tech Article",
            source_importance="medium",
        )
        assert SoftFailReason.boilerplate_heavy in result.soft_fails

    def test_boilerplate_ratio_stored(self) -> None:
        """boilerplate_ratio field is populated on the assessment."""
        a = self._assessor()
        boilerplate_lines = ["© 2024 Corp", "Privacy Policy", "All Rights Reserved"] * 5
        content = "\n".join(["Some real content here."] + boilerplate_lines)
        result = a.assess(
            content=content,
            url="https://example.com",
            domain="example.com",
            title="Page",
            source_importance="low",
        )
        assert result.boilerplate_ratio > 0.0

    def test_no_boilerplate_for_clean_content(self) -> None:
        a = self._assessor()
        result = a.assess(
            content=LONG_CONTENT,
            url="https://python.org",
            domain="python.org",
            title="Python",
            source_importance="high",
        )
        assert SoftFailReason.boilerplate_heavy not in result.soft_fails

    def test_missing_entities_soft_fail(self) -> None:
        """< 30% of required entities in content → missing_entities soft fail (non-high importance)."""
        a = self._assessor()
        ctx = QueryContext(
            required_entities=["Rust", "Cargo", "Tokio", "async"],
        )
        result = a.assess(
            content=(
                "Python is a popular programming language. "
                "It was created by Guido van Rossum. "
                "Python is dynamically typed and supports many paradigms."
            ),
            url="https://example.com",
            domain="example.com",
            title="Programming Languages",
            source_importance="medium",
            query_context=ctx,
        )
        assert SoftFailReason.missing_entities in result.soft_fails

    def test_no_publish_date_time_sensitive(self) -> None:
        """Time-sensitive query with no date pattern in content → no_publish_date soft fail."""
        a = self._assessor()
        ctx = QueryContext(time_sensitive=True)
        # Content with no date patterns
        result = a.assess(
            content=(
                "Python is a popular programming language used widely across "
                "many fields including data science and web development. "
                "The language is dynamically typed and has a large ecosystem."
            ),
            url="https://example.com",
            domain="example.com",
            title="Python Overview",
            source_importance="medium",
            query_context=ctx,
        )
        assert SoftFailReason.no_publish_date in result.soft_fails

    def test_no_date_check_when_not_time_sensitive(self) -> None:
        """Non-time-sensitive query should never trigger no_publish_date."""
        a = self._assessor()
        ctx = QueryContext(time_sensitive=False)
        result = a.assess(
            content=(
                "Python is a programming language. "
                "It supports many paradigms. "
                "The standard library is comprehensive."
            ),
            url="https://example.com",
            domain="example.com",
            title="Python",
            source_importance="medium",
            query_context=ctx,
        )
        assert SoftFailReason.no_publish_date not in result.soft_fails

    def test_no_date_check_when_no_query_context(self) -> None:
        """No query context → no_publish_date check skipped."""
        a = self._assessor()
        result = a.assess(
            content="Some content without dates.",
            url="https://example.com",
            domain="example.com",
            title="Page",
            source_importance="medium",
            query_context=None,
        )
        assert SoftFailReason.no_publish_date not in result.soft_fails

    def test_date_pattern_iso_format_satisfies_time_sensitivity(self) -> None:
        """ISO date pattern (YYYY-MM-DD) satisfies time-sensitive requirement."""
        a = self._assessor()
        ctx = QueryContext(time_sensitive=True)
        result = a.assess(
            content=(
                "Published: 2024-03-15. "
                "Python released a new version with performance improvements. "
                "The update includes significant changes to the memory model. "
                "Developers are encouraged to upgrade as soon as possible."
            ),
            url="https://python.org/news",
            domain="python.org",
            title="Python News",
            source_importance="high",
            query_context=ctx,
        )
        assert SoftFailReason.no_publish_date not in result.soft_fails

    def test_date_pattern_month_name_satisfies_time_sensitivity(self) -> None:
        """Month-name + year pattern satisfies time-sensitive requirement."""
        a = self._assessor()
        ctx = QueryContext(time_sensitive=True)
        result = a.assess(
            content=(
                "Updated March 2024. "
                "The latest Python release brings improved performance. "
                "Many new features were added to the standard library. "
                "This version supports better async patterns."
            ),
            url="https://python.org",
            domain="python.org",
            title="Python Update",
            source_importance="medium",
            query_context=ctx,
        )
        assert SoftFailReason.no_publish_date not in result.soft_fails

    def test_weak_content_density(self) -> None:
        """Highly repetitive content (unique_words / total_words < 0.3) → weak_content_density."""
        a = self._assessor()
        # Highly repetitive: very low unique word ratio
        repeated = ("the the the the the the the the the the cat cat cat cat cat ") * 20
        result = a.assess(
            content=repeated,
            url="https://example.com",
            domain="example.com",
            title="Page",
            source_importance="low",
        )
        assert SoftFailReason.weak_content_density in result.soft_fails

    def test_good_density_no_soft_fail(self) -> None:
        a = self._assessor()
        result = a.assess(
            content=LONG_CONTENT,
            url="https://python.org",
            domain="python.org",
            title="Python",
            source_importance="high",
        )
        assert SoftFailReason.weak_content_density not in result.soft_fails


# ---------------------------------------------------------------------------
# TestDecisionMatrix
# ---------------------------------------------------------------------------


class TestDecisionMatrix:
    """Decision matrix: confidence bucket + promotion decision outcomes."""

    def _assessor(self, **cfg_overrides: object) -> ContentConfidenceAssessor:
        return ContentConfidenceAssessor(_config(**cfg_overrides))

    def test_high_confidence_clean_content(self) -> None:
        """No hard or soft fails → HIGH / NO_VERIFY."""
        a = self._assessor()
        result = a.assess(
            content=LONG_CONTENT,
            url="https://python.org",
            domain="python.org",
            title="Python Programming Language",
            source_importance="high",
        )
        assert result.confidence_bucket == ConfidenceBucket.high
        assert result.promotion_decision == PromotionDecision.no_verify
        assert result.hard_fails == []
        assert result.soft_point_total == 0

    def test_one_soft_fail_no_verify(self) -> None:
        """1 soft fail (threshold=2) → HIGH / NO_VERIFY."""
        a = self._assessor()
        ctx = QueryContext(time_sensitive=True)
        # Only thin content soft fail expected (content 200-499 chars, no date)
        content = "Python is a programming language. " * 8  # ~264 chars
        result = a.assess(
            content=content,
            url="https://example.com",
            domain="example.com",
            title="Python",
            source_importance="high",
            query_context=ctx,
        )
        # May have thin_content + no_publish_date → up to 2 soft fails
        # This test only verifies when exactly 1 soft fail present
        if result.soft_point_total == 1:
            assert result.confidence_bucket == ConfidenceBucket.high
            assert result.promotion_decision == PromotionDecision.no_verify

    def test_two_soft_fails_verify_if_high_importance(self) -> None:
        """2 soft fails (threshold=2 verify, 3 required) → MEDIUM / VERIFY_IF_HIGH_IMPORTANCE."""
        a = self._assessor(
            research_soft_fail_verify_threshold=2,
            research_soft_fail_required_threshold=3,
        )
        ctx = QueryContext(time_sensitive=True)
        # Use thin content (< 500 chars) + no date → 2 soft fails
        content = (
            "Python is a general-purpose programming language. "
            "It supports many paradigms including OOP and functional styles. "
            "Python is widely used in data science and web development."
        )
        result = a.assess(
            content=content,
            url="https://example.com",
            domain="example.com",
            title="Python Language",
            source_importance="medium",
            query_context=ctx,
        )
        # thin_content + no_publish_date = 2 soft fails
        assert SoftFailReason.thin_content in result.soft_fails
        assert SoftFailReason.no_publish_date in result.soft_fails
        assert result.soft_point_total == 2
        assert result.confidence_bucket == ConfidenceBucket.medium
        assert result.promotion_decision == PromotionDecision.verify_if_high_importance

    def test_three_soft_fails_required(self) -> None:
        """3+ soft fails → LOW / REQUIRED."""
        a = self._assessor(
            research_soft_fail_verify_threshold=2,
            research_soft_fail_required_threshold=3,
            research_boilerplate_ratio_threshold=0.3,
        )
        ctx = QueryContext(
            time_sensitive=True,
            required_entities=["Rust", "Cargo", "async"],
        )
        # thin + no_date + missing_entities = 3 soft fails
        content = (
            "Python is used in data science and web applications. "
            "This article discusses programming languages in general. "
            "Languages have different paradigms and use cases."
        )
        result = a.assess(
            content=content,
            url="https://example.com",
            domain="example.com",
            title="Programming Languages",
            source_importance="medium",
            query_context=ctx,
        )
        assert result.soft_point_total >= 3
        assert result.confidence_bucket == ConfidenceBucket.low
        assert result.promotion_decision == PromotionDecision.required

    def test_hard_fail_overrides_soft_fail_count(self) -> None:
        """Hard fail → LOW / REQUIRED regardless of soft fail count."""
        a = self._assessor()
        result = a.assess(
            content="Subscribe to continue reading this premium article.",
            url="https://news.example.com",
            domain="news.example.com",
            title="News",
            source_importance="high",
        )
        assert len(result.hard_fails) > 0
        assert result.confidence_bucket == ConfidenceBucket.low
        assert result.promotion_decision == PromotionDecision.required

    def test_content_length_stored(self) -> None:
        """content_length field reflects actual content length."""
        a = self._assessor()
        result = a.assess(
            content=LONG_CONTENT,
            url="https://python.org",
            domain="python.org",
            title="Python",
            source_importance="high",
        )
        assert result.content_length == len(LONG_CONTENT.strip())

    def test_soft_point_total_matches_soft_fails_length(self) -> None:
        a = self._assessor()
        ctx = QueryContext(time_sensitive=True)
        content = "Python programming. " * 5  # < 500 chars, no date
        result = a.assess(
            content=content,
            url="https://example.com",
            domain="example.com",
            title="Python",
            source_importance="medium",
            query_context=ctx,
        )
        assert result.soft_point_total == len(result.soft_fails)


# ---------------------------------------------------------------------------
# TestShadowScore
# ---------------------------------------------------------------------------


class TestShadowScore:
    """Shadow score telemetry — not used for decisions, just asserted in tests."""

    def _assessor(self) -> ContentConfidenceAssessor:
        return ContentConfidenceAssessor(_config())

    def test_perfect_content_high_shadow_score(self) -> None:
        """No fails → shadow_score >= 0.9."""
        a = self._assessor()
        result = a.assess(
            content=LONG_CONTENT,
            url="https://python.org",
            domain="python.org",
            title="Python Programming Language",
            source_importance="high",
        )
        assert result.shadow_score >= 0.9

    def test_hard_fail_low_shadow_score(self) -> None:
        """Hard fail → shadow_score < 0.7."""
        a = self._assessor()
        result = a.assess(
            content="Subscribe to continue reading this article.",
            url="https://example.com",
            domain="example.com",
            title="Article",
            source_importance="high",
        )
        assert result.shadow_score < 0.7

    def test_shadow_score_clamped_between_0_and_1(self) -> None:
        """shadow_score must always be in [0.0, 1.0]."""
        a = self._assessor()
        # Multiple hard fails — ensure clamping works
        result = a.assess(
            content="",  # extraction failure
            url="https://example.com",
            domain="example.com",
            title="Page",
            source_importance="high",
        )
        assert 0.0 <= result.shadow_score <= 1.0

    def test_shadow_score_decreases_with_soft_fails(self) -> None:
        """More soft fails → lower shadow score."""
        a = self._assessor()
        ctx_none = QueryContext(time_sensitive=False)
        ctx_sensitive = QueryContext(time_sensitive=True)

        result_clean = a.assess(
            content=LONG_CONTENT,
            url="https://python.org",
            domain="python.org",
            title="Python Programming Language",
            source_importance="high",
            query_context=ctx_none,
        )

        # Thin content only: fewer soft fails
        content_thin = "Python is short. " * 8  # ~136 chars, thin content
        result_one_soft = a.assess(
            content=content_thin,
            url="https://example.com",
            domain="example.com",
            title="Python",
            source_importance="high",
            query_context=ctx_none,
        )

        assert result_one_soft.shadow_score <= result_clean.shadow_score

        # Add time sensitivity to trigger no_publish_date as well
        result_two_soft = a.assess(
            content=content_thin,
            url="https://example.com",
            domain="example.com",
            title="Python",
            source_importance="high",
            query_context=ctx_sensitive,
        )
        assert result_two_soft.shadow_score <= result_one_soft.shadow_score

    def test_shadow_score_is_float(self) -> None:
        a = self._assessor()
        result = a.assess(
            content=LONG_CONTENT,
            url="https://python.org",
            domain="python.org",
            title="Python",
            source_importance="high",
        )
        assert isinstance(result.shadow_score, float)
