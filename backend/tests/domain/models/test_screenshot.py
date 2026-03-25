"""Tests for screenshot domain models: ScreenshotTrigger and SessionScreenshot."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.models.screenshot import ScreenshotTrigger, SessionScreenshot

# ---------------------------------------------------------------------------
# ScreenshotTrigger enum
# ---------------------------------------------------------------------------


def test_screenshot_trigger_all_members():
    """All five trigger values exist as enum members."""
    assert ScreenshotTrigger.TOOL_BEFORE == "tool_before"
    assert ScreenshotTrigger.TOOL_AFTER == "tool_after"
    assert ScreenshotTrigger.PERIODIC == "periodic"
    assert ScreenshotTrigger.SESSION_START == "session_start"
    assert ScreenshotTrigger.SESSION_END == "session_end"


def test_screenshot_trigger_member_count():
    assert len(ScreenshotTrigger) == 5


def test_screenshot_trigger_is_str_subclass():
    """ScreenshotTrigger inherits from str for JSON-safe serialization."""
    for member in ScreenshotTrigger:
        assert isinstance(member, str)


def test_screenshot_trigger_from_string_value():
    """Enum members can be looked up by their string value."""
    assert ScreenshotTrigger("tool_before") is ScreenshotTrigger.TOOL_BEFORE
    assert ScreenshotTrigger("periodic") is ScreenshotTrigger.PERIODIC
    assert ScreenshotTrigger("session_end") is ScreenshotTrigger.SESSION_END


def test_screenshot_trigger_invalid_value_raises():
    with pytest.raises(ValueError):
        ScreenshotTrigger("unknown_trigger")


def test_screenshot_trigger_values_are_lowercase_snake():
    for member in ScreenshotTrigger:
        assert member.value == member.value.lower()
        assert " " not in member.value


# ---------------------------------------------------------------------------
# SessionScreenshot — required fields
# ---------------------------------------------------------------------------


def _make_screenshot(**overrides) -> SessionScreenshot:
    """Return a minimal valid SessionScreenshot."""
    defaults = {
        "id": "ss-001",
        "session_id": "sess-abc",
        "sequence_number": 1,
        "storage_key": "sess-abc/0001_periodic.jpg",
        "trigger": ScreenshotTrigger.PERIODIC,
    }
    defaults.update(overrides)
    return SessionScreenshot(**defaults)


def test_session_screenshot_minimal_construction():
    ss = _make_screenshot()
    assert ss.id == "ss-001"
    assert ss.session_id == "sess-abc"
    assert ss.sequence_number == 1
    assert ss.storage_key == "sess-abc/0001_periodic.jpg"
    assert ss.trigger == ScreenshotTrigger.PERIODIC


def test_session_screenshot_missing_id_raises():
    with pytest.raises(ValidationError) as exc_info:
        SessionScreenshot(  # type: ignore[call-arg]
            session_id="sess",
            sequence_number=0,
            storage_key="key",
            trigger=ScreenshotTrigger.PERIODIC,
        )
    field_names = [e["loc"][0] for e in exc_info.value.errors()]
    assert "id" in field_names


def test_session_screenshot_missing_session_id_raises():
    with pytest.raises(ValidationError) as exc_info:
        SessionScreenshot(  # type: ignore[call-arg]
            id="ss-001",
            sequence_number=0,
            storage_key="key",
            trigger=ScreenshotTrigger.PERIODIC,
        )
    field_names = [e["loc"][0] for e in exc_info.value.errors()]
    assert "session_id" in field_names


def test_session_screenshot_missing_storage_key_raises():
    with pytest.raises(ValidationError) as exc_info:
        SessionScreenshot(  # type: ignore[call-arg]
            id="ss-001",
            session_id="sess",
            sequence_number=0,
            trigger=ScreenshotTrigger.PERIODIC,
        )
    field_names = [e["loc"][0] for e in exc_info.value.errors()]
    assert "storage_key" in field_names


def test_session_screenshot_missing_trigger_raises():
    with pytest.raises(ValidationError) as exc_info:
        SessionScreenshot(  # type: ignore[call-arg]
            id="ss-001",
            session_id="sess",
            sequence_number=0,
            storage_key="key",
        )
    field_names = [e["loc"][0] for e in exc_info.value.errors()]
    assert "trigger" in field_names


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_session_screenshot_default_timestamp_is_utc():
    before = datetime.now(UTC)
    ss = _make_screenshot()
    after = datetime.now(UTC)
    assert ss.timestamp.tzinfo is not None
    assert before <= ss.timestamp <= after


def test_session_screenshot_default_thumbnail_is_none():
    ss = _make_screenshot()
    assert ss.thumbnail_storage_key is None


def test_session_screenshot_default_tool_call_id_is_none():
    ss = _make_screenshot()
    assert ss.tool_call_id is None


def test_session_screenshot_default_tool_name_is_none():
    ss = _make_screenshot()
    assert ss.tool_name is None


def test_session_screenshot_default_function_name_is_none():
    ss = _make_screenshot()
    assert ss.function_name is None


def test_session_screenshot_default_action_type_is_none():
    ss = _make_screenshot()
    assert ss.action_type is None


def test_session_screenshot_default_size_bytes_is_zero():
    ss = _make_screenshot()
    assert ss.size_bytes == 0


def test_session_screenshot_default_perceptual_hash_is_none():
    ss = _make_screenshot()
    assert ss.perceptual_hash is None


def test_session_screenshot_default_is_duplicate_is_false():
    ss = _make_screenshot()
    assert ss.is_duplicate is False


def test_session_screenshot_default_original_storage_key_is_none():
    ss = _make_screenshot()
    assert ss.original_storage_key is None


# ---------------------------------------------------------------------------
# Trigger variants
# ---------------------------------------------------------------------------


def test_session_screenshot_trigger_tool_before():
    ss = _make_screenshot(trigger=ScreenshotTrigger.TOOL_BEFORE)
    assert ss.trigger == ScreenshotTrigger.TOOL_BEFORE


def test_session_screenshot_trigger_tool_after():
    ss = _make_screenshot(trigger=ScreenshotTrigger.TOOL_AFTER)
    assert ss.trigger == ScreenshotTrigger.TOOL_AFTER


def test_session_screenshot_trigger_session_start():
    ss = _make_screenshot(trigger=ScreenshotTrigger.SESSION_START)
    assert ss.trigger == ScreenshotTrigger.SESSION_START


def test_session_screenshot_trigger_session_end():
    ss = _make_screenshot(trigger=ScreenshotTrigger.SESSION_END)
    assert ss.trigger == ScreenshotTrigger.SESSION_END


def test_session_screenshot_trigger_from_string():
    """Trigger can be supplied as a raw string value."""
    ss = _make_screenshot(trigger="tool_after")  # type: ignore[arg-type]
    assert ss.trigger == ScreenshotTrigger.TOOL_AFTER


# ---------------------------------------------------------------------------
# Tool context fields
# ---------------------------------------------------------------------------


def test_session_screenshot_with_tool_context():
    ss = _make_screenshot(
        trigger=ScreenshotTrigger.TOOL_AFTER,
        tool_call_id="call-xyz",
        tool_name="browser_navigate",
        function_name="navigate",
        action_type="browser",
    )
    assert ss.tool_call_id == "call-xyz"
    assert ss.tool_name == "browser_navigate"
    assert ss.function_name == "navigate"
    assert ss.action_type == "browser"


def test_session_screenshot_with_thumbnail():
    ss = _make_screenshot(thumbnail_storage_key="sess-abc/0001_thumb.jpg")
    assert ss.thumbnail_storage_key == "sess-abc/0001_thumb.jpg"


def test_session_screenshot_with_explicit_timestamp():
    ts = datetime(2026, 3, 25, 12, 0, 0, tzinfo=UTC)
    ss = _make_screenshot(timestamp=ts)
    assert ss.timestamp == ts


def test_session_screenshot_with_size_bytes():
    ss = _make_screenshot(size_bytes=98_304)
    assert ss.size_bytes == 98_304


# ---------------------------------------------------------------------------
# Deduplication fields
# ---------------------------------------------------------------------------


def test_session_screenshot_mark_as_duplicate():
    """is_duplicate=True with a reference to the original storage key."""
    original = _make_screenshot(
        id="ss-001",
        sequence_number=1,
        storage_key="sess/0001_periodic.jpg",
    )
    duplicate = _make_screenshot(
        id="ss-002",
        sequence_number=2,
        storage_key="sess/0002_periodic.jpg",
        is_duplicate=True,
        perceptual_hash="aabbccddeeff0011",
        original_storage_key=original.storage_key,
    )
    assert duplicate.is_duplicate is True
    assert duplicate.original_storage_key == "sess/0001_periodic.jpg"
    assert duplicate.perceptual_hash == "aabbccddeeff0011"


def test_session_screenshot_not_duplicate_keeps_defaults():
    ss = _make_screenshot(perceptual_hash="deadbeef01234567")
    assert ss.is_duplicate is False
    assert ss.original_storage_key is None
    assert ss.perceptual_hash == "deadbeef01234567"


# ---------------------------------------------------------------------------
# sequence_number variants
# ---------------------------------------------------------------------------


def test_session_screenshot_sequence_number_zero():
    ss = _make_screenshot(sequence_number=0)
    assert ss.sequence_number == 0


def test_session_screenshot_sequence_number_large():
    ss = _make_screenshot(sequence_number=9999)
    assert ss.sequence_number == 9999


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_session_screenshot_model_dump_includes_all_fields():
    ss = _make_screenshot()
    data = ss.model_dump()
    expected_keys = {
        "id",
        "session_id",
        "sequence_number",
        "timestamp",
        "storage_key",
        "thumbnail_storage_key",
        "trigger",
        "tool_call_id",
        "tool_name",
        "function_name",
        "action_type",
        "size_bytes",
        "perceptual_hash",
        "is_duplicate",
        "original_storage_key",
    }
    assert expected_keys.issubset(data.keys())


def test_session_screenshot_model_dump_trigger_is_string():
    """Trigger should serialize as its string value, not the enum object."""
    ss = _make_screenshot(trigger=ScreenshotTrigger.PERIODIC)
    data = ss.model_dump()
    # Pydantic v2 serializes StrEnum as string by default
    assert data["trigger"] in (ScreenshotTrigger.PERIODIC, "periodic")


def test_session_screenshot_round_trip_from_dict():
    ts = datetime(2026, 3, 25, 10, 0, 0, tzinfo=UTC)
    original = _make_screenshot(
        id="ss-rt",
        sequence_number=5,
        timestamp=ts,
        trigger=ScreenshotTrigger.TOOL_AFTER,
        tool_call_id="call-rt",
        size_bytes=512,
        is_duplicate=False,
    )
    data = original.model_dump()
    restored = SessionScreenshot.model_validate(data)
    assert restored.id == original.id
    assert restored.sequence_number == original.sequence_number
    assert restored.trigger == original.trigger
    assert restored.tool_call_id == original.tool_call_id
    assert restored.size_bytes == original.size_bytes


def test_session_screenshot_round_trip_via_json():
    ss = _make_screenshot(
        id="ss-json",
        trigger=ScreenshotTrigger.SESSION_START,
        perceptual_hash="cafebabe",
    )
    json_str = ss.model_dump_json()
    restored = SessionScreenshot.model_validate_json(json_str)
    assert restored.id == "ss-json"
    assert restored.trigger == ScreenshotTrigger.SESSION_START
    assert restored.perceptual_hash == "cafebabe"
