"""Tests for URLVerificationService and URL verification models.

Covers:
- URLVerificationResult model properties and warning messages
- BatchURLVerificationResult model aggregation and summary
- URLVerificationService.detect_placeholder_url (14 regex patterns + suspicious TLDs)
- URLVerificationService.is_valid_url_format
- URLVerificationService._normalize_url
- URLVerificationService.verify_url_was_visited
- URLVerificationService.extract_urls_from_text
- URLVerificationService.verify_url_exists (async, httpx-mocked)
- URLVerificationService.verify_url (async, httpx-mocked)
- URLVerificationService.batch_verify (async, httpx-mocked)
- get_url_verification_service singleton

Run with: pytest tests/domain/services/agents/test_url_verification.py -v
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import httpx
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

# ── Helpers ─────────────────────────────────────────────────────────


def _make_result(status: URLVerificationStatus, **kwargs) -> URLVerificationResult:
    """Build a URLVerificationResult with sensible defaults."""
    return URLVerificationResult(url="https://example.com", status=status, **kwargs)


def _make_mock_response(
    status_code: int = 200,
    history: list | None = None,
    final_url: str = "https://example.com",
) -> MagicMock:
    """Build a mock httpx Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.history = history if history is not None else []
    resp.url = httpx.URL(final_url)
    return resp


def _same_url(actual: str, expected: str) -> bool:
    actual_parsed = urlparse(actual)
    expected_parsed = urlparse(expected)
    return (
        actual_parsed.scheme,
        actual_parsed.netloc,
        actual_parsed.path,
        actual_parsed.query,
    ) == (
        expected_parsed.scheme,
        expected_parsed.netloc,
        expected_parsed.path,
        expected_parsed.query,
    )


def _collection_has_url(values: list[str] | set[str], expected: str) -> bool:
    return any(_same_url(value, expected) for value in values)


def _text_has_url(text: str, expected: str) -> bool:
    return _collection_has_url(
        [token.strip("()[]<>,.;!?") for token in text.split()],
        expected,
    )


# ── URLVerificationStatus enum ───────────────────────────────────────


class TestURLVerificationStatus:
    def test_all_members_present(self):
        members = {s.value for s in URLVerificationStatus}
        assert members == {"verified", "exists_not_visited", "not_found", "placeholder", "timeout", "error"}

    def test_is_str_subclass(self):
        assert isinstance(URLVerificationStatus.VERIFIED, str)
        assert URLVerificationStatus.VERIFIED == "verified"


# ── URLVerificationResult model ─────────────────────────────────────


class TestURLVerificationResultProperties:
    def test_verified_is_valid_citation(self):
        r = _make_result(URLVerificationStatus.VERIFIED, exists=True, was_visited=True)
        assert r.is_valid_citation is True

    def test_exists_not_visited_is_not_valid_citation(self):
        r = _make_result(URLVerificationStatus.EXISTS_NOT_VISITED, exists=True)
        assert r.is_valid_citation is False

    def test_not_found_is_not_valid_citation(self):
        r = _make_result(URLVerificationStatus.NOT_FOUND)
        assert r.is_valid_citation is False

    def test_placeholder_is_not_valid_citation(self):
        r = _make_result(URLVerificationStatus.PLACEHOLDER)
        assert r.is_valid_citation is False

    def test_timeout_is_not_valid_citation(self):
        r = _make_result(URLVerificationStatus.TIMEOUT)
        assert r.is_valid_citation is False

    def test_error_is_not_valid_citation(self):
        r = _make_result(URLVerificationStatus.ERROR)
        assert r.is_valid_citation is False

    def test_placeholder_is_suspicious(self):
        r = _make_result(URLVerificationStatus.PLACEHOLDER)
        assert r.is_suspicious is True

    def test_exists_not_visited_is_suspicious(self):
        r = _make_result(URLVerificationStatus.EXISTS_NOT_VISITED)
        assert r.is_suspicious is True

    def test_not_found_is_suspicious(self):
        r = _make_result(URLVerificationStatus.NOT_FOUND)
        assert r.is_suspicious is True

    def test_verified_is_not_suspicious(self):
        r = _make_result(URLVerificationStatus.VERIFIED)
        assert r.is_suspicious is False

    def test_timeout_is_not_suspicious(self):
        r = _make_result(URLVerificationStatus.TIMEOUT)
        assert r.is_suspicious is False

    def test_error_is_not_suspicious(self):
        r = _make_result(URLVerificationStatus.ERROR)
        assert r.is_suspicious is False

    def test_default_exists_is_false(self):
        r = URLVerificationResult(url="https://a.com", status=URLVerificationStatus.PLACEHOLDER)
        assert r.exists is False

    def test_default_was_visited_is_false(self):
        r = URLVerificationResult(url="https://a.com", status=URLVerificationStatus.VERIFIED)
        assert r.was_visited is False

    def test_http_status_stored(self):
        r = _make_result(URLVerificationStatus.NOT_FOUND, http_status=404)
        assert r.http_status == 404

    def test_redirect_url_stored(self):
        r = _make_result(URLVerificationStatus.VERIFIED, redirect_url="https://redirect.com")
        assert r.redirect_url == "https://redirect.com"

    def test_error_message_stored(self):
        r = _make_result(URLVerificationStatus.ERROR, error="Connection refused")
        assert r.error == "Connection refused"

    def test_verified_at_is_utc_datetime(self):
        r = _make_result(URLVerificationStatus.VERIFIED)
        assert isinstance(r.verified_at, datetime)
        assert r.verified_at.tzinfo is not None

    def test_verification_time_ms_default(self):
        r = _make_result(URLVerificationStatus.VERIFIED)
        assert r.verification_time_ms == 0.0


