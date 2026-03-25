"""Tests for Message domain model."""

from __future__ import annotations

from app.domain.models.message import Message

# ---------------------------------------------------------------------------
# Empty / minimal construction
# ---------------------------------------------------------------------------


def test_message_empty_construction():
    """Message can be constructed with no arguments at all."""
    msg = Message()
    assert msg.title is None
    assert msg.message == ""
    assert msg.attachments == []
    assert msg.skills == []
    assert msg.thinking_mode is None
    assert msg.follow_up_selected_suggestion is None
    assert msg.follow_up_anchor_event_id is None
    assert msg.follow_up_source is None


def test_message_no_required_fields():
    """Pydantic should not raise when constructing with no arguments."""
    # No fields are required; this must not raise ValidationError.
    msg = Message()
    assert isinstance(msg, Message)


# ---------------------------------------------------------------------------
# title field
# ---------------------------------------------------------------------------


def test_message_with_title():
    msg = Message(title="Research task")
    assert msg.title == "Research task"


def test_message_title_default_is_none():
    msg = Message()
    assert msg.title is None


def test_message_title_can_be_empty_string():
    msg = Message(title="")
    assert msg.title == ""


# ---------------------------------------------------------------------------
# message field
# ---------------------------------------------------------------------------


def test_message_with_message_text():
    msg = Message(message="Hello, Pythinker!")
    assert msg.message == "Hello, Pythinker!"


def test_message_default_message_is_empty_string():
    msg = Message()
    assert msg.message == ""


def test_message_with_multiline_text():
    text = "Line one\nLine two\nLine three"
    msg = Message(message=text)
    assert msg.message == text


# ---------------------------------------------------------------------------
# attachments field
# ---------------------------------------------------------------------------


def test_message_default_attachments_is_empty_list():
    msg = Message()
    assert msg.attachments == []


def test_message_with_single_attachment():
    msg = Message(attachments=["file-001"])
    assert msg.attachments == ["file-001"]


def test_message_with_multiple_attachments():
    ids = ["file-001", "file-002", "file-003"]
    msg = Message(attachments=ids)
    assert msg.attachments == ids
    assert len(msg.attachments) == 3


def test_message_attachments_are_independent_between_instances():
    """Default factory must produce a new list for each instance."""
    msg_a = Message()
    msg_b = Message()
    msg_a.attachments.append("file-x")
    assert msg_b.attachments == []


# ---------------------------------------------------------------------------
# skills field
# ---------------------------------------------------------------------------


def test_message_default_skills_is_empty_list():
    msg = Message()
    assert msg.skills == []


def test_message_with_single_skill():
    msg = Message(skills=["excel-generator"])
    assert msg.skills == ["excel-generator"]


def test_message_with_multiple_skills():
    skills = ["excel-generator", "research-assistant", "code-runner"]
    msg = Message(skills=skills)
    assert msg.skills == skills


def test_message_skills_are_independent_between_instances():
    """Default factory must produce a new list for each instance."""
    msg_a = Message()
    msg_b = Message()
    msg_a.skills.append("skill-x")
    assert msg_b.skills == []


# ---------------------------------------------------------------------------
# thinking_mode field
# ---------------------------------------------------------------------------


def test_message_default_thinking_mode_is_none():
    msg = Message()
    assert msg.thinking_mode is None


def test_message_thinking_mode_auto():
    msg = Message(thinking_mode="auto")
    assert msg.thinking_mode == "auto"


def test_message_thinking_mode_fast():
    msg = Message(thinking_mode="fast")
    assert msg.thinking_mode == "fast"


def test_message_thinking_mode_deep_think():
    msg = Message(thinking_mode="deep_think")
    assert msg.thinking_mode == "deep_think"


def test_message_thinking_mode_arbitrary_string():
    """The field is a plain str — no enum validation expected."""
    msg = Message(thinking_mode="custom_mode")
    assert msg.thinking_mode == "custom_mode"


