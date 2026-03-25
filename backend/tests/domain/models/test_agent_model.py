"""Tests for Agent domain model."""

import pytest

from app.domain.models.agent import Agent, AgentLearningState, AgentPerformanceState, AgentPersona


class TestAgentPersona:
    def test_defaults(self) -> None:
        p = AgentPersona()
        assert p.style == "balanced"
        assert p.communication_tone == "professional"
        assert p.domain_expertise == []


class TestAgentPerformanceState:
    def test_defaults(self) -> None:
        s = AgentPerformanceState()
        assert s.tasks_completed == 0
        assert s.success_rate == 1.0


class TestAgentLearningState:
    def test_defaults(self) -> None:
        s = AgentLearningState()
        assert s.confidence_scores == {}
        assert s.preferred_strategies == []


class TestAgent:
    def test_defaults(self) -> None:
        a = Agent()
        assert len(a.id) > 0
        assert a.temperature == 0.7
        assert a.max_tokens == 2000

    def test_invalid_temperature(self) -> None:
        with pytest.raises(ValueError, match="Temperature"):
            Agent(temperature=3.0)

    def test_invalid_max_tokens(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            Agent(max_tokens=-1)

    def test_valid_temperature_range(self) -> None:
        a = Agent(temperature=0.0)
        assert a.temperature == 0.0
        a2 = Agent(temperature=2.0)
        assert a2.temperature == 2.0
