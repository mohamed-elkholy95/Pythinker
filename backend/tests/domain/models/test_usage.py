"""Tests for usage module — UsageType, UsageRecord, SessionUsage.

Covers:
  - UsageType enum members
  - UsageRecord defaults and fields
  - SessionUsage defaults and aggregation fields
"""

from __future__ import annotations

from app.domain.models.usage import SessionUsage, UsageRecord, UsageType


class TestUsageType:
    """UsageType enum members."""

    def test_members(self) -> None:
        assert UsageType.LLM_CALL.value == "llm_call"
        assert UsageType.TOOL_CALL.value == "tool_call"
        assert UsageType.EMBEDDING.value == "embedding"
        assert len(UsageType) == 3


class TestUsageRecord:
    """UsageRecord model."""

    def test_defaults(self) -> None:
        r = UsageRecord(user_id="u1", session_id="s1", model="gpt-4", provider="openai")
        assert r.prompt_tokens == 0
        assert r.completion_tokens == 0
        assert r.cached_tokens == 0
        assert r.total_cost == 0.0
        assert r.usage_type == UsageType.LLM_CALL
        assert len(r.id) == 16
        assert r.created_at is not None

    def test_custom_values(self) -> None:
        r = UsageRecord(
            user_id="u1",
            session_id="s1",
            model="claude-3",
            provider="anthropic",
            prompt_tokens=1000,
            completion_tokens=500,
            cached_tokens=200,
            prompt_cost=0.01,
            completion_cost=0.03,
            total_cost=0.04,
        )
        assert r.prompt_tokens == 1000
        assert r.total_cost == 0.04


class TestSessionUsage:
    """SessionUsage model."""

    def test_defaults(self) -> None:
        su = SessionUsage(session_id="s1", user_id="u1")
        assert su.total_prompt_tokens == 0
        assert su.total_completion_tokens == 0
        assert su.total_cost == 0.0
        assert su.llm_call_count == 0
        assert su.tool_call_count == 0
        assert su.tokens_by_model == {}
        assert su.cost_by_model == {}
        assert su.first_activity is None
        assert su.last_activity is None
