"""Tests for SuggestionEvent metadata fields."""

from app.domain.models.event import SuggestionEvent


class TestSuggestionEventMetadata:
    """Test SuggestionEvent includes anchor metadata for session context."""

    def test_suggestion_event_accepts_source_metadata(self):
        """SuggestionEvent should accept source field indicating where suggestions came from."""
        event = SuggestionEvent(
            suggestions=["What's next?", "Can you explain more?"],
            source="completion",
        )
        assert event.source == "completion"

    def test_suggestion_event_accepts_anchor_event_id(self):
        """SuggestionEvent should accept anchor_event_id to link to report/message."""
        event = SuggestionEvent(
            suggestions=["What's next?"],
            source="completion",
            anchor_event_id="report-123",
        )
        assert event.anchor_event_id == "report-123"

    def test_suggestion_event_accepts_anchor_excerpt(self):
        """SuggestionEvent should accept anchor_excerpt with content preview."""
        event = SuggestionEvent(
            suggestions=["Tell me more about X"],
            source="completion",
            anchor_event_id="report-123",
            anchor_excerpt="The analysis found 3 key insights...",
        )
        assert event.anchor_excerpt == "The analysis found 3 key insights..."

    def test_suggestion_event_metadata_fields_are_optional(self):
        """Metadata fields should be optional (backward compatibility)."""
        event = SuggestionEvent(suggestions=["Generic question"])
        assert event.source is None
        assert event.anchor_event_id is None
        assert event.anchor_excerpt is None

    def test_suggestion_event_serializes_with_metadata(self):
        """SuggestionEvent should serialize to dict including metadata."""
        event = SuggestionEvent(
            suggestions=["Follow-up 1", "Follow-up 2"],
            source="discuss",
            anchor_event_id="msg-456",
            anchor_excerpt="Brief excerpt here",
        )
        data = event.model_dump()
        assert data["source"] == "discuss"
        assert data["anchor_event_id"] == "msg-456"
        assert data["anchor_excerpt"] == "Brief excerpt here"
