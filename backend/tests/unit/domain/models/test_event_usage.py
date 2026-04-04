"""Tests for UsageEvent (app.domain.models.event)."""

from __future__ import annotations

from pydantic import TypeAdapter

from app.domain.models.event import AgentEvent, UsageEvent


class TestUsageEvent:
    def test_creation(self) -> None:
        ev = UsageEvent(
            iterations=2,
            prompt_tokens=123,
            completion_tokens=45,
            estimated_cost_usd=0.001,
            duration_seconds=0.5,
        )
        assert ev.type == "usage"
        assert ev.iterations == 2
        assert ev.prompt_tokens == 123
        assert ev.completion_tokens == 45
        assert ev.estimated_cost_usd == 0.001
        assert ev.duration_seconds == 0.5

    def test_discriminated_union_parses_usage_event(self) -> None:
        parsed = TypeAdapter(AgentEvent).validate_python(
            {
                "type": "usage",
                "iterations": 1,
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "estimated_cost_usd": 0.0,
                "duration_seconds": 3.25,
            }
        )
        assert isinstance(parsed, UsageEvent)
        assert parsed.type == "usage"
