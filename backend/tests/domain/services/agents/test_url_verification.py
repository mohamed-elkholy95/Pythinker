"""Tests for URLVerificationService — hallucination prevention via URL checks."""

import pytest

from app.domain.models.url_verification import (
    BatchURLVerificationResult,
    URLVerificationResult,
    URLVerificationStatus,
)
from app.domain.services.agents.url_verification import (
    URLVerificationService,
    get_url_verification_service,
)

# ── URLVerificationResult model ─────────────────────────────────────


class TestURLVerificationResult:
    def test_verified_is_valid_citation(self):
        r = URLVerificationResult(url="https://a.com", status=URLVerificationStatus.VERIFIED)
        assert r.is_valid_citation is True

    def test_not_visited_is_suspicious(self):
        r = URLVerificationResult(url="https://a.com", status=URLVerificationStatus.EXISTS_NOT_VISITED)
        assert r.is_suspicious is True

    def test_not_found_is_suspicious(self):
        r = URLVerificationResult(url="https://a.com", status=URLVerificationStatus.NOT_FOUND)
        assert r.is_suspicious is True

    def test_placeholder_is_suspicious(self):
        r = URLVerificationResult(url="https://a.com", status=URLVerificationStatus.PLACEHOLDER)
        assert r.is_suspicious is True

    def test_error_is_not_suspicious(self):
        r = URLVerificationResult(url="https://a.com", status=URLVerificationStatus.ERROR)
        assert r.is_suspicious is False

    def test_warning_messages(self):
        cases = [
            (URLVerificationStatus.EXISTS_NOT_VISITED, "never visited"),
            (URLVerificationStatus.NOT_FOUND, "does not exist"),
            (URLVerificationStatus.PLACEHOLDER, "Placeholder"),
            (URLVerificationStatus.TIMEOUT, "timeout"),
            (URLVerificationStatus.ERROR, "failed"),
        ]
        for status, expected_fragment in cases:
            r = URLVerificationResult(url="https://a.com", status=status)
            msg = r.get_warning_message()
            assert msg is not None, f"Expected message for {status}"
            assert expected_fragment.lower() in msg.lower(), f"Expected '{expected_fragment}' in '{msg}'"

    def test_verified_no_warning(self):
        r = URLVerificationResult(url="https://a.com", status=URLVerificationStatus.VERIFIED)
        assert r.get_warning_message() is None


# ── BatchURLVerificationResult model ────────────────────────────────


class TestBatchURLVerificationResult:
    def test_empty_batch(self):
        batch = BatchURLVerificationResult()
        assert batch.all_valid is True  # vacuous truth
        assert batch.has_critical_issues is False
        assert batch.has_warnings is False
        assert batch.get_invalid_urls() == []
        assert batch.get_warnings() == []

    def test_all_valid_with_results(self):
        batch = BatchURLVerificationResult(
            results={
                "https://a.com": URLVerificationResult(url="https://a.com", status=URLVerificationStatus.VERIFIED),
            },
            verified_count=1,
        )
        assert batch.all_valid is True

    def test_has_critical_issues(self):
        batch = BatchURLVerificationResult(not_found_count=1)
        assert batch.has_critical_issues is True

    def test_has_placeholder_critical(self):
        batch = BatchURLVerificationResult(placeholder_count=1)
        assert batch.has_critical_issues is True

    def test_has_warnings_from_not_visited(self):
        batch = BatchURLVerificationResult(not_visited_count=1)
        assert batch.has_warnings is True

    def test_get_summary(self):
        batch = BatchURLVerificationResult(total_urls=3, verified_count=1, not_found_count=1, placeholder_count=1)
        summary = batch.get_summary()
        assert "Total: 3" in summary
        assert "Verified: 1" in summary


# ── Placeholder URL Detection ───────────────────────────────────────


class TestDetectPlaceholderUrl:
    svc = URLVerificationService()

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/page",
            "https://example.org/api",
            "https://example.net",
            "http://localhost:8080/test",
            "http://127.0.0.1:3000/api",
            "https://site.com/[URL]",
            "https://site.com/[link]",
            "https://placeholder.com/data",
            "https://your-domain.com/api",
            "https://yourdomain.com/api",
            "https://test.com/page",
            "https://fake.com/resource",
            "https://sample.com/doc",
            "https://xxx.com/page",
            "https://domain.com/path",
            "https://website.com/home",
            "https://url.com/redirect",
        ],
    )
    def test_detects_placeholder(self, url: str):
        assert self.svc.detect_placeholder_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://google.com/search",
            "https://python.org/docs",
            "https://github.com/user/repo",
            "https://docs.python.org/3/library",
            "https://stackoverflow.com/questions/123",
            "https://en.wikipedia.org/wiki/Python",
        ],
    )
    def test_does_not_flag_real_urls(self, url: str):
        assert self.svc.detect_placeholder_url(url) is False

    def test_suspicious_tld_invalid(self):
        assert self.svc.detect_placeholder_url("https://something.invalid") is True

    def test_suspicious_tld_test(self):
        assert self.svc.detect_placeholder_url("https://something.test") is True

    def test_suspicious_tld_example(self):
        assert self.svc.detect_placeholder_url("https://something.example") is True

    def test_suspicious_tld_localhost(self):
        assert self.svc.detect_placeholder_url("https://something.localhost") is True