class TestURLVerificationResultWarningMessages:
    def test_verified_returns_none(self):
        r = _make_result(URLVerificationStatus.VERIFIED)
        assert r.get_warning_message() is None

    def test_exists_not_visited_mentions_session(self):
        r = URLVerificationResult(
            url="https://real.com/page",
            status=URLVerificationStatus.EXISTS_NOT_VISITED,
        )
        msg = r.get_warning_message()
        assert msg is not None
        assert "never visited" in msg.lower()
        assert "https://real.com/page" in msg

    def test_not_found_mentions_http_status(self):
        r = URLVerificationResult(
            url="https://gone.com",
            status=URLVerificationStatus.NOT_FOUND,
            http_status=404,
        )
        msg = r.get_warning_message()
        assert msg is not None
        assert "does not exist" in msg.lower()
        assert "404" in msg

    def test_placeholder_mentions_url(self):
        r = URLVerificationResult(
            url="https://example.com/fake",
            status=URLVerificationStatus.PLACEHOLDER,
        )
        msg = r.get_warning_message()
        assert msg is not None
        assert "placeholder" in msg.lower() or "fake" in msg.lower()
        assert "https://example.com/fake" in msg

    def test_timeout_mentions_timeout(self):
        r = URLVerificationResult(
            url="https://slow.com",
            status=URLVerificationStatus.TIMEOUT,
        )
        msg = r.get_warning_message()
        assert msg is not None
        assert "timeout" in msg.lower()

    def test_error_includes_error_detail(self):
        r = URLVerificationResult(
            url="https://broken.com",
            status=URLVerificationStatus.ERROR,
            error="SSL certificate error",
        )
        msg = r.get_warning_message()
        assert msg is not None
        assert "failed" in msg.lower()
        assert _text_has_url(msg, "https://broken.com")

    def test_not_found_with_none_http_status(self):
        """get_warning_message should not crash when http_status is None."""
        r = URLVerificationResult(
            url="https://unreachable.com",
            status=URLVerificationStatus.NOT_FOUND,
            http_status=None,
        )
        msg = r.get_warning_message()
        assert msg is not None
        assert _text_has_url(msg, "https://unreachable.com")


# ── BatchURLVerificationResult model ────────────────────────────────


class TestBatchURLVerificationResultEmpty:
    def test_all_valid_on_empty_batch(self):
        """Vacuous truth: no results means all_valid is True."""
        batch = BatchURLVerificationResult()
        assert batch.all_valid is True

    def test_no_critical_issues_on_empty(self):
        batch = BatchURLVerificationResult()
        assert batch.has_critical_issues is False

    def test_no_warnings_on_empty(self):
        batch = BatchURLVerificationResult()
        assert batch.has_warnings is False

    def test_get_invalid_urls_empty(self):
        batch = BatchURLVerificationResult()
        assert batch.get_invalid_urls() == []

    def test_get_warnings_empty(self):
        batch = BatchURLVerificationResult()
        assert batch.get_warnings() == []

    def test_summary_shows_zeros(self):
        batch = BatchURLVerificationResult()
        summary = batch.get_summary()
        assert "Total: 0" in summary
        assert "Verified: 0" in summary


class TestBatchURLVerificationResultAllValid:
    def test_single_verified_url(self):
        batch = BatchURLVerificationResult(
            results={
                "https://a.com": URLVerificationResult(url="https://a.com", status=URLVerificationStatus.VERIFIED)
            },
            total_urls=1,
            verified_count=1,
        )
        assert batch.all_valid is True
        assert batch.has_critical_issues is False
        assert batch.get_invalid_urls() == []

    def test_multiple_verified_urls(self):
        batch = BatchURLVerificationResult(
            results={
                "https://a.com": URLVerificationResult(url="https://a.com", status=URLVerificationStatus.VERIFIED),
                "https://b.com": URLVerificationResult(url="https://b.com", status=URLVerificationStatus.VERIFIED),
            },
            total_urls=2,
            verified_count=2,
        )
        assert batch.all_valid is True


class TestBatchURLVerificationResultCriticalIssues:
    def test_not_found_triggers_critical(self):
        batch = BatchURLVerificationResult(not_found_count=1)
        assert batch.has_critical_issues is True

    def test_placeholder_triggers_critical(self):
        batch = BatchURLVerificationResult(placeholder_count=2)
        assert batch.has_critical_issues is True

    def test_both_counts_trigger_critical(self):
        batch = BatchURLVerificationResult(not_found_count=1, placeholder_count=1)
        assert batch.has_critical_issues is True

    def test_only_not_visited_no_critical(self):
        batch = BatchURLVerificationResult(not_visited_count=3)
        assert batch.has_critical_issues is False

    def test_only_errors_no_critical(self):
        batch = BatchURLVerificationResult(error_count=5)
        assert batch.has_critical_issues is False


