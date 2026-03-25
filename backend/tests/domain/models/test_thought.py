"""Tests for thought chain-of-thought domain models."""

import pytest

from app.domain.models.thought import (
    ReasoningStep,
    Thought,
    ThoughtChain,
    ThoughtQuality,
    ThoughtType,
)


@pytest.mark.unit
class TestThoughtTypeEnum:
    def test_all_values(self) -> None:
        expected = {
            "observation", "analysis", "hypothesis", "inference",
            "evaluation", "decision", "reflection", "uncertainty",
        }
        assert {t.value for t in ThoughtType} == expected


@pytest.mark.unit
class TestThoughtQualityEnum:
    def test_all_values(self) -> None:
        expected = {"high", "medium", "low", "uncertain"}
        assert {q.value for q in ThoughtQuality} == expected


@pytest.mark.unit
class TestThought:
    def _make_thought(self, **kwargs) -> Thought:
        defaults = {
            "type": ThoughtType.OBSERVATION,
            "content": "The data shows a trend",
        }
        defaults.update(kwargs)
        return Thought(**defaults)

    def test_basic_construction(self) -> None:
        thought = self._make_thought()
        assert thought.content == "The data shows a trend"
        assert thought.type == ThoughtType.OBSERVATION
        assert thought.confidence == 0.5
        assert thought.quality == ThoughtQuality.MEDIUM

    def test_is_high_quality_true(self) -> None:
        thought = self._make_thought(quality=ThoughtQuality.HIGH, confidence=0.9)
        assert thought.is_high_quality() is True

    def test_is_high_quality_false_low_confidence(self) -> None:
        thought = self._make_thought(quality=ThoughtQuality.HIGH, confidence=0.5)
        assert thought.is_high_quality() is False

    def test_is_high_quality_false_medium_quality(self) -> None:
        thought = self._make_thought(quality=ThoughtQuality.MEDIUM, confidence=0.9)
        assert thought.is_high_quality() is False

    def test_has_evidence(self) -> None:
        thought = self._make_thought(supporting_evidence=["Source A"])
        assert thought.has_evidence() is True

    def test_has_no_evidence(self) -> None:
        thought = self._make_thought()
        assert thought.has_evidence() is False

    def test_is_contested(self) -> None:
        thought = self._make_thought(contradicting_evidence=["Source B says otherwise"])
        assert thought.is_contested() is True

    def test_is_not_contested(self) -> None:
        thought = self._make_thought()
        assert thought.is_contested() is False


@pytest.mark.unit
class TestReasoningStep:
    def test_basic_construction(self) -> None:
        step = ReasoningStep(name="Analysis")
        assert step.name == "Analysis"
        assert step.thoughts == []
        assert step.is_complete is False

    def test_add_thought(self) -> None:
        step = ReasoningStep(name="Analysis")
        thought = Thought(type=ThoughtType.ANALYSIS, content="analyzing...")
        step.add_thought(thought)
        assert len(step.thoughts) == 1

    def test_get_average_confidence_empty(self) -> None:
        step = ReasoningStep(name="Empty")
        assert step.get_average_confidence() == 0.0

    def test_get_average_confidence(self) -> None:
        step = ReasoningStep(name="Test")
        step.add_thought(Thought(type=ThoughtType.ANALYSIS, content="a", confidence=0.8))
        step.add_thought(Thought(type=ThoughtType.ANALYSIS, content="b", confidence=0.6))
        assert step.get_average_confidence() == pytest.approx(0.7)

    def test_get_high_quality_thoughts(self) -> None:
        step = ReasoningStep(name="Test")
        step.add_thought(Thought(type=ThoughtType.ANALYSIS, content="a", quality=ThoughtQuality.HIGH, confidence=0.9))
        step.add_thought(Thought(type=ThoughtType.ANALYSIS, content="b", quality=ThoughtQuality.LOW, confidence=0.3))
        high = step.get_high_quality_thoughts()
        assert len(high) == 1


@pytest.mark.unit
class TestThoughtChain:
    def test_basic_construction(self) -> None:
        chain = ThoughtChain(problem="What should we do?")
        assert chain.problem == "What should we do?"
        assert chain.steps == []
        assert chain.final_decision is None

    def test_add_step(self) -> None:
        chain = ThoughtChain(problem="test")
        step = ReasoningStep(name="Step 1")
        chain.add_step(step)
        assert len(chain.steps) == 1

    def test_get_all_thoughts(self) -> None:
        chain = ThoughtChain(problem="test")
        step1 = ReasoningStep(name="S1")
        step1.add_thought(Thought(type=ThoughtType.OBSERVATION, content="obs1"))
        step2 = ReasoningStep(name="S2")
        step2.add_thought(Thought(type=ThoughtType.DECISION, content="dec1"))
        chain.add_step(step1)
        chain.add_step(step2)
        assert len(chain.get_all_thoughts()) == 2

    def test_get_thoughts_by_type(self) -> None:
        chain = ThoughtChain(problem="test")
        step = ReasoningStep(name="S1")
        step.add_thought(Thought(type=ThoughtType.OBSERVATION, content="obs"))
        step.add_thought(Thought(type=ThoughtType.DECISION, content="dec"))
        step.add_thought(Thought(type=ThoughtType.UNCERTAINTY, content="unc"))
        chain.add_step(step)
        assert len(chain.get_thoughts_by_type(ThoughtType.OBSERVATION)) == 1
        assert len(chain.get_decisions()) == 1
        assert len(chain.get_uncertainties()) == 1

    def test_calculate_overall_confidence_empty(self) -> None:
        chain = ThoughtChain(problem="test")
        assert chain.calculate_overall_confidence() == 0.0

    def test_calculate_overall_confidence(self) -> None:
        chain = ThoughtChain(problem="test")
        s1 = ReasoningStep(name="S1")
        s1.add_thought(Thought(type=ThoughtType.ANALYSIS, content="a", confidence=0.8))
        s2 = ReasoningStep(name="S2")
        s2.add_thought(Thought(type=ThoughtType.ANALYSIS, content="b", confidence=0.6))
        chain.add_step(s1)
        chain.add_step(s2)
        assert chain.calculate_overall_confidence() == pytest.approx(0.7)
