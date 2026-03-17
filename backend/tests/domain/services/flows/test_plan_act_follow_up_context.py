"""Tests for follow-up context routing in PlanActFlow.

Verifies that suggestion-click follow-ups bypass fast path and use full contextual flow.
"""

from app.domain.models.message import Message
from app.domain.services.flows.plan_act import should_bypass_fast_path_for_suggestion


class TestFollowUpContextDetection:
    """Tests for detecting suggestion follow-ups using metadata and regex fallback."""

    def test_metadata_based_detection_for_suggestion_click(self):
        """When follow_up_source='suggestion_click', should bypass fast path."""
        message = Message(
            message="What are the best next steps?",
            follow_up_source="suggestion_click",
            follow_up_selected_suggestion="What are the best next steps?",
            follow_up_anchor_event_id="evt_123",
        )

        has_recent_assistant_reply = True

        # Should bypass fast path due to metadata
        assert should_bypass_fast_path_for_suggestion(message, has_recent_assistant_reply) is True

    def test_regex_fallback_when_no_metadata(self):
        """When no metadata but message matches regex, should bypass fast path."""
        message = Message(
            message="Can you explain this in more detail?",
            # No follow_up_source metadata
        )

        has_recent_assistant_reply = True

        # Should bypass fast path due to regex fallback
        assert should_bypass_fast_path_for_suggestion(message, has_recent_assistant_reply) is True

    def test_metadata_bypasses_even_without_assistant_reply(self):
        """Metadata-based detection should bypass fast path even without recent assistant reply."""
        message = Message(
            message="Can you explain this in more detail?",
            follow_up_source="suggestion_click",
        )

        has_recent_assistant_reply = False

        # Should bypass - explicit metadata takes precedence over has_recent_assistant_reply
        assert should_bypass_fast_path_for_suggestion(message, has_recent_assistant_reply) is True

    def test_regex_requires_assistant_reply(self):
        """Regex-based fallback detection should require recent assistant reply."""
        message = Message(
            message="Can you explain this in more detail?",  # Matches regex pattern
            # No follow_up_source metadata
        )

        has_recent_assistant_reply = False

        # Should NOT bypass - regex fallback requires assistant reply
        assert should_bypass_fast_path_for_suggestion(message, has_recent_assistant_reply) is False

    def test_no_bypass_for_regular_messages(self):
        """Regular messages without metadata or regex match should not bypass."""
        message = Message(
            message="what is python?",
            # No follow_up metadata, doesn't match regex
        )

        has_recent_assistant_reply = True

        # Should NOT bypass fast path
        assert should_bypass_fast_path_for_suggestion(message, has_recent_assistant_reply) is False

    def test_metadata_with_non_suggestion_source(self):
        """Metadata with source other than 'suggestion_click' uses regex fallback."""
        message = Message(
            message="Can you explain this in more detail?",
            follow_up_source="manual_input",  # Not "suggestion_click"
        )

        has_recent_assistant_reply = True

        # Should bypass due to regex fallback (message matches pattern)
        assert should_bypass_fast_path_for_suggestion(message, has_recent_assistant_reply) is True
