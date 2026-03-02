"""Unit tests for UrlFailureGuard 3-tier escalation."""

from app.domain.services.agents.url_failure_guard import (
    UrlFailureGuard,
    normalize_url,
)


class TestUrlNormalization:
    """URL normalization catches near-duplicates."""

    def test_strips_trailing_slash(self):
        assert normalize_url("https://example.com/path/") == "https://example.com/path"

    def test_lowercases_scheme_and_host(self):
        assert normalize_url("HTTPS://Example.COM/Path") == "https://example.com/Path"

    def test_sorts_query_parameters(self):
        assert normalize_url("https://example.com?b=2&a=1") == "https://example.com?a=1&b=2"

    def test_removes_fragments(self):
        assert normalize_url("https://example.com/page#section") == "https://example.com/page"

    def test_preserves_path_case(self):
        """Path is case-sensitive per RFC 3986."""
        assert normalize_url("https://example.com/Vue/Guide") == "https://example.com/Vue/Guide"

    def test_empty_url_returns_empty(self):
        assert normalize_url("") == ""

    def test_url_without_scheme(self):
        """URLs without scheme are returned as-is (normalized lowercase)."""
        result = normalize_url("example.com/path/")
        assert result == "example.com/path"


class TestTierEscalation:
    """3-tier escalation: allow → warn → block."""

    def setup_method(self):
        self.guard = UrlFailureGuard(max_failures_per_url=3)

    def test_tier1_first_attempt_allows(self):
        decision = self.guard.check_url("https://example.com/missing")
        assert decision.action == "allow"
        assert decision.tier == 1
        assert decision.message is None

    def test_tier2_second_attempt_warns(self):
        self.guard.record_failure("https://example.com/missing", "HTTP 404 Not Found", "browser_get_content")
        decision = self.guard.check_url("https://example.com/missing")
        assert decision.action == "warn"
        assert decision.tier == 2
        assert "already tried" in decision.message.lower() or "already failed" in decision.message.lower()

    def test_tier3_third_attempt_blocks(self):
        url = "https://example.com/missing"
        self.guard.record_failure(url, "HTTP 404 Not Found", "browser_get_content")
        self.guard.record_failure(url, "HTTP 404 Not Found", "browser_get_content")
        decision = self.guard.check_url(url)
        assert decision.action == "block"
        assert decision.tier == 3
        assert "BLOCKED" in decision.message

    def test_tier3_blocks_after_max_failures(self):
        url = "https://vuejs.org/guide/best-practices/"
        for _ in range(3):
            self.guard.record_failure(url, "HTTP 404", "browser_get_content")
        decision = self.guard.check_url(url)
        assert decision.action == "block"
        assert decision.tier == 3

    def test_different_urls_independent(self):
        """Failures on one URL don't affect another."""
        self.guard.record_failure("https://a.com/404", "404", "browser")
        self.guard.record_failure("https://a.com/404", "404", "browser")
        decision_a = self.guard.check_url("https://a.com/404")
        decision_b = self.guard.check_url("https://b.com/page")
        assert decision_a.action == "block"
        assert decision_b.action == "allow"


class TestAlternativeUrls:
    """Search result URLs suggested as alternatives."""

    def setup_method(self):
        self.guard = UrlFailureGuard()

    def test_alternatives_from_search_results(self):
        self.guard.record_search_results(
            [
                "https://vuejs.org/guide/introduction.html",
                "https://coreui.io/vue/docs/",
            ]
        )
        self.guard.record_failure("https://vuejs.org/guide/best-practices/", "404", "browser")
        decision = self.guard.check_url("https://vuejs.org/guide/best-practices/")
        assert decision.action == "warn"
        assert len(decision.alternative_urls) > 0
        assert "https://vuejs.org/guide/introduction.html" in decision.alternative_urls

    def test_failed_urls_excluded_from_alternatives(self):
        """URLs that have failed should not be suggested as alternatives."""
        self.guard.record_search_results(
            [
                "https://a.com/good",
                "https://b.com/also-bad",
            ]
        )
        self.guard.record_failure("https://b.com/also-bad", "404", "browser")
        self.guard.record_failure("https://example.com/bad", "404", "browser")
        decision = self.guard.check_url("https://example.com/bad")
        assert "https://a.com/good" in decision.alternative_urls
        assert "https://b.com/also-bad" not in decision.alternative_urls

    def test_alternatives_capped_at_five(self):
        urls = [f"https://example.com/page{i}" for i in range(10)]
        self.guard.record_search_results(urls)
        self.guard.record_failure("https://bad.com/404", "404", "browser")
        decision = self.guard.check_url("https://bad.com/404")
        assert len(decision.alternative_urls) <= 5


class TestUrlNormalizationInGuard:
    """Guard normalizes URLs before tracking."""

    def setup_method(self):
        self.guard = UrlFailureGuard()

    def test_trailing_slash_treated_as_same(self):
        self.guard.record_failure("https://example.com/path/", "404", "browser")
        decision = self.guard.check_url("https://example.com/path")
        assert decision.action == "warn"
        assert decision.tier == 2

    def test_case_insensitive_host(self):
        self.guard.record_failure("https://EXAMPLE.COM/path", "404", "browser")
        decision = self.guard.check_url("https://example.com/path")
        assert decision.action == "warn"


class TestMetrics:
    """Guard exposes metrics for Prometheus."""

    def test_metrics_initial(self):
        guard = UrlFailureGuard()
        metrics = guard.get_metrics()
        assert metrics["tracked_urls"] == 0
        assert metrics["total_failures"] == 0
        assert metrics["tier2_escalations"] == 0
        assert metrics["tier3_escalations"] == 0

    def test_metrics_after_escalation(self):
        guard = UrlFailureGuard()
        guard.record_failure("https://a.com/404", "404", "browser")
        guard.record_failure("https://a.com/404", "404", "browser")
        metrics = guard.get_metrics()
        assert metrics["tracked_urls"] == 1
        assert metrics["total_failures"] == 2

    def test_get_failed_urls_summary(self):
        guard = UrlFailureGuard()
        assert guard.get_failed_urls_summary() is None
        guard.record_failure("https://a.com/bad", "404", "browser")
        summary = guard.get_failed_urls_summary()
        assert "a.com/bad" in summary
        assert "404" in summary
