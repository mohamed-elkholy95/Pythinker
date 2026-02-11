"""
Tests for ChatRequest.follow_up schema field.

Verifies that ChatRequest properly accepts and validates follow_up metadata
for suggestion click context.
"""

import pytest
from pydantic import ValidationError

from app.interfaces.schemas.session import ChatRequest, FollowUpContext


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
        assert isinstance(request.follow_up, FollowUpContext)
        assert request.follow_up.selected_suggestion == "Can you explain this in more detail?"
        assert request.follow_up.anchor_event_id == "evt_123456"
        assert request.follow_up.source == "suggestion_click"

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
        # With Pydantic model, this should now raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(
                message="Test",
                follow_up={
                    "selected_suggestion": "Test suggestion",
                    # Missing anchor_event_id (required field)
                },
            )

        # Verify that anchor_event_id is mentioned in the error
        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any("anchor_event_id" in str(error) for error in errors)

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

    def test_chat_request_follow_up_default_source(self):
        """Test ChatRequest follow_up with default source value"""
        request = ChatRequest(
            message="Follow-up message",
            follow_up={
                "selected_suggestion": "What about X?",
                "anchor_event_id": "evt_789",
                # source not provided, should use default
            },
        )

        assert request.follow_up is not None
        assert request.follow_up.source == "suggestion_click"

    def test_follow_up_context_validation(self):
        """Test FollowUpContext direct validation"""
        # Valid context
        context = FollowUpContext(
            selected_suggestion="Test suggestion",
            anchor_event_id="evt_123",
        )
        assert context.selected_suggestion == "Test suggestion"
        assert context.anchor_event_id == "evt_123"
        assert context.source == "suggestion_click"

        # Missing required field
        with pytest.raises(ValidationError) as exc_info:
            FollowUpContext(selected_suggestion="Test suggestion")

        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any("anchor_event_id" in str(error) for error in errors)
