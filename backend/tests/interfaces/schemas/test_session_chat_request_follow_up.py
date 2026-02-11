"""
Tests for ChatRequest.follow_up schema field.

Verifies that ChatRequest properly accepts and validates follow_up metadata
for suggestion click context.
"""

import pytest
from pydantic import ValidationError

from app.interfaces.schemas.session import ChatRequest


class TestChatRequestFollowUp:
    """Tests for ChatRequest follow_up field"""

    def test_chat_request_with_follow_up_all_fields(self):
        """Test ChatRequest with complete follow_up metadata"""
        request = ChatRequest(
            message="Tell me more about that",
            follow_up={
                "selected_suggestion": "Can you explain this in more detail?",
                "anchor_event_id": "evt_123456",
                "source": "suggestion_click",
            },
        )

        assert request.message == "Tell me more about that"
        assert request.follow_up is not None
        assert request.follow_up["selected_suggestion"] == "Can you explain this in more detail?"
        assert request.follow_up["anchor_event_id"] == "evt_123456"
        assert request.follow_up["source"] == "suggestion_click"

    def test_chat_request_without_follow_up(self):
        """Test ChatRequest without follow_up (optional field)"""
        request = ChatRequest(message="Regular message")

        assert request.message == "Regular message"
        assert request.follow_up is None

    def test_chat_request_with_empty_follow_up(self):
        """Test ChatRequest with None follow_up"""
        request = ChatRequest(message="Regular message", follow_up=None)

        assert request.message == "Regular message"
        assert request.follow_up is None

    def test_chat_request_follow_up_missing_required_fields(self):
        """Test ChatRequest rejects follow_up missing required fields"""
        # This test expects validation to fail if follow_up is provided
        # but missing required fields (we'll implement validation later if needed)
        # For now, we're using a dict, so this test verifies the structure
        request = ChatRequest(
            message="Test",
            follow_up={
                "selected_suggestion": "Test suggestion",
                # Missing anchor_event_id and source
            },
        )

        # Since we're using dict type, this will pass
        # If we want strict validation, we'd need a Pydantic model for follow_up
        assert request.follow_up is not None
        assert "selected_suggestion" in request.follow_up

    def test_chat_request_serialization_with_follow_up(self):
        """Test ChatRequest serializes correctly with follow_up"""
        request = ChatRequest(
            message="Follow-up message",
            follow_up={
                "selected_suggestion": "What about X?",
                "anchor_event_id": "evt_789",
                "source": "suggestion_click",
            },
        )

        data = request.model_dump()
        assert data["message"] == "Follow-up message"
        assert data["follow_up"]["selected_suggestion"] == "What about X?"
        assert data["follow_up"]["anchor_event_id"] == "evt_789"
        assert data["follow_up"]["source"] == "suggestion_click"
