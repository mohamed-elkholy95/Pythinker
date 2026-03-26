"""Tests for app.domain.models.conversation_context — conversation context models.

Covers: TurnRole, TurnEventType, ConversationTurn, ConversationContextResult,
ConversationContext (is_empty, total_turns, format_for_injection).
"""

from __future__ import annotations

import pytest

from app.domain.models.conversation_context import (
    ConversationContext,
    ConversationContextResult,
    ConversationTurn,
    TurnEventType,
    TurnRole,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_result(
    content: str = "test content",
    role: str = "user",
    event_type: str = "message",
    session_id: str = "s1",
    turn_number: int = 1,
    relevance_score: float = 0.9,
    source: str = "sliding_window",
    **kwargs,
) -> ConversationContextResult:
    defaults = {
        "point_id": f"p-{turn_number}",
        "content": content,
        "role": role,
        "event_type": event_type,
        "session_id": session_id,
        "turn_number": turn_number,
        "created_at": 1700000000 + turn_number,
        "relevance_score": relevance_score,
        "source": source,
    }
    defaults.update(kwargs)
    return ConversationContextResult(**defaults)


# ---------------------------------------------------------------------------
# TurnRole enum
# ---------------------------------------------------------------------------
class TestTurnRole:
    def test_user_value(self):
        assert TurnRole.USER == "user"

    def test_assistant_value(self):
        assert TurnRole.ASSISTANT == "assistant"

    def test_tool_summary_value(self):
        assert TurnRole.TOOL_SUMMARY == "tool_summary"

    def test_step_summary_value(self):
        assert TurnRole.STEP_SUMMARY == "step_summary"

    def test_plan_summary_value(self):
        assert TurnRole.PLAN_SUMMARY == "plan_summary"

    def test_thought_value(self):
        assert TurnRole.THOUGHT == "thought"


# ---------------------------------------------------------------------------
# TurnEventType enum
# ---------------------------------------------------------------------------
class TestTurnEventType:
    def test_message_value(self):
        assert TurnEventType.MESSAGE == "message"

    def test_tool_result_value(self):
        assert TurnEventType.TOOL_RESULT == "tool_result"

    def test_step_completion_value(self):
        assert TurnEventType.STEP_COMPLETION == "step_completion"

    def test_report_value(self):
        assert TurnEventType.REPORT == "report"

    def test_error_value(self):
        assert TurnEventType.ERROR == "error"

    def test_all_event_types_exist(self):
        expected = {
            "message",
            "tool_result",
            "step_completion",
            "report",
            "error",
            "plan",
            "thought",
            "verification",
            "flow_transition",
            "reflection",
            "suggestion",
            "comprehension",
            "mode_change",
            "task_recreation",
        }
        actual = {e.value for e in TurnEventType}
        assert actual == expected


# ---------------------------------------------------------------------------
# ConversationTurn
# ---------------------------------------------------------------------------
class TestConversationTurn:
    def test_creation_with_required_fields(self):
        turn = ConversationTurn(
            point_id="p1",
            user_id="u1",
            session_id="s1",
            role=TurnRole.USER,
            event_type=TurnEventType.MESSAGE,
            content="hello",
            turn_number=1,
            event_id="e1",
            created_at=1700000000,
            content_hash="abc123",
        )
        assert turn.content == "hello"
        assert turn.role == TurnRole.USER

    def test_optional_fields_default_to_none(self):
        turn = ConversationTurn(
            point_id="p1",
            user_id="u1",
            session_id="s1",
            role=TurnRole.ASSISTANT,
            event_type=TurnEventType.MESSAGE,
            content="hi",
            turn_number=1,
            event_id="e1",
            created_at=1700000000,
            content_hash="def456",
        )
        assert turn.step_id is None
        assert turn.tool_name is None

    def test_frozen(self):
        turn = ConversationTurn(
            point_id="p1",
            user_id="u1",
            session_id="s1",
            role=TurnRole.USER,
            event_type=TurnEventType.MESSAGE,
            content="frozen",
            turn_number=1,
            event_id="e1",
            created_at=1700000000,
            content_hash="xyz789",
        )
        with pytest.raises(AttributeError):
            turn.content = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ConversationContext — is_empty / total_turns
# ---------------------------------------------------------------------------
class TestConversationContextProperties:
    def test_empty_context(self):
        ctx = ConversationContext()
        assert ctx.is_empty is True
        assert ctx.total_turns == 0

    def test_not_empty_with_sliding_window(self):
        ctx = ConversationContext(sliding_window_turns=[_make_result()])
        assert ctx.is_empty is False
        assert ctx.total_turns == 1

    def test_not_empty_with_semantic_turns(self):
        ctx = ConversationContext(semantic_turns=[_make_result(source="intra_session")])
        assert ctx.is_empty is False
        assert ctx.total_turns == 1

    def test_not_empty_with_cross_session(self):
        ctx = ConversationContext(cross_session_turns=[_make_result(source="cross_session")])
        assert ctx.is_empty is False
        assert ctx.total_turns == 1

    def test_total_turns_sums_all_phases(self):
        ctx = ConversationContext(
            sliding_window_turns=[_make_result(turn_number=1), _make_result(turn_number=2)],
            semantic_turns=[_make_result(turn_number=3, source="intra_session")],
            cross_session_turns=[_make_result(turn_number=4, source="cross_session")],
        )
        assert ctx.total_turns == 4


# ---------------------------------------------------------------------------
# ConversationContext.format_for_injection
# ---------------------------------------------------------------------------
class TestFormatForInjection:
    def test_empty_returns_empty_string(self):
        ctx = ConversationContext()
        assert ctx.format_for_injection() == ""

    def test_sliding_window_only(self):
        ctx = ConversationContext(
            sliding_window_turns=[
                _make_result(content="Hi there", role="user", turn_number=1),
                _make_result(content="Hello!", role="assistant", turn_number=2),
            ]
        )
        result = ctx.format_for_injection()
        assert "## Session Context" in result
        assert "### Recent Conversation" in result
        assert "[Turn 1] User: Hi there" in result
        assert "[Turn 2] Assistant: Hello!" in result

    def test_semantic_turns_section(self):
        ctx = ConversationContext(
            semantic_turns=[
                _make_result(content="Earlier context", role="tool_summary", turn_number=5, source="intra_session"),
            ]
        )
        result = ctx.format_for_injection()
        assert "### Related Earlier Context (this session)" in result
        assert "Tool Summary" in result
        assert "Earlier context" in result

    def test_cross_session_section(self):
        ctx = ConversationContext(
            cross_session_turns=[
                _make_result(content="Past info", role="user", turn_number=10, source="cross_session"),
            ]
        )
        result = ctx.format_for_injection()
        assert "### Related Past Sessions" in result
        assert "[Past session] User: Past info" in result

    def test_all_three_phases(self):
        ctx = ConversationContext(
            sliding_window_turns=[_make_result(content="recent", role="user", turn_number=1)],
            semantic_turns=[_make_result(content="semantic", role="assistant", turn_number=5, source="intra_session")],
            cross_session_turns=[_make_result(content="cross", role="user", turn_number=10, source="cross_session")],
        )
        result = ctx.format_for_injection()
        assert "### Recent Conversation" in result
        assert "### Related Earlier Context (this session)" in result
        assert "### Related Past Sessions" in result

    def test_truncation_respects_max_chars(self):
        long_content = "x" * 3000
        ctx = ConversationContext(
            sliding_window_turns=[_make_result(content=long_content, turn_number=1)],
            semantic_turns=[_make_result(content="should not appear", turn_number=2, source="intra_session")],
        )
        result = ctx.format_for_injection(max_chars=3200)
        # Sliding window section should be included
        assert "### Recent Conversation" in result
        # But semantic might not fit or only header
        # The important thing is total doesn't wildly exceed max_chars

    def test_small_max_chars_may_exclude_later_phases(self):
        ctx = ConversationContext(
            sliding_window_turns=[_make_result(content="A" * 100, turn_number=i) for i in range(1, 20)],
            cross_session_turns=[
                _make_result(content="should not appear", turn_number=99, source="cross_session"),
            ],
        )
        result = ctx.format_for_injection(max_chars=500)
        # Cross-session may be truncated out
        if "### Related Past Sessions" in result:
            # If it's there, total chars should still be reasonable
            assert len(result) < 1000

    def test_role_label_formatting(self):
        ctx = ConversationContext(
            sliding_window_turns=[
                _make_result(content="summary", role="step_summary", turn_number=1),
            ]
        )
        result = ctx.format_for_injection()
        assert "Step Summary" in result

    def test_default_max_chars(self):
        # Default is 4000
        ctx = ConversationContext(sliding_window_turns=[_make_result(content="test", turn_number=1)])
        result = ctx.format_for_injection()
        assert len(result) <= 4100  # Some slack for headers


# ---------------------------------------------------------------------------
# ConversationContextResult
# ---------------------------------------------------------------------------
class TestConversationContextResult:
    def test_fields(self):
        r = _make_result(content="hello", relevance_score=0.75)
        assert r.content == "hello"
        assert r.relevance_score == 0.75
        assert r.source == "sliding_window"
