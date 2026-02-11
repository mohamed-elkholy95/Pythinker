#!/usr/bin/env python3
"""
Validation script to verify ChatRequest.follow_up implementation.
This is a manual verification since conda environment has issues.
"""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app.domain.models.event import MessageEvent
    from app.domain.models.message import Message
    from app.interfaces.schemas.session import ChatRequest

    # Test 1: ChatRequest with follow_up
    request = ChatRequest(
        message="Tell me more about that",
        follow_up={
            "selected_suggestion": "Can you explain this in more detail?",
            "anchor_event_id": "evt_123456",
            "source": "suggestion_click",
        },
    )
    assert request.message == "Tell me more about that"  # noqa: S101 - Validation script uses asserts for testing
    assert request.follow_up is not None  # noqa: S101 - Validation script uses asserts for testing
    assert request.follow_up["selected_suggestion"] == "Can you explain this in more detail?"  # noqa: S101 - Validation script uses asserts for testing
    assert request.follow_up["anchor_event_id"] == "evt_123456"  # noqa: S101 - Validation script uses asserts for testing
    assert request.follow_up["source"] == "suggestion_click"  # noqa: S101 - Validation script uses asserts for testing

    # Test 2: ChatRequest without follow_up
    request = ChatRequest(message="Regular message")
    assert request.message == "Regular message"  # noqa: S101 - Validation script uses asserts for testing
    assert request.follow_up is None  # noqa: S101 - Validation script uses asserts for testing

    # Test 3: ChatRequest serialization
    request = ChatRequest(
        message="Follow-up message",
        follow_up={
            "selected_suggestion": "What about X?",
            "anchor_event_id": "evt_789",
            "source": "suggestion_click",
        },
    )
    data = request.model_dump()
    assert data["message"] == "Follow-up message"  # noqa: S101 - Validation script uses asserts for testing
    assert data["follow_up"]["selected_suggestion"] == "What about X?"  # noqa: S101 - Validation script uses asserts for testing
    assert data["follow_up"]["anchor_event_id"] == "evt_789"  # noqa: S101 - Validation script uses asserts for testing
    assert data["follow_up"]["source"] == "suggestion_click"  # noqa: S101 - Validation script uses asserts for testing

    # Test 4: Message domain model
    message = Message(
        message="Test message",
        follow_up_selected_suggestion="Test suggestion",
        follow_up_anchor_event_id="evt_abc",
        follow_up_source="suggestion_click",
    )
    assert message.follow_up_selected_suggestion == "Test suggestion"  # noqa: S101 - Validation script uses asserts for testing
    assert message.follow_up_anchor_event_id == "evt_abc"  # noqa: S101 - Validation script uses asserts for testing
    assert message.follow_up_source == "suggestion_click"  # noqa: S101 - Validation script uses asserts for testing

    # Test 5: MessageEvent
    event = MessageEvent(
        message="Test message",
        follow_up_selected_suggestion="Test suggestion",
        follow_up_anchor_event_id="evt_xyz",
        follow_up_source="suggestion_click",
    )
    assert event.follow_up_selected_suggestion == "Test suggestion"  # noqa: S101 - Validation script uses asserts for testing
    assert event.follow_up_anchor_event_id == "evt_xyz"  # noqa: S101 - Validation script uses asserts for testing
    assert event.follow_up_source == "suggestion_click"  # noqa: S101 - Validation script uses asserts for testing

    # Test 6: MessageEvent serialization
    event_data = event.model_dump()
    assert event_data["follow_up_selected_suggestion"] == "Test suggestion"  # noqa: S101 - Validation script uses asserts for testing
    assert event_data["follow_up_anchor_event_id"] == "evt_xyz"  # noqa: S101 - Validation script uses asserts for testing
    assert event_data["follow_up_source"] == "suggestion_click"  # noqa: S101 - Validation script uses asserts for testing

    sys.exit(0)

except Exception:
    import traceback

    traceback.print_exc()
    sys.exit(1)