# ---------------------------------------------------------------------------
# Follow-up fields
# ---------------------------------------------------------------------------


def test_message_default_follow_up_fields_are_none():
    msg = Message()
    assert msg.follow_up_selected_suggestion is None
    assert msg.follow_up_anchor_event_id is None
    assert msg.follow_up_source is None


def test_message_with_follow_up_selected_suggestion():
    msg = Message(follow_up_selected_suggestion="Tell me more about Python")
    assert msg.follow_up_selected_suggestion == "Tell me more about Python"


def test_message_with_follow_up_anchor_event_id():
    msg = Message(follow_up_anchor_event_id="evt-abc-123")
    assert msg.follow_up_anchor_event_id == "evt-abc-123"


def test_message_with_follow_up_source():
    msg = Message(follow_up_source="suggestion_click")
    assert msg.follow_up_source == "suggestion_click"


def test_message_with_all_follow_up_fields():
    msg = Message(
        follow_up_selected_suggestion="What are the key risks?",
        follow_up_anchor_event_id="evt-xyz",
        follow_up_source="suggestion_click",
    )
    assert msg.follow_up_selected_suggestion == "What are the key risks?"
    assert msg.follow_up_anchor_event_id == "evt-xyz"
    assert msg.follow_up_source == "suggestion_click"


# ---------------------------------------------------------------------------
# Full construction
# ---------------------------------------------------------------------------


def test_message_full_construction():
    """All fields can be set together."""
    msg = Message(
        title="Full message",
        message="Please analyse this data",
        attachments=["file-1", "file-2"],
        skills=["excel-generator"],
        thinking_mode="deep_think",
        follow_up_selected_suggestion="Expand on point 3",
        follow_up_anchor_event_id="evt-001",
        follow_up_source="suggestion_click",
    )
    assert msg.title == "Full message"
    assert msg.message == "Please analyse this data"
    assert msg.attachments == ["file-1", "file-2"]
    assert msg.skills == ["excel-generator"]
    assert msg.thinking_mode == "deep_think"
    assert msg.follow_up_selected_suggestion == "Expand on point 3"
    assert msg.follow_up_anchor_event_id == "evt-001"
    assert msg.follow_up_source == "suggestion_click"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_message_model_dump_defaults():
    msg = Message()
    data = msg.model_dump()
    assert data["title"] is None
    assert data["message"] == ""
    assert data["attachments"] == []
    assert data["skills"] == []
    assert data["thinking_mode"] is None
    assert data["follow_up_selected_suggestion"] is None
    assert data["follow_up_anchor_event_id"] is None
    assert data["follow_up_source"] is None


def test_message_model_dump_with_values():
    msg = Message(message="Hello", skills=["sk1"], thinking_mode="auto")
    data = msg.model_dump()
    assert data["message"] == "Hello"
    assert data["skills"] == ["sk1"]
    assert data["thinking_mode"] == "auto"


def test_message_round_trip_from_dict():
    original = Message(
        title="RT title",
        message="Round trip",
        attachments=["a1"],
        skills=["s1"],
        thinking_mode="fast",
        follow_up_selected_suggestion="more",
        follow_up_anchor_event_id="evt-rt",
        follow_up_source="suggestion_click",
    )
    data = original.model_dump()
    restored = Message.model_validate(data)
    assert restored.title == original.title
    assert restored.message == original.message
    assert restored.attachments == original.attachments
    assert restored.skills == original.skills
    assert restored.thinking_mode == original.thinking_mode
    assert restored.follow_up_anchor_event_id == original.follow_up_anchor_event_id
    assert restored.follow_up_source == original.follow_up_source


def test_message_round_trip_via_json():
    msg = Message(message="JSON test", thinking_mode="deep_think", skills=["sk-x"])
    json_str = msg.model_dump_json()
    restored = Message.model_validate_json(json_str)
    assert restored.message == "JSON test"
    assert restored.thinking_mode == "deep_think"
    assert restored.skills == ["sk-x"]