class TestBatchURLVerificationResultWarnings:
    def test_not_visited_triggers_warning(self):
        batch = BatchURLVerificationResult(not_visited_count=1)
        assert batch.has_warnings is True

    def test_zero_not_visited_no_warning(self):
        batch = BatchURLVerificationResult(not_visited_count=0)
        assert batch.has_warnings is False


class TestBatchURLVerificationResultGetInvalidUrls:
    def test_returns_non_verified_urls(self):
        batch = BatchURLVerificationResult(
            results={
                "https://ok.com": URLVerificationResult(url="https://ok.com", status=URLVerificationStatus.VERIFIED),
                "https://bad.com": URLVerificationResult(url="https://bad.com", status=URLVerificationStatus.NOT_FOUND),
                "https://fake.com": URLVerificationResult(
                    url="https://fake.com", status=URLVerificationStatus.PLACEHOLDER
                ),
            }
        )
        invalid = batch.get_invalid_urls()
        assert not _collection_has_url(invalid, "https://ok.com")
        assert _collection_has_url(invalid, "https://bad.com")
        assert _collection_has_url(invalid, "https://fake.com")
        assert len(invalid) == 2

    def test_all_verified_returns_empty(self):
        batch = BatchURLVerificationResult(
            results={
                "https://a.com": URLVerificationResult(url="https://a.com", status=URLVerificationStatus.VERIFIED),
            }
        )
        assert batch.get_invalid_urls() == []


class TestBatchURLVerificationResultGetWarnings:
    def test_collects_warning_messages(self):
        batch = BatchURLVerificationResult(
            results={
                "https://ok.com": URLVerificationResult(url="https://ok.com", status=URLVerificationStatus.VERIFIED),
                "https://gone.com": URLVerificationResult(
                    url="https://gone.com", status=URLVerificationStatus.NOT_FOUND, http_status=404
                ),
                "https://fake.com": URLVerificationResult(
                    url="https://fake.com", status=URLVerificationStatus.PLACEHOLDER
                ),
            }
        )
        warnings = batch.get_warnings()
        assert len(warnings) == 2
        combined = " ".join(warnings)
        assert _text_has_url(combined, "https://gone.com")
        assert _text_has_url(combined, "https://fake.com")
        assert not _text_has_url(combined, "https://ok.com")

    def test_no_warnings_when_all_verified(self):
        batch = BatchURLVerificationResult(
            results={
                "https://a.com": URLVerificationResult(url="https://a.com", status=URLVerificationStatus.VERIFIED),
            }
        )
        assert batch.get_warnings() == []


class TestBatchURLVerificationResultGetSummary:
    def test_summary_contains_all_fields(self):
        batch = BatchURLVerificationResult(
            total_urls=10,
            verified_count=5,
            not_visited_count=2,
            not_found_count=1,
            placeholder_count=1,
            error_count=1,
        )
        summary = batch.get_summary()
        assert "Total: 10" in summary
        assert "Verified: 5" in summary
        assert "Not Visited: 2" in summary
        assert "Not Found: 1" in summary
        assert "Placeholder: 1" in summary
        assert "Errors: 1" in summary

    def test_summary_is_multiline(self):
        batch = BatchURLVerificationResult(total_urls=3, verified_count=3)
        lines = batch.get_summary().splitlines()
        assert len(lines) >= 2

    def test_summary_header_present(self):
        batch = BatchURLVerificationResult()
        assert "URL Verification Summary" in batch.get_summary()


# ── URLVerificationService — placeholder detection ───────────────────


class TestDetectPlaceholderUrlPatterns:
    svc = URLVerificationService()

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/page",
            "https://example.org/api",
            "https://example.net/resource",
            "http://example.com",
        ],
    )
    def test_example_tld_variants(self, url: str):
        assert self.svc.detect_placeholder_url(url) is True

    def test_localhost_plain(self):
        assert self.svc.detect_placeholder_url("http://localhost") is True

    def test_localhost_with_port(self):
        assert self.svc.detect_placeholder_url("http://localhost:8080/api") is True

    def test_loopback_ip(self):
        assert self.svc.detect_placeholder_url("http://127.0.0.1/health") is True

    def test_bracket_url_uppercase(self):
        assert self.svc.detect_placeholder_url("https://site.com/[URL]") is True

    def test_bracket_url_lowercase(self):
        assert self.svc.detect_placeholder_url("https://site.com/[url]") is True

    def test_bracket_link(self):
        assert self.svc.detect_placeholder_url("https://site.com/[link]") is True

    def test_placeholder_word_in_domain(self):
        assert self.svc.detect_placeholder_url("https://placeholder.io/data") is True

    def test_placeholder_word_in_path(self):
        assert self.svc.detect_placeholder_url("https://real.com/placeholder/resource") is True

    def test_your_domain_hyphenated(self):
        assert self.svc.detect_placeholder_url("https://your-domain.com/api") is True

    def test_yourdomain_no_hyphen(self):
        assert self.svc.detect_placeholder_url("https://yourdomain.com/api") is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://test.com",
            "https://test.org/page",
            "https://test.net/resource",
        ],
    )
    def test_test_tld_variants(self, url: str):
        assert self.svc.detect_placeholder_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://fake.com",
            "https://fake.org/endpoint",
            "https://fake.net",
        ],
    )
    def test_fake_tld_variants(self, url: str):
        assert self.svc.detect_placeholder_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://sample.com",
            "https://sample.org/docs",
            "https://sample.net",
        ],
    )
    def test_sample_tld_variants(self, url: str):
        assert self.svc.detect_placeholder_url(url) is True

    def test_xxx_repeated_chars(self):
        assert self.svc.detect_placeholder_url("https://xxx.com") is True

    def test_xxxx_repeated_chars(self):
        assert self.svc.detect_placeholder_url("https://xxxx.org") is True

    def test_domain_dot_com_generic(self):
        assert self.svc.detect_placeholder_url("https://domain.com/path") is True

    def test_website_dot_com_generic(self):
        assert self.svc.detect_placeholder_url("https://website.com/home") is True

    def test_url_dot_com_generic(self):
        assert self.svc.detect_placeholder_url("https://url.com/redirect") is True

    def test_suspicious_tld_invalid(self):
        assert self.svc.detect_placeholder_url("https://mysite.invalid/page") is True

    def test_suspicious_tld_test(self):
        assert self.svc.detect_placeholder_url("https://myapp.test/health") is True

    def test_suspicious_tld_example(self):
        assert self.svc.detect_placeholder_url("https://corp.example") is True

    def test_suspicious_tld_localhost(self):
        assert self.svc.detect_placeholder_url("https://service.localhost") is True

    def test_case_insensitive_example(self):
        assert self.svc.detect_placeholder_url("https://EXAMPLE.COM/page") is True

    def test_case_insensitive_localhost(self):
        assert self.svc.detect_placeholder_url("http://LOCALHOST:3000") is True


