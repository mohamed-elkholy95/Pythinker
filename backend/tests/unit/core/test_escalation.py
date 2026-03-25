"""Tests for scraper escalation decision logic."""

import pytest

from app.infrastructure.external.scraper.escalation import (
    ESCALATION_STATUS_CODES,
    has_http2_transport_error,
    should_escalate,
)
from app.domain.external.scraper import ScrapedContent


@pytest.mark.unit
class TestEscalationStatusCodes:
    """Tests for ESCALATION_STATUS_CODES constant."""

    def test_contains_403(self) -> None:
        assert 403 in ESCALATION_STATUS_CODES

    def test_contains_429(self) -> None:
        assert 429 in ESCALATION_STATUS_CODES

    def test_contains_503(self) -> None:
        assert 503 in ESCALATION_STATUS_CODES

    def test_is_frozenset(self) -> None:
        assert isinstance(ESCALATION_STATUS_CODES, frozenset)


@pytest.mark.unit
class TestHasHttp2TransportError:
    """Tests for has_http2_transport_error function."""

    def test_none_error(self) -> None:
        assert has_http2_transport_error(None) is False

    def test_empty_error(self) -> None:
        assert has_http2_transport_error("") is False

    def test_curl_92_error(self) -> None:
        assert has_http2_transport_error("curl: (92) something failed") is True

    def test_nghttp2_error(self) -> None:
        assert has_http2_transport_error("NGHTTP2_INTERNAL_ERROR in stream") is True

    def test_http2_stream_error(self) -> None:
        assert has_http2_transport_error("HTTP/2 stream error occurred") is True

    def test_h2_stream_error(self) -> None:
        assert has_http2_transport_error("h2 stream reset") is True

    def test_not_closed_cleanly(self) -> None:
        assert has_http2_transport_error("connection was not closed cleanly") is True

    def test_err_http2(self) -> None:
        assert has_http2_transport_error("ERR_HTTP2 protocol error") is True

    def test_unrelated_error(self) -> None:
        assert has_http2_transport_error("DNS resolution failed") is False

    def test_case_insensitive(self) -> None:
        assert has_http2_transport_error("CURL: (92) big fail") is True


@pytest.mark.unit
class TestShouldEscalate:
    """Tests for should_escalate function."""

    def _make_content(self, **kwargs) -> ScrapedContent:
        defaults = {
            "success": True,
            "url": "https://example.com",
            "text": "A" * 600,
            "status_code": 200,
        }
        defaults.update(kwargs)
        return ScrapedContent(**defaults)

    def test_failed_result_escalates(self) -> None:
        result = self._make_content(success=False)
        assert should_escalate(result) is True

    def test_short_content_escalates(self) -> None:
        result = self._make_content(text="short")
        assert should_escalate(result) is True

    def test_custom_min_length(self) -> None:
        result = self._make_content(text="A" * 100)
        assert should_escalate(result, min_content_length=50) is False
        assert should_escalate(result, min_content_length=200) is True

    def test_403_status_escalates(self) -> None:
        result = self._make_content(status_code=403)
        assert should_escalate(result) is True

    def test_429_status_escalates(self) -> None:
        result = self._make_content(status_code=429)
        assert should_escalate(result) is True

    def test_503_status_escalates(self) -> None:
        result = self._make_content(status_code=503)
        assert should_escalate(result) is True

    def test_200_with_good_content_no_escalation(self) -> None:
        result = self._make_content()
        assert should_escalate(result) is False

    def test_cloudflare_challenge_escalates(self) -> None:
        result = self._make_content(text="A" * 600 + " Just a moment... Checking your browser")
        assert should_escalate(result) is True

    def test_access_denied_escalates(self) -> None:
        result = self._make_content(text="A" * 600 + " Access Denied - you are blocked")
        assert should_escalate(result) is True

    def test_ddos_guard_escalates(self) -> None:
        result = self._make_content(text="A" * 600 + " ddos-guard protection active")
        assert should_escalate(result) is True

    def test_enable_javascript_escalates(self) -> None:
        result = self._make_content(text="A" * 600 + " Please enable javascript to continue")
        assert should_escalate(result) is True

    def test_normal_page_no_escalation(self) -> None:
        result = self._make_content(text="This is a normal web page with sufficient content " * 20)
        assert should_escalate(result) is False
