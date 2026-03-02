"""Tests for extended SearchToolContent model."""

import pytest

from app.domain.models.event import SearchToolContent
from app.domain.models.search import SearchResultItem


class TestSearchToolContentExtended:
    """Verify SearchToolContent has new optional metadata fields."""

    def test_basic_construction(self):
        item = SearchResultItem(title="Test", link="https://example.com", snippet="A snippet")
        content = SearchToolContent(results=[item])
        assert len(content.results) == 1
        assert content.provider is None
        assert content.search_depth is None
        assert content.credits_used is None
        assert content.intent_tier is None

    def test_with_metadata(self):
        item = SearchResultItem(title="Test", link="https://example.com", snippet="snippet")
        content = SearchToolContent(
            results=[item],
            provider="tavily",
            search_depth="advanced",
            credits_used=2,
            intent_tier="standard",
        )
        assert content.provider == "tavily"
        assert content.search_depth == "advanced"
        assert content.credits_used == 2
        assert content.intent_tier == "standard"

    def test_serializes_to_dict(self):
        item = SearchResultItem(title="T", link="https://x.com", snippet="s")
        content = SearchToolContent(results=[item], provider="serper", credits_used=1)
        data = content.model_dump()
        assert data["provider"] == "serper"
        assert data["credits_used"] == 1
        assert data["search_depth"] is None  # Optional, not set