class TestDetectPlaceholderUrlRealUrls:
    svc = URLVerificationService()

    @pytest.mark.parametrize(
        "url",
        [
            "https://google.com/search?q=python",
            "https://python.org/docs/3/library/asyncio.html",
            "https://github.com/python/cpython",
            "https://docs.python.org/3/",
            "https://stackoverflow.com/questions/12345",
            "https://en.wikipedia.org/wiki/Python_(programming_language)",
            "https://pypi.org/project/httpx/",
            "https://fastapi.tiangolo.com/tutorial/",
            "https://pydantic-docs.helpmanual.io/",
            "https://www.reuters.com/article/some-news",
        ],
    )
    def test_real_urls_not_flagged(self, url: str):
        assert self.svc.detect_placeholder_url(url) is False

    def test_testify_substring_not_flagged(self):
        """'testify' contains 'test' but should not match 'test.com' pattern."""
        assert self.svc.detect_placeholder_url("https://testify.com/docs") is False

    def test_domain_in_path_not_flagged(self):
        """'domain' appears in path component, not hostname."""
        assert self.svc.detect_placeholder_url("https://realsite.com/domain/settings") is False


# ── URLVerificationService — format validation ───────────────────────


class TestIsValidUrlFormat:
    svc = URLVerificationService()

    def test_http_scheme_accepted(self):
        assert self.svc.is_valid_url_format("http://google.com") is True

    def test_https_scheme_accepted(self):
        assert self.svc.is_valid_url_format("https://google.com") is True

    def test_with_path_and_query(self):
        assert self.svc.is_valid_url_format("https://search.example.org/q?term=foo&limit=10") is True

    def test_with_port_number(self):
        assert self.svc.is_valid_url_format("http://api.example.com:8080/health") is True

    def test_ftp_scheme_rejected(self):
        assert self.svc.is_valid_url_format("ftp://files.example.com/data") is False

    def test_file_scheme_rejected(self):
        assert self.svc.is_valid_url_format("file:///etc/passwd") is False

    def test_no_scheme_rejected(self):
        assert self.svc.is_valid_url_format("google.com/search") is False

    def test_empty_string_rejected(self):
        assert self.svc.is_valid_url_format("") is False

    def test_scheme_only_rejected(self):
        assert self.svc.is_valid_url_format("https://") is False

    def test_url_at_2047_chars_accepted(self):
        path = "a" * (2047 - len("https://x.com/"))
        url = f"https://x.com/{path}"
        assert len(url) < 2048
        assert self.svc.is_valid_url_format(url) is True

    def test_url_at_2048_chars_rejected(self):
        path = "a" * (2048 - len("https://x.com/"))
        url = f"https://x.com/{path}"
        assert len(url) == 2048
        assert self.svc.is_valid_url_format(url) is False

    def test_url_exceeding_2048_rejected(self):
        url = "https://example.com/" + "x" * 2048
        assert self.svc.is_valid_url_format(url) is False

    def test_ip_address_host_accepted(self):
        assert self.svc.is_valid_url_format("https://192.168.1.1/api") is True


# ── URLVerificationService — normalization ───────────────────────────


