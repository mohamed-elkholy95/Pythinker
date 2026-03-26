"""Tests for URL verification domain models."""

from app.domain.models.url_verification import (
    BatchURLVerificationResult,
    URLVerificationResult,
    URLVerificationStatus,
)


class TestURLVerificationStatus:
    def test_values(self) -> None:
        expected = {"verified", "exists_not_visited", "not_found", "placeholder", "timeout", "error"}
        assert {s.value for s in URLVerificationStatus} == expected


class TestURLVerificationResult:
    def test_verified_is_valid(self) -> None:
        r = URLVerificationResult(
            url="https://example.com",
            status=URLVerificationStatus.VERIFIED,
            exists=True,
            was_visited=True,
        )
        assert r.is_valid_citation is True
        assert r.is_suspicious is False
        assert r.get_warning_message() is None

    def test_not_visited_is_suspicious(self) -> None:
        r = URLVerificationResult(
            url="https://example.com",
            status=URLVerificationStatus.EXISTS_NOT_VISITED,
            exists=True,
        )
        assert r.is_valid_citation is False
        assert r.is_suspicious is True
        msg = r.get_warning_message()
        assert msg is not None
        assert "never visited" in msg

    def test_not_found_warning(self) -> None:
        r = URLVerificationResult(
            url="https://fake.com/page",
            status=URLVerificationStatus.NOT_FOUND,
            http_status=404,
        )
        assert r.is_suspicious is True
        msg = r.get_warning_message()
        assert "does not exist" in msg
        assert "404" in msg

    def test_placeholder_warning(self) -> None:
        r = URLVerificationResult(
            url="https://example.com/[URL]",
            status=URLVerificationStatus.PLACEHOLDER,
        )
        msg = r.get_warning_message()
        assert "Placeholder" in msg

    def test_timeout_warning(self) -> None:
        r = URLVerificationResult(
            url="https://slow.com",
            status=URLVerificationStatus.TIMEOUT,
        )
        msg = r.get_warning_message()
        assert "timeout" in msg

    def test_error_warning(self) -> None:
        r = URLVerificationResult(
            url="https://broken.com",
            status=URLVerificationStatus.ERROR,
            error="DNS failed",
        )
        msg = r.get_warning_message()
        assert "DNS failed" in msg

    def test_verification_time(self) -> None:
        r = URLVerificationResult(
            url="https://example.com",
            status=URLVerificationStatus.VERIFIED,
            verification_time_ms=150.5,
        )
        assert r.verification_time_ms == 150.5


class TestBatchURLVerificationResult:
    def _make_batch(self) -> BatchURLVerificationResult:
        results = {
            "https://a.com": URLVerificationResult(
                url="https://a.com", status=URLVerificationStatus.VERIFIED, exists=True, was_visited=True
            ),
            "https://b.com": URLVerificationResult(
                url="https://b.com", status=URLVerificationStatus.NOT_FOUND, http_status=404
            ),
            "https://c.com": URLVerificationResult(url="https://c.com", status=URLVerificationStatus.PLACEHOLDER),
        }
        return BatchURLVerificationResult(
            results=results,
            total_urls=3,
            verified_count=1,
            not_found_count=1,
            placeholder_count=1,
        )

    def test_all_valid_false(self) -> None:
        batch = self._make_batch()
        assert batch.all_valid is False

    def test_all_valid_true(self) -> None:
        results = {
            "https://a.com": URLVerificationResult(url="https://a.com", status=URLVerificationStatus.VERIFIED),
        }
        batch = BatchURLVerificationResult(results=results, total_urls=1, verified_count=1)
        assert batch.all_valid is True

    def test_has_critical_issues(self) -> None:
        batch = self._make_batch()
        assert batch.has_critical_issues is True

    def test_no_critical_issues(self) -> None:
        batch = BatchURLVerificationResult()
        assert batch.has_critical_issues is False

    def test_has_warnings(self) -> None:
        results = {
            "https://x.com": URLVerificationResult(
                url="https://x.com", status=URLVerificationStatus.EXISTS_NOT_VISITED
            ),
        }
        batch = BatchURLVerificationResult(results=results, not_visited_count=1)
        assert batch.has_warnings is True

    def test_get_invalid_urls(self) -> None:
        batch = self._make_batch()
        invalid = batch.get_invalid_urls()
        assert "https://b.com" in invalid  # lgtm[py/incomplete-url-scheme-check]
        assert "https://c.com" in invalid  # lgtm[py/incomplete-url-scheme-check]
        assert "https://a.com" not in invalid

    def test_get_warnings(self) -> None:
        batch = self._make_batch()
        warnings = batch.get_warnings()
        assert len(warnings) == 2  # not_found + placeholder

    def test_get_summary(self) -> None:
        batch = self._make_batch()
        summary = batch.get_summary()
        assert "Total: 3" in summary
        assert "Verified: 1" in summary
        assert "Not Found: 1" in summary
        assert "Placeholder: 1" in summary

    def test_empty_batch(self) -> None:
        batch = BatchURLVerificationResult()
        assert batch.all_valid is True
        assert batch.has_critical_issues is False
        assert batch.get_invalid_urls() == []
        assert batch.get_warnings() == []
