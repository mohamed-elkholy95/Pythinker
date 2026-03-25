"""Tests for visited source domain model."""

import hashlib

import pytest

from app.domain.models.visited_source import (
    ContentAccessMethod,
    VisitedSource,
)


@pytest.mark.unit
class TestContentAccessMethodEnum:
    def test_all_values(self) -> None:
        expected = {
            "browser_navigate", "browser_get_content", "http_fetch",
            "search_snippet", "file_read", "mcp_tool",
        }
        assert {m.value for m in ContentAccessMethod} == expected


@pytest.mark.unit
class TestVisitedSource:
    def _make_source(self, content: str = "Sample page content for testing", **kwargs) -> VisitedSource:
        defaults = {
            "session_id": "sess1",
            "tool_event_id": "evt1",
            "url": "https://example.com/article",
            "content": content,
            "access_method": ContentAccessMethod.BROWSER_NAVIGATE,
        }
        defaults.update(kwargs)
        return VisitedSource.create(**defaults)

    def test_create_basic(self) -> None:
        source = self._make_source()
        assert source.session_id == "sess1"
        assert source.url == "https://example.com/article"
        assert source.access_method == ContentAccessMethod.BROWSER_NAVIGATE
        assert source.id  # auto-generated

    def test_content_hash_correct(self) -> None:
        content = "Hello world"
        source = self._make_source(content=content)
        expected_hash = hashlib.sha256(content.encode()).hexdigest()
        assert source.content_hash == expected_hash

    def test_content_length(self) -> None:
        content = "A" * 500
        source = self._make_source(content=content)
        assert source.content_length == 500

    def test_content_preview_capped(self) -> None:
        content = "A" * 5000
        source = self._make_source(content=content)
        assert len(source.content_preview) <= 2000

    def test_full_content_stored(self) -> None:
        content = "Full content here"
        source = self._make_source(content=content)
        assert source.full_content == content

    def test_content_contains(self) -> None:
        source = self._make_source(content="The accuracy was 92% in testing")
        assert source.content_contains("accuracy") is True
        assert source.content_contains("missing_text") is False

    def test_content_contains_case_insensitive(self) -> None:
        source = self._make_source(content="Hello World")
        assert source.content_contains("hello world") is True
        assert source.content_contains("HELLO WORLD") is True

    def test_content_contains_case_sensitive(self) -> None:
        source = self._make_source(content="Hello World")
        assert source.content_contains("hello world", case_sensitive=True) is False
        assert source.content_contains("Hello World", case_sensitive=True) is True

    def test_content_contains_number(self) -> None:
        source = self._make_source(content="The model achieved 92.5% accuracy")
        assert source.content_contains_number(92.5) is True
        assert source.content_contains_number(50.0) is False

    def test_content_contains_number_integer(self) -> None:
        source = self._make_source(content="There are 42 items")
        assert source.content_contains_number(42) is True

    def test_get_excerpt_containing(self) -> None:
        content = "A" * 200 + "TARGET_TEXT" + "B" * 200
        source = self._make_source(content=content)
        excerpt = source.get_excerpt_containing("TARGET_TEXT", context_chars=50)
        assert excerpt is not None
        assert "TARGET_TEXT" in excerpt

    def test_get_excerpt_not_found(self) -> None:
        source = self._make_source(content="Nothing special here")
        assert source.get_excerpt_containing("NONEXISTENT") is None

    def test_is_fully_accessible(self) -> None:
        source = self._make_source()
        assert source.is_fully_accessible is True

    def test_is_not_fully_accessible_paywall(self) -> None:
        source = self._make_source(paywall_confidence=0.8)
        assert source.is_fully_accessible is False

    def test_is_search_snippet_only(self) -> None:
        source = self._make_source(access_method=ContentAccessMethod.SEARCH_SNIPPET)
        assert source.is_search_snippet_only is True

    def test_is_not_search_snippet(self) -> None:
        source = self._make_source(access_method=ContentAccessMethod.BROWSER_NAVIGATE)
        assert source.is_search_snippet_only is False

    def test_set_full_content(self) -> None:
        source = self._make_source(content="initial")
        source.set_full_content("new full content")
        assert source.full_content == "new full content"

    def test_final_url(self) -> None:
        source = self._make_source(final_url="https://example.com/redirected")
        assert source.final_url == "https://example.com/redirected"
