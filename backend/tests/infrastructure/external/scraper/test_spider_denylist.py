"""Tests for spider domain denylist.

Domains like reddit.com that block anonymous scraping should be
skipped by the spider. Search snippets are preserved instead.
"""

from __future__ import annotations

import pytest

try:
    from app.infrastructure.external.scraper.research_spider import (
        SPIDER_DENYLIST_DOMAINS,
        should_skip_spider,
    )
except ImportError:
    SPIDER_DENYLIST_DOMAINS = None  # type: ignore[assignment]
    should_skip_spider = None  # type: ignore[assignment]

pytestmark = pytest.mark.skipif(
    should_skip_spider is None,
    reason="scrapling/browserforge not installed",
)


class TestShouldSkipSpider:
    """URL-level denylist checks."""

    def test_reddit_www(self):
        assert should_skip_spider("https://www.reddit.com/r/OpenAI/comments/abc/title/")

    def test_reddit_bare(self):
        assert should_skip_spider("https://reddit.com/r/LocalLLaMA/comments/xyz/")

    def test_old_reddit(self):
        assert should_skip_spider("https://old.reddit.com/r/programming/")

    def test_x_com(self):
        assert should_skip_spider("https://x.com/elonmusk/status/12345")

    def test_twitter_legacy(self):
        assert should_skip_spider("https://twitter.com/openai/status/67890")

    def test_datacamp_allowed(self):
        assert not should_skip_spider("https://www.datacamp.com/blog/gpt-5-4")

    def test_github_allowed(self):
        assert not should_skip_spider("https://github.com/openai/codex")

    def test_empty_url(self):
        assert not should_skip_spider("")

    def test_malformed_url(self):
        assert not should_skip_spider("not-a-url")


class TestDenylistContents:
    """Verify denylist set contains expected domains."""

    def test_contains_reddit(self):
        assert "reddit.com" in SPIDER_DENYLIST_DOMAINS

    def test_contains_x(self):
        assert "x.com" in SPIDER_DENYLIST_DOMAINS

    def test_contains_twitter(self):
        assert "twitter.com" in SPIDER_DENYLIST_DOMAINS
