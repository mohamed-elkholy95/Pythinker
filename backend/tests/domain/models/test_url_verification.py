"""Tests for url_verification — URLVerificationStatus, URLVerificationResult, BatchURLVerificationResult.

Covers:
  - URLVerificationStatus enum
  - URLVerificationResult: is_valid_citation, is_suspicious, get_warning_message
  - BatchURLVerificationResult: all_valid, has_critical_issues, has_warnings,
    get_invalid_urls, get_warnings, get_summary
"""

from __future__ import annotations

from app.domain.models.url_verification import (
    BatchURLVerificationResult,
    URLVerificationResult,
    URLVerificationStatus,
)

# ---------------------------------------------------------------------------
# URLVerificationStatus
# ---------------------------------------------------------------------------


class TestURLVerificationStatus:
    """Enum members."""

    def test_all_members(self) -> None:
        expected = {"verified", "exists_not_visited", "not_found", "placeholder", "timeout", "error"}
        assert {s.value for s in URLVerificationStatus} == expected


# ---------------------------------------------------------------------------
# URLVerificationResult
# ---------------------------------------------------------------------------


class TestURLVerificationResult:
    """URLVerificationResult properties."""

    def test_is_valid_citation_verified(self) -> None:
        r = URLVerificationResult(url="https://example.com", status=URLVerificationStatus.VERIFIED)
        assert r.is_valid_citation is True

    def test_is_valid_citation_not_found(self) -> None:
        r = URLVerificationResult(url="https://example.com", status=URLVerificationStatus.NOT_FOUND)
        assert r.is_valid_citation is False

    def test_is_suspicious_placeholder(self) -> None:
        r = URLVerificationResult(url="https://fake.example", status=URLVerificationStatus.PLACEHOLDER)
        assert r.is_suspicious is True

    def test_is_suspicious_not_visited(self) -> None:
        r = URLVerificationResult(url="https://real.com", status=URLVerificationStatus.EXISTS_NOT_VISITED)
        assert r.is_suspicious is True

    def test_is_not_suspicious_verified(self) -> None:
        r = URLVerificationResult(url="https://good.com", status=URLVerificationStatus.VERIFIED)
        assert r.is_suspicious is False

    def test_warning_message_not_found(self) -> None:
        r = URLVerificationResult(url="https://x.com", status=URLVerificationStatus.NOT_FOUND, http_status=404)
        msg = r.get_warning_message()
        assert msg is not None
        assert "404" in msg

    def test_warning_message_placeholder(self) -> None:
        r = URLVerificationResult(url="https://fake.com", status=URLVerificationStatus.PLACEHOLDER)
        msg = r.get_warning_message()
        assert "Placeholder" in msg

    def test_warning_message_verified_none(self) -> None:
        r = URLVerificationResult(url="https://ok.com", status=URLVerificationStatus.VERIFIED)
        assert r.get_warning_message() is None

    def test_warning_message_error(self) -> None:
        r = URLVerificationResult(url="https://x.com", status=URLVerificationStatus.ERROR, error="DNS failed")
        msg = r.get_warning_message()
        assert "DNS failed" in msg

    def test_warning_message_timeout(self) -> None:
        r = URLVerificationResult(url="https://x.com", status=URLVerificationStatus.TIMEOUT)
        msg = r.get_warning_message()
        assert "timeout" in msg.lower()


# ---------------------------------------------------------------------------
# BatchURLVerificationResult
# ---------------------------------------------------------------------------


class TestBatchURLVerificationResult:
    """BatchURLVerificationResult aggregate properties."""

    def _verified(self, url: str) -> URLVerificationResult:
        return URLVerificationResult(url=url, status=URLVerificationStatus.VERIFIED)

    def _not_found(self, url: str) -> URLVerificationResult:
        return URLVerificationResult(url=url, status=URLVerificationStatus.NOT_FOUND, http_status=404)

    def _placeholder(self, url: str) -> URLVerificationResult:
        return URLVerificationResult(url=url, status=URLVerificationStatus.PLACEHOLDER)

    def test_all_valid_true(self) -> None:
        batch = BatchURLVerificationResult(
            results={"a": self._verified("a"), "b": self._verified("b")},
            total_urls=2,
            verified_count=2,
        )
        assert batch.all_valid is True

    def test_all_valid_false(self) -> None:
        batch = BatchURLVerificationResult(
            results={"a": self._verified("a"), "b": self._not_found("b")},
            total_urls=2,
            verified_count=1,
            not_found_count=1,
        )
        assert batch.all_valid is False

    def test_has_critical_issues_not_found(self) -> None:
        batch = BatchURLVerificationResult(not_found_count=1)
        assert batch.has_critical_issues is True

    def test_has_critical_issues_placeholder(self) -> None:
        batch = BatchURLVerificationResult(placeholder_count=1)
        assert batch.has_critical_issues is True

    def test_has_critical_issues_none(self) -> None:
        batch = BatchURLVerificationResult()
        assert batch.has_critical_issues is False

    def test_has_warnings(self) -> None:
        batch = BatchURLVerificationResult(not_visited_count=2)
        assert batch.has_warnings is True

    def test_has_no_warnings(self) -> None:
        batch = BatchURLVerificationResult()
        assert batch.has_warnings is False

    def test_get_invalid_urls(self) -> None:
        batch = BatchURLVerificationResult(
            results={
                "https://good.com": self._verified("https://good.com"),
                "https://bad.com": self._not_found("https://bad.com"),
                "https://fake.com": self._placeholder("https://fake.com"),
            },
        )
        invalid = batch.get_invalid_urls()
        assert "https://bad.com" in invalid
        assert "https://fake.com" in invalid
        assert "https://good.com" not in invalid

    def test_get_warnings(self) -> None:
        batch = BatchURLVerificationResult(
            results={
                "https://good.com": self._verified("https://good.com"),
                "https://bad.com": self._not_found("https://bad.com"),
            },
        )
        warnings = batch.get_warnings()
        assert len(warnings) == 1
        assert "bad.com" in warnings[0]

    def test_get_summary(self) -> None:
        batch = BatchURLVerificationResult(
            total_urls=5,
            verified_count=3,
            not_visited_count=1,
            not_found_count=1,
        )
        summary = batch.get_summary()
        assert "Total: 5" in summary
        assert "Verified: 3" in summary
        assert "Not Found: 1" in summary