class TestNormalizeUrl:
    svc = URLVerificationService()

    def test_removes_trailing_slash_from_path(self):
        result = self.svc._normalize_url("https://example.com/path/to/resource/")
        assert not result.endswith("/path/to/resource/")
        assert result.endswith("/path/to/resource")

    def test_lowercases_hostname(self):
        result = self.svc._normalize_url("https://GITHUB.COM/User/Repo")
        parsed = urlparse(result)
        assert parsed.netloc == "github.com"
        assert parsed.path == "/User/Repo"

    def test_preserves_path_case(self):
        """Path is case-sensitive and must not be lowercased."""
        result = self.svc._normalize_url("https://example.com/MyPath")
        assert "/MyPath" in result

    def test_removes_fragment(self):
        result = self.svc._normalize_url("https://docs.python.org/3/library#section")
        assert "#section" not in result
        assert "#" not in result

    def test_preserves_query_string(self):
        result = self.svc._normalize_url("https://search.com/q?term=python&page=2")
        assert "?term=python&page=2" in result

    def test_root_path_becomes_slash(self):
        """A URL with no path should normalize to '/'."""
        result = self.svc._normalize_url("https://example.com")
        assert result.endswith("/")

    def test_multiple_trailing_slashes_removed(self):
        result = self.svc._normalize_url("https://example.com/path///")
        assert not result.endswith("/path///")

    def test_malformed_url_returns_string(self):
        result = self.svc._normalize_url("not a url at all")
        assert isinstance(result, str)

    def test_empty_string_returns_string(self):
        result = self.svc._normalize_url("")
        assert isinstance(result, str)

    def test_no_modification_already_normalized(self):
        url = "https://python.org/docs/3/library"
        result = self.svc._normalize_url(url)
        assert result == url

    def test_scheme_and_netloc_present_in_result(self):
        result = self.svc._normalize_url("https://EXAMPLE.COM/path")
        assert urlparse(result).scheme == "https"
        assert urlparse(result).netloc == "example.com"


# ── URLVerificationService — visit verification ──────────────────────


class TestVerifyUrlWasVisited:
    svc = URLVerificationService()

    def test_exact_match_in_session(self):
        session_urls = {"https://google.com/search", "https://python.org"}
        assert self.svc.verify_url_was_visited("https://google.com/search", session_urls) is True

    def test_not_in_session_returns_false(self):
        session_urls = {"https://google.com/search"}
        assert self.svc.verify_url_was_visited("https://other.com/page", session_urls) is False

    def test_empty_session_urls_returns_false(self):
        assert self.svc.verify_url_was_visited("https://google.com", set()) is False

    def test_trailing_slash_normalized_match(self):
        """URL with trailing slash matches session URL without trailing slash."""
        session_urls = {"https://python.org/docs"}
        assert self.svc.verify_url_was_visited("https://python.org/docs/", session_urls) is True

    def test_missing_trailing_slash_normalized_match(self):
        """URL without trailing slash matches session URL with trailing slash."""
        session_urls = {"https://python.org/docs/"}
        assert self.svc.verify_url_was_visited("https://python.org/docs", session_urls) is True

    def test_case_insensitive_host_match(self):
        session_urls = {"https://GITHUB.COM/user/repo"}
        assert self.svc.verify_url_was_visited("https://github.com/user/repo", session_urls) is True

    def test_fragment_difference_still_matches(self):
        """Fragment (#section) should be stripped; URL still matches."""
        session_urls = {"https://docs.python.org/3/library/asyncio"}
        assert (
            self.svc.verify_url_was_visited("https://docs.python.org/3/library/asyncio#coroutines", session_urls)
            is True
        )

    def test_query_string_difference_not_matched(self):
        """Different query strings should not match."""
        session_urls = {"https://search.com/q?term=python"}
        assert self.svc.verify_url_was_visited("https://search.com/q?term=java", session_urls) is False

    def test_normalized_direct_match_via_session_url(self):
        """Normalize session URL and check against target."""
        session_urls = {"https://EXAMPLE.ORG/path/"}
        assert self.svc.verify_url_was_visited("https://example.org/path", session_urls) is True

    def test_multiple_session_urls_finds_match(self):
        session_urls = {"https://a.com/page1", "https://b.com/page2", "https://c.com/page3"}
        assert self.svc.verify_url_was_visited("https://b.com/page2", session_urls) is True

    def test_multiple_session_urls_no_match(self):
        session_urls = {"https://a.com/page1", "https://b.com/page2"}
        assert self.svc.verify_url_was_visited("https://c.com/page3", session_urls) is False


# ── URLVerificationService — URL extraction ──────────────────────────


