"""Tests for SourceCitation model."""

from datetime import UTC, datetime

from app.domain.models.source_citation import SourceCitation


class TestSourceCitation:
    def test_construction_search(self):
        now = datetime.now(UTC)
        c = SourceCitation(
            url="https://example.com",
            title="Example Page",
            access_time=now,
            source_type="search",
        )
        assert c.url == "https://example.com"
        assert c.title == "Example Page"
        assert c.snippet is None
        assert c.source_type == "search"

    def test_construction_browser(self):
        c = SourceCitation(
            url="https://example.com/page",
            title="Page Title",
            snippet="Some preview text",
            access_time=datetime.now(UTC),
            source_type="browser",
        )
        assert c.source_type == "browser"
        assert c.snippet == "Some preview text"

    def test_construction_file(self):
        c = SourceCitation(
            url="file:///tmp/data.csv",
            title="Data File",
            access_time=datetime.now(UTC),
            source_type="file",
        )
        assert c.source_type == "file"

    def test_serialization_roundtrip(self):
        now = datetime.now(UTC)
        c = SourceCitation(
            url="https://example.com",
            title="Test",
            snippet="preview",
            access_time=now,
            source_type="search",
        )
        data = c.model_dump()
        c2 = SourceCitation.model_validate(data)
        assert c2.url == c.url
        assert c2.title == c.title
        assert c2.snippet == c.snippet
        assert c2.source_type == c.source_type
