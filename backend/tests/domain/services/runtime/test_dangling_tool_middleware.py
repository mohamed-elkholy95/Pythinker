"""Tests for DanglingToolCallMiddleware and sanitize_tool_history.

Covers:
- Complete tool call / response pairs are left unchanged.
- A dangling tool call receives a synthetic placeholder message.
- Multiple dangling calls across separate assistant messages are all patched.
- Empty message list returns an empty list.
"""

from __future__ import annotations

import pytest

from app.domain.services.runtime.dangling_tool_middleware import (
    _PLACEHOLDER,
    DanglingToolCallMiddleware,
    sanitize_tool_history,
)
from app.domain.services.runtime.middleware import RuntimeContext

# ─────────────────────────── sanitize_tool_history ───────────────────────────


def test_no_dangling_calls_unchanged() -> None:
    """Assistant message with one tool call that already has a tool response."""
    messages = [
        {"role": "user", "content": "Search for something."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_abc", "function": {"name": "search"}}],
        },
        {"role": "tool", "tool_call_id": "call_abc", "content": "result here"},
        {"role": "assistant", "content": "Done."},
    ]

    result = sanitize_tool_history(messages)

    assert len(result) == 4  # nothing injected


def test_dangling_call_gets_placeholder() -> None:
    """Assistant with 2 tool_calls but only 1 tool response — 1 placeholder injected."""
    messages = [
        {"role": "user", "content": "Do two things."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "function": {"name": "tool_a"}},
                {"id": "call_2", "function": {"name": "tool_b"}},
            ],
        },
        # Only call_1 has a response; call_2 is dangling.
        {"role": "tool", "tool_call_id": "call_1", "content": "result_a"},
    ]

    result = sanitize_tool_history(messages)

    # 3 original messages + 1 injected placeholder = 4 total.
    assert len(result) == 4

    # Locate the injected placeholder.
    injected = [m for m in result if m.get("role") == "tool" and m.get("tool_call_id") == "call_2"]
    assert len(injected) == 1
    assert injected[0]["content"] == _PLACEHOLDER


def test_multiple_dangling_across_messages() -> None:
    """Two separate assistant messages each with 1 dangling tool call."""
    messages = [
        {"role": "user", "content": "Step one."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_x", "function": {"name": "tool_x"}}],
        },
        # No tool response for call_x.
        {"role": "user", "content": "Step two."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_y", "function": {"name": "tool_y"}}],
        },
        # No tool response for call_y either.
    ]

    result = sanitize_tool_history(messages)

    # 4 original + 2 injected placeholders = 6 messages.
    assert len(result) == 6

    placeholder_ids = {
        m["tool_call_id"] for m in result if m.get("role") == "tool" and m.get("content") == _PLACEHOLDER
    }
    assert placeholder_ids == {"call_x", "call_y"}


def test_empty_messages_returns_empty() -> None:
    """Empty input produces empty output."""
    result = sanitize_tool_history([])
    assert result == []


# ─────────────────────────── DanglingToolCallMiddleware ──────────────────────


@pytest.mark.asyncio
class TestDanglingToolCallMiddleware:
    async def test_before_step_sanitizes_message_history(self) -> None:
        """before_step replaces dangling calls in ctx.metadata['message_history']."""
        messages = [
            {"role": "user", "content": "Go."},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call_z", "function": {"name": "tool_z"}}],
            },
            # No tool response — call_z is dangling.
        ]

        ctx = RuntimeContext(
            session_id="sess-test",
            agent_id="a-1",
            metadata={"message_history": messages},
        )

        middleware = DanglingToolCallMiddleware()
        result_ctx = await middleware.before_step(ctx)

        history = result_ctx.metadata["message_history"]
        # 2 original + 1 injected = 3.
        assert len(history) == 3
        injected = [m for m in history if m.get("tool_call_id") == "call_z"]
        assert injected[0]["content"] == _PLACEHOLDER

    async def test_before_step_no_message_history_is_noop(self) -> None:
        """before_step is a no-op when message_history is absent from metadata."""
        ctx = RuntimeContext(session_id="sess-noop", agent_id="a-1", metadata={})

        middleware = DanglingToolCallMiddleware()
        result_ctx = await middleware.before_step(ctx)

        assert result_ctx is ctx
        assert "message_history" not in result_ctx.metadata