class TestExtractUrlsFromText:
    svc = URLVerificationService()

    def test_extracts_https_url(self):
        text = "Learn more at https://python.org/library."
        urls = self.svc.extract_urls_from_text(text)
        assert _collection_has_url(urls, "https://python.org/library")

    def test_extracts_http_url(self):
        text = "Visit http://httpbin.org/get for testing."
        urls = self.svc.extract_urls_from_text(text)
        assert _collection_has_url(urls, "http://httpbin.org/get")

    def test_extracts_multiple_urls(self):
        text = "Sources: https://python.org and https://github.com/python."
        urls = self.svc.extract_urls_from_text(text)
        assert len(urls) >= 2

    def test_deduplicates_identical_urls(self):
        text = "See https://python.org/docs and again https://python.org/docs."
        urls = self.svc.extract_urls_from_text(text)
        assert urls.count("https://python.org/docs") <= 1

    def test_strips_trailing_period(self):
        text = "See https://python.org/docs."
        urls = self.svc.extract_urls_from_text(text)
        assert not any(u.endswith(".") for u in urls)

    def test_strips_trailing_comma(self):
        text = "Visit https://python.org/docs, then check Github."
        urls = self.svc.extract_urls_from_text(text)
        assert not any(u.endswith(",") for u in urls)

    def test_strips_trailing_semicolon(self):
        text = "Reference: https://python.org/docs;"
        urls = self.svc.extract_urls_from_text(text)
        assert not any(u.endswith(";") for u in urls)

    def test_strips_trailing_exclamation(self):
        text = "Go to https://python.org/docs!"
        urls = self.svc.extract_urls_from_text(text)
        assert not any(u.endswith("!") for u in urls)

    def test_strips_trailing_question_mark(self):
        text = "Did you see https://python.org/docs?"
        urls = self.svc.extract_urls_from_text(text)
        assert not any(u.endswith("?") for u in urls)

    def test_no_urls_returns_empty_list(self):
        text = "This text contains no URLs at all."
        urls = self.svc.extract_urls_from_text(text)
        assert urls == []

    def test_empty_text_returns_empty_list(self):
        urls = self.svc.extract_urls_from_text("")
        assert urls == []

    def test_ftp_url_excluded(self):
        """ftp:// URLs fail is_valid_url_format and should be excluded."""
        text = "Download from ftp://files.example.com/data.zip"
        urls = self.svc.extract_urls_from_text(text)
        assert len(urls) == 0

    def test_url_in_markdown_link(self):
        text = "Check [Python](https://python.org/docs) for reference."
        urls = self.svc.extract_urls_from_text(text)
        assert _collection_has_url(urls, "https://python.org/docs")

    def test_url_with_query_string_extracted(self):
        text = "Search at https://google.com/search?q=python+asyncio"
        urls = self.svc.extract_urls_from_text(text)
        assert any("google.com/search" in u for u in urls)

    def test_returns_list_type(self):
        urls = self.svc.extract_urls_from_text("See https://python.org")
        assert isinstance(urls, list)


# ── URLVerificationService — async verify_url_exists ─────────────────


