"""Tests for domain URL filter utilities."""

from urllib.parse import urlparse

import pytest

from app.domain.utils.url_filters import (
    VIDEO_DOMAINS,
    VIDEO_EXTENSIONS,
    filter_video_urls,
    is_ssrf_target,
    is_video_url,
)


@pytest.mark.unit
class TestIsVideoUrl:
    """Tests for is_video_url function."""

    def test_empty_url(self) -> None:
        assert is_video_url("") is False

    def test_youtube_url(self) -> None:
        assert is_video_url("https://www.youtube.com/watch?v=abc123") is True

    def test_youtube_short_url(self) -> None:
        assert is_video_url("https://youtu.be/abc123") is True

    def test_vimeo_url(self) -> None:
        assert is_video_url("https://vimeo.com/12345") is True

    def test_netflix_url(self) -> None:
        assert is_video_url("https://www.netflix.com/title/12345") is True

    def test_twitch_url(self) -> None:
        assert is_video_url("https://www.twitch.tv/streamer") is True

    def test_tiktok_url(self) -> None:
        assert is_video_url("https://www.tiktok.com/@user/video/123") is True

    def test_mp4_extension(self) -> None:
        assert is_video_url("https://example.com/video.mp4") is True

    def test_webm_extension(self) -> None:
        assert is_video_url("https://cdn.example.com/clip.webm") is True

    def test_m3u8_extension(self) -> None:
        assert is_video_url("https://stream.example.com/live.m3u8") is True

    def test_watch_pattern(self) -> None:
        assert is_video_url("https://example.com/watch?v=abc") is True

    def test_embed_pattern(self) -> None:
        assert is_video_url("https://example.com/embed/12345") is True

    def test_normal_webpage(self) -> None:
        assert is_video_url("https://example.com/article") is False

    def test_github_url(self) -> None:
        assert is_video_url("https://github.com/user/repo") is False

    def test_documentation_url(self) -> None:
        assert is_video_url("https://docs.python.org/3/library/json.html") is False

    def test_scheme_less_youtube(self) -> None:
        assert is_video_url("youtube.com/watch?v=abc") is True

    def test_bilibili_url(self) -> None:
        assert is_video_url("https://www.bilibili.com/video/BV123") is True


@pytest.mark.unit
class TestFilterVideoUrls:
    """Tests for filter_video_urls function."""

    def test_filters_video_urls(self) -> None:
        urls = [
            "https://example.com/article",
            "https://www.youtube.com/watch?v=abc",
            "https://docs.python.org",
            "https://vimeo.com/123",
        ]
        filtered = filter_video_urls(urls)
        assert len(filtered) == 2
        assert any(urlparse(url).netloc == "example.com" for url in filtered)
        assert any(urlparse(url).netloc == "docs.python.org" for url in filtered)

    def test_empty_list(self) -> None:
        assert filter_video_urls([]) == []

    def test_no_video_urls(self) -> None:
        urls = ["https://example.com", "https://docs.python.org"]
        assert filter_video_urls(urls) == urls


@pytest.mark.unit
class TestIsSsrfTarget:
    """Tests for is_ssrf_target function."""

    def test_empty_url(self) -> None:
        result = is_ssrf_target("")
        assert result is not None  # Should be blocked

    def test_localhost_blocked(self) -> None:
        result = is_ssrf_target("http://localhost:8000/api")
        assert result is not None
        assert "internal" in result.lower() or "blocked" in result.lower()

    def test_internal_hostname_backend(self) -> None:
        result = is_ssrf_target("http://backend:8000/api")
        assert result is not None

    def test_internal_hostname_mongodb(self) -> None:
        result = is_ssrf_target("http://mongodb:27017")
        assert result is not None

    def test_internal_hostname_redis(self) -> None:
        result = is_ssrf_target("http://redis:6379")
        assert result is not None

    def test_cloud_metadata_ip(self) -> None:
        result = is_ssrf_target("http://169.254.169.254/latest/meta-data/")
        assert result is not None

    def test_blocked_scheme_ftp(self) -> None:
        result = is_ssrf_target("ftp://example.com/file")
        assert result is not None  # Should be blocked (either scheme or DNS)

    def test_blocked_scheme_file(self) -> None:
        result = is_ssrf_target("file:///etc/passwd")
        assert result is not None

    def test_normal_https_url(self) -> None:
        result = is_ssrf_target("https://www.google.com")
        # Google resolves to public IPs, so this should be safe
        assert result is None

    def test_normal_http_url(self) -> None:
        result = is_ssrf_target("https://www.example.com")
        assert result is None

    def test_prometheus_blocked(self) -> None:
        result = is_ssrf_target("http://prometheus:9090/api/v1/query")
        assert result is not None

    def test_grafana_blocked(self) -> None:
        result = is_ssrf_target("http://grafana:3000/dashboard")
        assert result is not None

    def test_metadata_google_internal_blocked(self) -> None:
        result = is_ssrf_target("http://metadata.google.internal/computeMetadata/v1/")
        assert result is not None


@pytest.mark.unit
class TestVideoConstants:
    """Tests for video constant sets."""

    def test_video_domains_contains_youtube(self) -> None:
        assert any(domain == "youtube.com" for domain in VIDEO_DOMAINS)

    def test_video_extensions_contains_mp4(self) -> None:
        assert ".mp4" in VIDEO_EXTENSIONS

    def test_video_extensions_are_lowercase(self) -> None:
        for ext in VIDEO_EXTENSIONS:
            assert ext == ext.lower()
            assert ext.startswith(".")
