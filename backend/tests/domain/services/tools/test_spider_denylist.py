"""Tests for spider denylist expansion — social media platforms."""
import pytest
from app.infrastructure.external.scraper.research_spider import should_skip_spider, SPIDER_DENYLIST_DOMAINS
from app.domain.services.tools.search import _should_skip_spider as search_should_skip_spider


class TestSpiderDenylistExpansion:
    """Verify social media domains are blocked from spider enrichment."""

    @pytest.mark.parametrize("url", [
        "https://www.instagram.com/p/DVaK8iICao8/",
        "https://instagram.com/reel/abc123",
        "https://www.facebook.com/some-page",
        "https://facebook.com/groups/python",
        "https://www.tiktok.com/@user/video/123",
        "https://tiktok.com/explore",
        "https://www.linkedin.com/pulse/article",
        "https://linkedin.com/posts/user-123",
        "https://www.pinterest.com/pin/123",
        "https://pinterest.com/ideas/python",
    ])
    def test_social_media_blocked_research_spider(self, url: str):
        assert should_skip_spider(url) is True

    @pytest.mark.parametrize("url", [
        "https://www.instagram.com/p/DVaK8iICao8/",
        "https://www.facebook.com/some-page",
        "https://www.tiktok.com/@user/video/123",
        "https://www.linkedin.com/pulse/article",
        "https://www.pinterest.com/pin/123",
    ])
    def test_social_media_blocked_search_module(self, url: str):
        assert search_should_skip_spider(url) is True

    @pytest.mark.parametrize("url", [
        "https://github.com/python/cpython",
        "https://dev.to/article",
        "https://blog.bytebytego.com/p/top-ai",
        "https://docs.python.org/3/",
        "https://stackoverflow.com/questions/123",
    ])
    def test_legitimate_domains_allowed(self, url: str):
        assert should_skip_spider(url) is False
        assert search_should_skip_spider(url) is False
