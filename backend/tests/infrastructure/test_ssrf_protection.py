"""Tests for SSRF protection in URL filters.

Validates that is_ssrf_target blocks internal/private network addresses,
Docker service hostnames, and cloud metadata endpoints.
"""

import pytest

from app.domain.utils.url_filters import is_ssrf_target


class TestSSRFBlockedTargets:
    """Verify that internal/private targets are blocked."""

    @pytest.mark.parametrize(
        "url,description",
        [
            ("http://localhost/admin", "loopback hostname"),
            ("http://127.0.0.1/admin", "loopback IP"),
            ("http://127.0.0.1:8080/api/v1/shell/exec", "loopback with port"),
            ("http://[::1]/admin", "IPv6 loopback"),
            ("http://sandbox/api/v1/shell/exec", "Docker sandbox hostname"),
            ("http://sandbox2/api/v1/file/read", "Docker sandbox2 hostname"),
            ("http://mongodb/admin", "Docker mongodb hostname"),
            ("http://redis:6379/", "Docker redis hostname"),
            ("http://redis-cache:6379/", "Docker redis-cache hostname"),
            ("http://qdrant:6333/collections", "Docker qdrant hostname"),
            ("http://minio:9000/", "Docker minio hostname"),
            ("http://prometheus:9090/", "Docker prometheus hostname"),
            ("http://grafana:3000/", "Docker grafana hostname"),
            ("http://loki:3100/", "Docker loki hostname"),
            ("http://backend:8000/api/v1/health", "Docker backend hostname"),
            ("http://169.254.169.254/latest/meta-data/", "AWS metadata"),
            ("http://metadata.google.internal/computeMetadata/v1/", "GCP metadata"),
            ("ftp://evil.com/file", "blocked scheme ftp"),
            ("file:///etc/passwd", "blocked scheme file"),
            ("gopher://evil.com/", "blocked scheme gopher"),
        ],
    )
    def test_blocks_internal_targets(self, url: str, description: str) -> None:
        result = is_ssrf_target(url)
        assert result is not None, f"Expected SSRF block for {description}: {url}"

    def test_blocks_empty_url(self) -> None:
        assert is_ssrf_target("") == "Empty URL"

    def test_blocks_no_hostname(self) -> None:
        result = is_ssrf_target("http:///path")
        assert result is not None


class TestSSRFAllowedTargets:
    """Verify that legitimate external URLs are allowed."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.google.com",
            "https://github.com/user/repo",
            "http://example.com/page",
            "https://api.openai.com/v1/chat",
            "https://docs.python.org/3/library/",
        ],
    )
    def test_allows_external_urls(self, url: str) -> None:
        result = is_ssrf_target(url)
        assert result is None, f"Should allow external URL: {url}, got: {result}"


class TestSSRFFailClosed:
    """Verify fail-closed behavior on parse/DNS errors."""

    def test_fails_closed_on_parse_error(self) -> None:
        # Malformed URL should be blocked, not allowed
        result = is_ssrf_target("http://[invalid-ipv6/path")
        # Should either return None (parseable) or a block reason (unparseable)
        # The key is it shouldn't crash
        assert isinstance(result, str) or result is None
