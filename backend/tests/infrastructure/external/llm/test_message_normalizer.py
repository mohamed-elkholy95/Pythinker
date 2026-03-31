"""Tests for the universal message normalizer (Phase 4).

Covers: string coercion, system-first enforcement, role alternation,
reasoning_content stripping, orphaned tool_call handling.
"""

from __future__ import annotations

from app.domain.external.llm_capabilities import ProviderCapabilities
from app.infrastructure.external.llm.message_normalizer import (
    _enforce_role_alternation,
    _enforce_system_first,
    _strip_reasoning_content,
    coerce_content_to_text,
    normalize_for_provider,
)

# ─────────────────────────── Helpers ─────────────────────────────────────────

GLM_CAPS = ProviderCapabilities(
    json_schema=False,
    content_format="string_only",
    system_message_position="first_only",
    parallel_tool_calls=False,
)

OPENAI_CAPS = ProviderCapabilities()  # defaults — flexible


# ─────────────────────────── coerce_content_to_text ─────────────────────────


def test_coerce_none_returns_empty():
    assert coerce_content_to_text(None) == ""


def test_coerce_string_returns_as_is():
    assert coerce_content_to_text("hello") == "hello"


def test_coerce_list_with_text_blocks():
    content = [{"type": "text", "text": "part1"}, {"type": "text", "text": "part2"}]
    result = coerce_content_to_text(content)
    assert "part1" in result
    assert "part2" in result


def test_coerce_list_drops_image_blocks():
    content = [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}},
        {"type": "text", "text": "describe this"},
    ]
    result = coerce_content_to_text(content)
    assert "describe this" in result
    assert "image_url" not in result
    assert "abc123" not in result


def test_coerce_empty_list_returns_empty():
    assert coerce_content_to_text([]) == ""


# ─────────────────────────── _strip_reasoning_content ────────────────────────


def test_strip_reasoning_content_removes_field():
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "ok", "reasoning_content": "my thoughts"},
    ]
    result = _strip_reasoning_content(messages)
    assert "reasoning_content" not in result[1]
    assert result[1]["content"] == "ok"


def test_strip_reasoning_content_fills_missing_content_for_tool_calls():
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}],
        }
    ]
    result = _strip_reasoning_content(messages)
    assert result[0]["content"] == ""


def test_strip_reasoning_content_no_op_without_field():
    messages = [{"role": "user", "content": "hi"}]
    result = _strip_reasoning_content(messages)
    assert result == messages


# ─────────────────────────── _enforce_role_alternation ───────────────────────


def test_merge_consecutive_user_messages():
    messages = [
        {"role": "user", "content": "first"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "ok"},
    ]
    result = _enforce_role_alternation(messages)
    assert len(result) == 2
    assert "first" in result[0]["content"]
    assert "second" in result[0]["content"]


def test_no_merge_when_roles_alternate():
    messages = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "q2"},
    ]
    result = _enforce_role_alternation(messages)
    assert len(result) == 3


def test_no_merge_when_tool_calls_present():
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}],
        },
        {"role": "assistant", "content": "done"},
    ]
    result = _enforce_role_alternation(messages)
    # Should not merge because first has tool_calls
    assert len(result) == 2


# ─────────────────────────── _enforce_system_first ───────────────────────────


def test_system_message_moved_to_front():
    messages = [
        {"role": "user", "content": "q"},
        {"role": "system", "content": "You are helpful"},
        {"role": "assistant", "content": "a"},
    ]
    result = _enforce_system_first(messages)
    assert result[0]["role"] == "system"


def test_multiple_system_messages_merged():
    messages = [
        {"role": "system", "content": "part1"},
        {"role": "user", "content": "q"},
        {"role": "system", "content": "part2"},
    ]
    result = _enforce_system_first(messages)
    system_msgs = [m for m in result if m["role"] == "system"]
    assert len(system_msgs) == 1
    assert "part1" in system_msgs[0]["content"]
    assert "part2" in system_msgs[0]["content"]


def test_leading_assistant_gets_placeholder_user_prepended():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": "start"},
    ]
    result = _enforce_system_first(messages)
    non_system = [m for m in result if m["role"] != "system"]
    assert non_system[0]["role"] == "user"


# ─────────────────────────── normalize_for_provider ──────────────────────────


def test_normalize_glm_full_pipeline():
    messages = [
        {"role": "user", "content": "q"},
        {"role": "system", "content": "sys"},  # out of position for GLM
        {"role": "assistant", "content": [{"type": "text", "text": "block content"}]},
        {"role": "assistant", "content": "duplicate"},  # consecutive assistant
    ]
    result = normalize_for_provider(messages, GLM_CAPS, provider_type="glm")

    # System should be first
    assert result[0]["role"] == "system"
    # Content should be plain strings (GLM string_only)
    for msg in result:
        if msg.get("content") is not None:
            assert isinstance(msg["content"], str)


def test_normalize_openai_flexible_preserves_list_content():
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    result = normalize_for_provider(messages, OPENAI_CAPS, provider_type="openai")
    # No coercion needed for flexible — content passes through
    assert result[0]["content"] == "hello"
    assert result[1]["content"] == "world"


def test_normalize_empty_messages_returns_empty():
    result = normalize_for_provider([], OPENAI_CAPS)
    assert result == []


def test_normalize_strips_reasoning_content():
    messages = [
        {"role": "assistant", "content": "ok", "reasoning_content": "thoughts", "extra_field": "x"},
    ]
    result = normalize_for_provider(messages, OPENAI_CAPS)
    assert "reasoning_content" not in result[0]


def test_normalize_removes_nonstandard_fields():
    messages = [
        {"role": "user", "content": "hi", "unknown_field": "should_be_removed"},
    ]
    result = normalize_for_provider(messages, OPENAI_CAPS)
    assert "unknown_field" not in result[0]


def test_normalize_developer_role_converted_to_system():
    messages = [{"role": "developer", "content": "instructions"}]
    result = normalize_for_provider(messages, OPENAI_CAPS)
    assert result[0]["role"] == "system"


def test_normalize_none_content_becomes_empty_string():
    messages = [{"role": "user", "content": None}]
    result = normalize_for_provider(messages, OPENAI_CAPS)
    assert result[0]["content"] == ""
