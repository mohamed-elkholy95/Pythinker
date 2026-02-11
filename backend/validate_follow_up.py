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

    print("=" * 70)
    print("BACKEND FOLLOW-UP CONTEXT VALIDATION")
    print("=" * 70)

    # Test 1: ChatRequest with follow_up
    print("\n✓ Test 1: ChatRequest with follow_up")
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
    print("  ✓ ChatRequest accepts and stores follow_up metadata")

    # Test 2: ChatRequest without follow_up
    print("\n✓ Test 2: ChatRequest without follow_up (optional)")
    request = ChatRequest(message="Regular message")
    assert request.message == "Regular message"
    assert request.follow_up is None
    print("  ✓ ChatRequest works without follow_up (None by default)")

    # Test 3: ChatRequest serialization
    print("\n✓ Test 3: ChatRequest serialization with follow_up")
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
    print("  ✓ ChatRequest serializes follow_up correctly")

    # Test 4: Message domain model
    print("\n✓ Test 4: Message domain model with follow_up fields")
    message = Message(
        message="Test message",
        follow_up_selected_suggestion="Test suggestion",
        follow_up_anchor_event_id="evt_abc",
        follow_up_source="suggestion_click",
    )
    assert message.follow_up_selected_suggestion == "Test suggestion"
    assert message.follow_up_anchor_event_id == "evt_abc"
    assert message.follow_up_source == "suggestion_click"
    print("  ✓ Message model has follow_up fields")

    # Test 5: MessageEvent
    print("\n✓ Test 5: MessageEvent with follow_up fields")
    event = MessageEvent(
        message="Test message",
        follow_up_selected_suggestion="Test suggestion",
        follow_up_anchor_event_id="evt_xyz",
        follow_up_source="suggestion_click",
    )
    assert event.follow_up_selected_suggestion == "Test suggestion"
    assert event.follow_up_anchor_event_id == "evt_xyz"
    assert event.follow_up_source == "suggestion_click"
    print("  ✓ MessageEvent has follow_up fields")

    # Test 6: MessageEvent serialization
    print("\n✓ Test 6: MessageEvent serialization")
    event_data = event.model_dump()
    assert event_data["follow_up_selected_suggestion"] == "Test suggestion"
    assert event_data["follow_up_anchor_event_id"] == "evt_xyz"
    assert event_data["follow_up_source"] == "suggestion_click"
    print("  ✓ MessageEvent serializes follow_up fields correctly")

    print("\n" + "=" * 70)
    print("ALL VALIDATION TESTS PASSED ✓")
    print("=" * 70)
    sys.exit(0)

except Exception as e:
    print(f"\n✗ VALIDATION FAILED: {type(e).__name__}: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
