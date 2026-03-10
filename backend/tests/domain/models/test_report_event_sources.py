"""Tests for ReportEvent sources normalization."""
from app.domain.models.event import ReportEvent


class TestReportEventSourcesNormalization:
    """ReportEvent.sources should never be None after construction."""

    def test_none_sources_normalized_to_empty_list(self):
        event = ReportEvent(id="test-1", title="Test", content="# Report", sources=None)
        assert event.sources == []
        assert event.sources is not None

    def test_missing_sources_normalized_to_empty_list(self):
        event = ReportEvent(id="test-2", title="Test", content="# Report")
        assert event.sources == []

    def test_present_sources_preserved(self):
        from datetime import UTC, datetime

        from app.domain.models.source_citation import SourceCitation
        src = SourceCitation(
            url="https://example.com",
            title="Example",
            access_time=datetime.now(UTC),
            source_type="search",
        )
        event = ReportEvent(id="test-3", title="Test", content="# Report", sources=[src])
        assert len(event.sources) == 1