# ── URL Format Validation ───────────────────────────────────────────


class TestIsValidUrlFormat:
    svc = URLVerificationService()

    def test_valid_http(self):
        assert self.svc.is_valid_url_format("http://example.com") is True

    def test_valid_https(self):
        assert self.svc.is_valid_url_format("https://google.com/search?q=test") is True

    def test_invalid_no_scheme(self):
        assert self.svc.is_valid_url_format("google.com") is False

    def test_invalid_ftp_scheme(self):
        assert self.svc.is_valid_url_format("ftp://files.example.com") is False

    def test_invalid_no_netloc(self):
        assert self.svc.is_valid_url_format("https://") is False

    def test_invalid_too_long(self):
        long_url = "https://example.com/" + "a" * 2048
        assert self.svc.is_valid_url_format(long_url) is False

    def test_empty_string(self):
        assert self.svc.is_valid_url_format("") is False


# ── URL Normalization ───────────────────────────────────────────────


class TestNormalizeUrl:
    svc = URLVerificationService()

    def test_removes_trailing_slash(self):
        normalized = self.svc._normalize_url("https://example.com/path/")
        assert normalized == "https://example.com/path"

    def test_lowercases_netloc(self):
        normalized = self.svc._normalize_url("https://EXAMPLE.COM/Path")
        assert normalized == "https://example.com/Path"

    def test_preserves_query(self):
        normalized = self.svc._normalize_url("https://example.com/search?q=test")
        assert "?q=test" in normalized

    def test_removes_fragment(self):
        normalized = self.svc._normalize_url("https://example.com/page#section")
        assert "#section" not in normalized

    def test_root_path_preserved(self):
        normalized = self.svc._normalize_url("https://example.com")
        assert normalized.endswith("/")

    def test_malformed_url_fallback(self):
        # urlparse handles most strings without raising, but test graceful handling
        normalized = self.svc._normalize_url("not a url at all")
        assert isinstance(normalized, str)


# ── Session URL Verification ────────────────────────────────────────


class TestVerifyUrlWasVisited:
    svc = URLVerificationService()

    def test_exact_match(self):
        session_urls = {"https://google.com/search"}
        assert self.svc.verify_url_was_visited("https://google.com/search", session_urls) is True

    def test_normalized_match(self):
        session_urls = {"https://google.com/search/"}
        # Normalized version removes trailing slash
        assert self.svc.verify_url_was_visited("https://google.com/search", session_urls) is True

    def test_case_insensitive_host(self):
        session_urls = {"https://Google.COM/path"}
        assert self.svc.verify_url_was_visited("https://google.com/path", session_urls) is True

    def test_not_visited(self):
        session_urls = {"https://google.com/search"}
        assert self.svc.verify_url_was_visited("https://other.com/page", session_urls) is False

    def test_empty_session_urls(self):
        assert self.svc.verify_url_was_visited("https://google.com", set()) is False

    def test_url_with_fragment_difference(self):
        session_urls = {"https://docs.python.org/3/library"}
        # The original URL has a fragment, session URL doesn't
        # After normalization both should match (fragments removed)
        assert self.svc.verify_url_was_visited("https://docs.python.org/3/library#section", session_urls) is True


# ── URL Extraction from Text ────────────────────────────────────────


class TestExtractUrlsFromText:
    svc = URLVerificationService()

    def test_extracts_single_url(self):
        text = "Visit https://google.com/search for more."
        urls = self.svc.extract_urls_from_text(text)
        assert "https://google.com/search" in urls

    def test_extracts_multiple_urls(self):
        text = "See https://a.com and http://b.com/page for details."
        urls = self.svc.extract_urls_from_text(text)
        assert len(urls) >= 2

    def test_deduplicates_urls(self):
        text = "https://a.com and again https://a.com"
        urls = self.svc.extract_urls_from_text(text)
        assert len(urls) == 1

    def test_strips_trailing_punctuation(self):
        text = "Check https://example.com/page."
        urls = self.svc.extract_urls_from_text(text)
        assert any(not u.endswith(".") for u in urls)

    def test_no_urls_in_text(self):
        text = "This is plain text without any URLs."
        urls = self.svc.extract_urls_from_text(text)
        assert urls == []

    def test_ignores_invalid_format(self):
        text = "Not a URL: ftp://files.example.com/data"
        urls = self.svc.extract_urls_from_text(text)
        assert len(urls) == 0


# ── Singleton ───────────────────────────────────────────────────────


class TestSingleton:
    def test_returns_instance(self):
        svc = get_url_verification_service()
        assert isinstance(svc, URLVerificationService)

    def test_is_stable(self):
        s1 = get_url_verification_service()
        s2 = get_url_verification_service()
        assert s1 is s2