class TestVerifyUrlExistsAsync:
    svc = URLVerificationService(timeout=5.0)

    async def test_placeholder_url_returns_placeholder_status(self):
        result = await self.svc.verify_url_exists("https://example.com/page")
        assert result.status == URLVerificationStatus.PLACEHOLDER
        assert result.exists is False

    async def test_invalid_format_returns_error_status(self):
        result = await self.svc.verify_url_exists("not-a-url")
        assert result.status == URLVerificationStatus.ERROR
        assert result.error is not None

    async def test_successful_head_request_marks_exists(self):
        mock_resp = _make_mock_response(status_code=200)

        with patch("httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.head = AsyncMock(return_value=mock_resp)
            mock_client.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await self.svc.verify_url_exists("https://python.org")

        assert result.exists is True
        assert result.http_status == 200

    async def test_404_response_marks_not_found(self):
        mock_resp = _make_mock_response(status_code=404)

        with patch("httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.head = AsyncMock(return_value=mock_resp)
            mock_client.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await self.svc.verify_url_exists("https://python.org/missing")

        assert result.exists is False
        assert result.status == URLVerificationStatus.NOT_FOUND
        assert result.http_status == 404

    async def test_405_head_falls_back_to_get(self):
        head_resp = _make_mock_response(status_code=405)
        get_resp = _make_mock_response(status_code=200)

        with patch("httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.head = AsyncMock(return_value=head_resp)
            instance.get = AsyncMock(return_value=get_resp)
            mock_client.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await self.svc.verify_url_exists("https://api.python.org/status")

        instance.get.assert_awaited_once()
        assert result.exists is True

    async def test_redirect_url_captured(self):
        final_url = "https://redirect-target.com/final"
        mock_resp = _make_mock_response(
            status_code=200,
            history=[MagicMock()],  # non-empty history means redirect occurred
            final_url=final_url,
        )

        with patch("httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.head = AsyncMock(return_value=mock_resp)
            mock_client.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await self.svc.verify_url_exists("https://short.url/abc")

        assert result.redirect_url == final_url

    async def test_timeout_exception_returns_timeout_status(self):
        with patch("httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.head = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            mock_client.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await self.svc.verify_url_exists("https://slow.python.org/page")

        assert result.status == URLVerificationStatus.TIMEOUT
        assert result.exists is False
        assert "timed out" in (result.error or "").lower()

    async def test_connect_error_returns_not_found_status(self):
        with patch("httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.head = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
            mock_client.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await self.svc.verify_url_exists("https://unreachable.python.org/api")

        assert result.status == URLVerificationStatus.NOT_FOUND
        assert result.exists is False

    async def test_generic_exception_returns_error_status(self):
        with patch("httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.head = AsyncMock(side_effect=RuntimeError("unexpected error"))
            mock_client.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await self.svc.verify_url_exists("https://python.org")

        assert result.status == URLVerificationStatus.ERROR
        assert result.exists is False
        assert result.error is not None

    async def test_verification_time_ms_is_positive(self):
        mock_resp = _make_mock_response(status_code=200)

        with patch("httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.head = AsyncMock(return_value=mock_resp)
            mock_client.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await self.svc.verify_url_exists("https://python.org")

        assert result.verification_time_ms >= 0.0

    async def test_500_response_marks_not_found(self):
        mock_resp = _make_mock_response(status_code=500)

        with patch("httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.head = AsyncMock(return_value=mock_resp)
            mock_client.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await self.svc.verify_url_exists("https://broken.org")

        assert result.exists is False
        assert result.http_status == 500


# ── URLVerificationService — async verify_url ─────────────────────────


class TestVerifyUrlAsync:
    svc = URLVerificationService()

    async def test_placeholder_skips_http_request(self):
        """Placeholder detection should short-circuit before any HTTP call."""
        with patch.object(self.svc, "verify_url_exists") as mock_exists:
            result = await self.svc.verify_url("https://example.com/page")

        mock_exists.assert_not_called()
        assert result.status == URLVerificationStatus.PLACEHOLDER

    async def test_visited_url_skips_http_request(self):
        """If URL was visited, no HTTP request should be made."""
        session_urls = {"https://python.org/docs"}

        with patch.object(self.svc, "verify_url_exists") as mock_exists:
            result = await self.svc.verify_url("https://python.org/docs", session_urls=session_urls)

        mock_exists.assert_not_called()
        assert result.status == URLVerificationStatus.VERIFIED
        assert result.was_visited is True
        assert result.exists is True

    async def test_not_visited_url_makes_http_request(self):
        """URL not in session should trigger HTTP verification."""
        session_urls = {"https://other.com"}
        mock_http_result = URLVerificationResult(
            url="https://python.org",
            status=URLVerificationStatus.EXISTS_NOT_VISITED,
            exists=True,
            was_visited=False,
        )

        with patch.object(self.svc, "verify_url_exists", return_value=mock_http_result) as mock_exists:
            result = await self.svc.verify_url("https://python.org", session_urls=session_urls)

        mock_exists.assert_awaited_once()
        assert result.status == URLVerificationStatus.EXISTS_NOT_VISITED
        assert result.was_visited is False

    async def test_no_session_urls_makes_http_request(self):
        """When session_urls is None, HTTP verification proceeds."""
        mock_http_result = URLVerificationResult(
            url="https://python.org",
            status=URLVerificationStatus.EXISTS_NOT_VISITED,
            exists=True,
            was_visited=False,
        )

        with patch.object(self.svc, "verify_url_exists", return_value=mock_http_result) as mock_exists:
            result = await self.svc.verify_url("https://python.org", session_urls=None)

        mock_exists.assert_awaited_once()
        assert result.exists is True

    async def test_exists_and_not_visited_status_set(self):
        """Existing but unvisited URL gets EXISTS_NOT_VISITED status."""
        session_urls = {"https://different.com"}
        mock_http_result = URLVerificationResult(
            url="https://python.org",
            status=URLVerificationStatus.EXISTS_NOT_VISITED,
            exists=True,
            was_visited=False,
            http_status=200,
        )

        with patch.object(self.svc, "verify_url_exists", return_value=mock_http_result):
            result = await self.svc.verify_url("https://python.org", session_urls=session_urls)

        assert result.status == URLVerificationStatus.EXISTS_NOT_VISITED
        assert result.was_visited is False


# ── URLVerificationService — async batch_verify ───────────────────────


class TestBatchVerifyAsync:
    svc = URLVerificationService()

    async def test_empty_list_returns_empty_batch(self):
        result = await self.svc.batch_verify([])
        assert isinstance(result, BatchURLVerificationResult)
        assert result.total_urls == 0
        assert result.results == {}

    async def test_deduplicates_urls_before_verification(self):
        """Duplicate URLs should only be verified once."""
        verified_result = URLVerificationResult(
            url="https://python.org",
            status=URLVerificationStatus.VERIFIED,
            exists=True,
            was_visited=True,
        )

        call_count = 0

        async def mock_verify_url(url: str, session_urls=None) -> URLVerificationResult:
            nonlocal call_count
            call_count += 1
            return verified_result

        with patch.object(self.svc, "verify_url", side_effect=mock_verify_url):
            await self.svc.batch_verify(["https://python.org", "https://python.org", "https://python.org"])

        assert call_count == 1

    async def test_verified_urls_increment_verified_count(self):
        verified = URLVerificationResult(
            url="https://python.org", status=URLVerificationStatus.VERIFIED, exists=True, was_visited=True
        )

        with patch.object(self.svc, "verify_url", return_value=verified):
            result = await self.svc.batch_verify(["https://python.org"])

        assert result.verified_count == 1

    async def test_not_visited_urls_increment_not_visited_count(self):
        not_visited = URLVerificationResult(
            url="https://python.org", status=URLVerificationStatus.EXISTS_NOT_VISITED, exists=True
        )

        with patch.object(self.svc, "verify_url", return_value=not_visited):
            result = await self.svc.batch_verify(["https://python.org"])

        assert result.not_visited_count == 1

    async def test_not_found_urls_increment_not_found_count(self):
        not_found = URLVerificationResult(url="https://gone.com", status=URLVerificationStatus.NOT_FOUND)

        with patch.object(self.svc, "verify_url", return_value=not_found):
            result = await self.svc.batch_verify(["https://gone.com"])

        assert result.not_found_count == 1

    async def test_placeholder_urls_increment_placeholder_count(self):
        placeholder = URLVerificationResult(url="https://example.com", status=URLVerificationStatus.PLACEHOLDER)

        with patch.object(self.svc, "verify_url", return_value=placeholder):
            result = await self.svc.batch_verify(["https://example.com"])

        assert result.placeholder_count == 1

    async def test_error_and_timeout_increment_error_count(self):
        error_result = URLVerificationResult(url="https://broken.com", status=URLVerificationStatus.ERROR)
        timeout_result = URLVerificationResult(url="https://slow.com", status=URLVerificationStatus.TIMEOUT)

        call_index = 0
        results_list = [error_result, timeout_result]

        async def mock_verify(url: str, session_urls=None) -> URLVerificationResult:
            nonlocal call_index
            r = results_list[call_index % len(results_list)]
            call_index += 1
            return r

        with patch.object(self.svc, "verify_url", side_effect=mock_verify):
            result = await self.svc.batch_verify(["https://broken.com", "https://slow.com"])

        assert result.error_count == 2

    async def test_mixed_results_counted_correctly(self):
        results_map = {
            "https://verified.com": URLVerificationResult(
                url="https://verified.com", status=URLVerificationStatus.VERIFIED
            ),
            "https://not-visited.com": URLVerificationResult(
                url="https://not-visited.com", status=URLVerificationStatus.EXISTS_NOT_VISITED
            ),
            "https://gone.com": URLVerificationResult(url="https://gone.com", status=URLVerificationStatus.NOT_FOUND),
            "https://example.com": URLVerificationResult(
                url="https://example.com", status=URLVerificationStatus.PLACEHOLDER
            ),
        }

        async def mock_verify(url: str, session_urls=None) -> URLVerificationResult:
            return results_map[url]

        with patch.object(self.svc, "verify_url", side_effect=mock_verify):
            result = await self.svc.batch_verify(list(results_map.keys()))

        assert result.verified_count == 1
        assert result.not_visited_count == 1
        assert result.not_found_count == 1
        assert result.placeholder_count == 1

    async def test_verification_time_ms_recorded(self):
        verified = URLVerificationResult(url="https://a.com", status=URLVerificationStatus.VERIFIED)

        with patch.object(self.svc, "verify_url", return_value=verified):
            result = await self.svc.batch_verify(["https://a.com"])

        assert result.verification_time_ms >= 0.0

    async def test_session_urls_passed_to_verify(self):
        session_urls = {"https://python.org"}
        verified = URLVerificationResult(url="https://python.org", status=URLVerificationStatus.VERIFIED)

        with patch.object(self.svc, "verify_url", return_value=verified) as mock_verify:
            await self.svc.batch_verify(["https://python.org"], session_urls=session_urls)

        call_kwargs = mock_verify.call_args
        assert call_kwargs.kwargs.get("session_urls") == session_urls or (
            len(call_kwargs.args) > 1 and call_kwargs.args[1] == session_urls
        )

    async def test_respects_max_concurrent_parameter(self):
        """Verify the semaphore limits concurrency (no errors with small limit)."""
        urls = [f"https://site{i}.com" for i in range(20)]
        verified = URLVerificationResult(url="https://a.com", status=URLVerificationStatus.VERIFIED)

        with patch.object(self.svc, "verify_url", return_value=verified):
            result = await self.svc.batch_verify(urls, max_concurrent=3)

        # All unique URLs processed despite low concurrency limit
        assert result.verified_count == 20


# ── URLVerificationService — constructor ─────────────────────────────


class TestURLVerificationServiceConstructor:
    def test_default_timeout(self):
        svc = URLVerificationService()
        assert svc._timeout == 10.0

    def test_custom_timeout(self):
        svc = URLVerificationService(timeout=30.0)
        assert svc._timeout == 30.0

    def test_default_max_redirects(self):
        svc = URLVerificationService()
        assert svc._max_redirects == 5

    def test_custom_max_redirects(self):
        svc = URLVerificationService(max_redirects=3)
        assert svc._max_redirects == 3

    def test_default_verify_ssl(self):
        svc = URLVerificationService()
        assert svc._verify_ssl is True

    def test_custom_verify_ssl_false(self):
        svc = URLVerificationService(verify_ssl=False)
        assert svc._verify_ssl is False

    def test_placeholder_patterns_are_compiled(self):
        import re

        svc = URLVerificationService()
        assert all(isinstance(p, re.Pattern) for p in svc.PLACEHOLDER_PATTERNS)

    def test_placeholder_patterns_count(self):
        svc = URLVerificationService()
        assert len(svc.PLACEHOLDER_PATTERNS) == 14

    def test_suspicious_tlds_is_set(self):
        svc = URLVerificationService()
        assert isinstance(svc.SUSPICIOUS_TLDS, set)
        assert ".invalid" in svc.SUSPICIOUS_TLDS
        assert ".test" in svc.SUSPICIOUS_TLDS
        assert ".example" in svc.SUSPICIOUS_TLDS
        assert ".localhost" in svc.SUSPICIOUS_TLDS


# ── get_url_verification_service singleton ────────────────────────────


class TestGetUrlVerificationServiceSingleton:
    def test_returns_url_verification_service_instance(self):
        svc = get_url_verification_service()
        assert isinstance(svc, URLVerificationService)

    def test_returns_same_instance_on_repeated_calls(self):
        s1 = get_url_verification_service()
        s2 = get_url_verification_service()
        assert s1 is s2

    def test_singleton_persists_across_multiple_accesses(self):
        instances = [get_url_verification_service() for _ in range(5)]
        assert all(i is instances[0] for i in instances)

    def test_singleton_is_module_level_variable(self):
        """After first call, module-level variable should be set."""
        import app.domain.services.agents.url_verification as mod

        get_url_verification_service()
        assert mod._url_verification_service is not None
        assert isinstance(mod._url_verification_service, URLVerificationService)
