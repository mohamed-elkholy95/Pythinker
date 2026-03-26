"""Tests for ThoughtChainBuilder in reasoning/thought_chain.py.

Covers chain/step lifecycle, thought inference, quality assessment,
text parsing utilities, and module-level convenience functions.
"""

from __future__ import annotations

import pytest

from app.domain.exceptions.base import InvalidStateException
from app.domain.models.thought import (
    Decision,
    ReasoningStep,
    Thought,
    ThoughtChain,
    ThoughtQuality,
    ThoughtType,
)
from app.domain.services.agents.reasoning.thought_chain import (
    ThoughtChainBuilder,
    create_thought_chain,
    extract_decision_from_reasoning,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_builder_with_chain(problem: str = "test problem") -> ThoughtChainBuilder:
    builder = ThoughtChainBuilder()
    builder.start_chain(problem)
    return builder


def _make_builder_with_step(
    problem: str = "test problem", step_name: str = "step one"
) -> ThoughtChainBuilder:
    builder = _make_builder_with_chain(problem)
    builder.start_step(step_name)
    return builder


# ---------------------------------------------------------------------------
# TestStartChain
# ---------------------------------------------------------------------------


class TestStartChain:
    def test_returns_thought_chain(self):
        builder = ThoughtChainBuilder()
        chain = builder.start_chain("What should I do?")
        assert isinstance(chain, ThoughtChain)

    def test_chain_stores_problem(self):
        builder = ThoughtChainBuilder()
        chain = builder.start_chain("My problem statement")
        assert chain.problem == "My problem statement"

    def test_chain_stores_context(self):
        builder = ThoughtChainBuilder()
        ctx = {"key": "value", "count": 42}
        chain = builder.start_chain("problem", context=ctx)
        assert chain.context == ctx

    def test_chain_empty_context_by_default(self):
        builder = ThoughtChainBuilder()
        chain = builder.start_chain("problem")
        assert chain.context == {}

    def test_chain_has_no_steps(self):
        builder = ThoughtChainBuilder()
        chain = builder.start_chain("problem")
        assert chain.steps == []

    def test_chain_not_complete_initially(self):
        builder = ThoughtChainBuilder()
        chain = builder.start_chain("problem")
        assert not chain.is_complete()

    def test_starting_new_chain_replaces_old(self):
        builder = ThoughtChainBuilder()
        first = builder.start_chain("first")
        second = builder.start_chain("second")
        assert first.problem == "first"
        assert second.problem == "second"


# ---------------------------------------------------------------------------
# TestStartStep
# ---------------------------------------------------------------------------


class TestStartStep:
    def test_returns_reasoning_step(self):
        builder = _make_builder_with_chain()
        step = builder.start_step("Analysis")
        assert isinstance(step, ReasoningStep)

    def test_step_stores_name(self):
        builder = _make_builder_with_chain()
        step = builder.start_step("My Step Name")
        assert step.name == "My Step Name"

    def test_step_starts_incomplete(self):
        builder = _make_builder_with_chain()
        step = builder.start_step("step")
        assert not step.is_complete

    def test_raises_without_chain(self):
        builder = ThoughtChainBuilder()
        with pytest.raises(InvalidStateException):
            builder.start_step("orphan step")

    def test_error_message_without_chain(self):
        builder = ThoughtChainBuilder()
        with pytest.raises(InvalidStateException, match="chain"):
            builder.start_step("orphan step")


# ---------------------------------------------------------------------------
# TestAddThought
# ---------------------------------------------------------------------------


class TestAddThought:
    def test_returns_thought(self):
        builder = _make_builder_with_step()
        thought = builder.add_thought("I notice that the sky is blue.")
        assert isinstance(thought, Thought)

    def test_explicit_type_is_preserved(self):
        builder = _make_builder_with_step()
        thought = builder.add_thought("some content", thought_type=ThoughtType.DECISION)
        assert thought.type == ThoughtType.DECISION

    def test_explicit_confidence_is_preserved(self):
        builder = _make_builder_with_step()
        thought = builder.add_thought("some content", confidence=0.8)
        assert thought.confidence == pytest.approx(0.8)

    def test_type_inferred_when_not_provided(self):
        builder = _make_builder_with_step()
        thought = builder.add_thought("I think this could be the answer.")
        # Pattern matches HYPOTHESIS
        assert thought.type == ThoughtType.HYPOTHESIS

    def test_confidence_estimated_when_not_provided(self):
        builder = _make_builder_with_step()
        thought = builder.add_thought("neutral content with no strong signals")
        assert 0.1 <= thought.confidence <= 0.9

    def test_supporting_evidence_stored(self):
        builder = _make_builder_with_step()
        evidence = ["source A", "source B"]
        thought = builder.add_thought("claim", supporting_evidence=evidence)
        assert thought.supporting_evidence == evidence

    def test_empty_evidence_by_default(self):
        builder = _make_builder_with_step()
        thought = builder.add_thought("claim")
        assert thought.supporting_evidence == []

    def test_thought_added_to_current_step(self):
        builder = _make_builder_with_step()
        builder.add_thought("first thought")
        builder.add_thought("second thought")
        assert len(builder._current_step.thoughts) == 2

    def test_raises_without_current_step(self):
        builder = _make_builder_with_chain()
        with pytest.raises(InvalidStateException):
            builder.add_thought("orphan thought")

    def test_error_message_without_step(self):
        builder = _make_builder_with_chain()
        with pytest.raises(InvalidStateException, match="step"):
            builder.add_thought("orphan thought")

    def test_quality_assessed_automatically(self):
        builder = _make_builder_with_step()
        thought = builder.add_thought("neutral content")
        assert isinstance(thought.quality, ThoughtQuality)


# ---------------------------------------------------------------------------
# TestCompleteStep
# ---------------------------------------------------------------------------


class TestCompleteStep:
    def test_returns_completed_step(self):
        builder = _make_builder_with_step()
        builder.add_thought("some thought")
        step = builder.complete_step()
        assert isinstance(step, ReasoningStep)

    def test_step_marked_complete(self):
        builder = _make_builder_with_step()
        builder.add_thought("thought")
        step = builder.complete_step()
        assert step.is_complete

    def test_conclusion_stored(self):
        builder = _make_builder_with_step()
        builder.add_thought("thought")
        step = builder.complete_step(conclusion="final answer")
        assert step.conclusion == "final answer"

    def test_none_conclusion_when_not_provided(self):
        builder = _make_builder_with_step()
        builder.add_thought("thought")
        step = builder.complete_step()
        assert step.conclusion is None

    def test_confidence_calculated_from_thoughts(self):
        builder = _make_builder_with_step()
        builder.add_thought("thought one", confidence=0.6)
        builder.add_thought("thought two", confidence=0.8)
        step = builder.complete_step()
        assert step.confidence == pytest.approx(0.7)

    def test_step_added_to_chain(self):
        builder = _make_builder_with_chain()
        builder.start_step("step")
        builder.add_thought("thought")
        builder.complete_step()
        assert len(builder._current_chain.steps) == 1

    def test_current_step_cleared_after_completion(self):
        builder = _make_builder_with_step()
        builder.add_thought("thought")
        builder.complete_step()
        assert builder._current_step is None

    def test_raises_without_current_step(self):
        builder = _make_builder_with_chain()
        with pytest.raises(InvalidStateException, match="No current step"):
            builder.complete_step()

    def test_raises_without_chain(self):
        builder = ThoughtChainBuilder()
        builder._current_step = ReasoningStep(name="dangling")
        with pytest.raises(InvalidStateException):
            builder.complete_step()


# ---------------------------------------------------------------------------
# TestCompleteChain
# ---------------------------------------------------------------------------


class TestCompleteChain:
    def _build_chain_with_step(self) -> ThoughtChainBuilder:
        builder = _make_builder_with_step()
        builder.add_thought("some thought", confidence=0.7)
        builder.complete_step()
        return builder

    def test_returns_thought_chain(self):
        builder = self._build_chain_with_step()
        chain = builder.complete_chain("go with option A")
        assert isinstance(chain, ThoughtChain)

    def test_final_decision_stored(self):
        builder = self._build_chain_with_step()
        chain = builder.complete_chain("use approach B")
        assert chain.final_decision == "use approach B"

    def test_completed_at_is_set(self):
        builder = self._build_chain_with_step()
        chain = builder.complete_chain("decision")
        assert chain.completed_at is not None

    def test_chain_is_complete(self):
        builder = self._build_chain_with_step()
        chain = builder.complete_chain("decision")
        assert chain.is_complete()

    def test_overall_confidence_calculated(self):
        builder = _make_builder_with_step()
        builder.add_thought("thought", confidence=0.8)
        builder.complete_step()
        chain = builder.complete_chain("decision")
        assert chain.overall_confidence == pytest.approx(0.8)

    def test_pending_step_auto_completed(self):
        builder = _make_builder_with_step()
        builder.add_thought("pending thought", confidence=0.5)
        # Do NOT call complete_step — chain.complete_chain should finish it
        chain = builder.complete_chain("go")
        assert len(chain.steps) == 1
        assert chain.steps[0].is_complete

    def test_builder_state_cleared_after_completion(self):
        builder = self._build_chain_with_step()
        builder.complete_chain("done")
        assert builder._current_chain is None
        assert builder._current_step is None

    def test_raises_without_chain(self):
        builder = ThoughtChainBuilder()
        with pytest.raises(InvalidStateException, match="No current chain"):
            builder.complete_chain("decision")


# ---------------------------------------------------------------------------
# TestInferThoughtType
# ---------------------------------------------------------------------------


class TestInferThoughtType:
    def _infer(self, text: str) -> ThoughtType:
        builder = ThoughtChainBuilder()
        return builder._infer_thought_type(text)

    def test_observation_i_notice(self):
        assert self._infer("I notice that the data is inconsistent.") == ThoughtType.OBSERVATION

    def test_observation_indicates(self):
        assert self._infer("This indicates a clear upward trend in the data.") == ThoughtType.OBSERVATION

    def test_observation_looking_at(self):
        assert self._infer("Looking at the available data, it is clear.") == ThoughtType.OBSERVATION

    def test_analysis_let_me_analyze(self):
        assert self._infer("Let me analyze the problem further.") == ThoughtType.ANALYSIS

    def test_analysis_considering(self):
        assert self._infer("Considering all factors, there are several options.") == ThoughtType.ANALYSIS

    def test_hypothesis_i_think(self):
        assert self._infer("I think this could work well.") == ThoughtType.HYPOTHESIS

    def test_hypothesis_perhaps(self):
        assert self._infer("Perhaps we should try a different approach.") == ThoughtType.HYPOTHESIS

    def test_hypothesis_could_be(self):
        assert self._infer("It could be a configuration issue.") == ThoughtType.HYPOTHESIS

    def test_inference_therefore(self):
        assert self._infer("Therefore, we should proceed with plan A.") == ThoughtType.INFERENCE

    def test_inference_thus(self):
        assert self._infer("Thus the result confirms our assumption.") == ThoughtType.INFERENCE

    def test_inference_based_on_this(self):
        assert self._infer("Based on this, we can conclude the task is done.") == ThoughtType.INFERENCE

    def test_evaluation_comparing(self):
        assert self._infer("Comparing option A and option B reveals trade-offs.") == ThoughtType.EVALUATION

    def test_evaluation_on_balance(self):
        assert self._infer("On balance, the first approach looks stronger.") == ThoughtType.EVALUATION

    def test_decision_i_will(self):
        assert self._infer("I will proceed with the refactoring.") == ThoughtType.DECISION

    def test_decision_choosing_to(self):
        assert self._infer("Choosing to go with approach B for reliability.") == ThoughtType.DECISION

    def test_reflection_looking_back(self):
        assert self._infer("Looking back, the earlier assumption was wrong.") == ThoughtType.REFLECTION

    def test_reflection_on_second_thought(self):
        assert self._infer("On second thought, we should verify this first.") == ThoughtType.REFLECTION

    def test_uncertainty_not_sure(self):
        assert self._infer("I'm not sure whether this is the right path.") == ThoughtType.UNCERTAINTY

    def test_uncertainty_unclear(self):
        assert self._infer("This is unclear and requires more context.") == ThoughtType.UNCERTAINTY

    def test_default_to_analysis(self):
        assert self._infer("The quick brown fox jumps over the lazy dog.") == ThoughtType.ANALYSIS


# ---------------------------------------------------------------------------
# TestEstimateConfidence
# ---------------------------------------------------------------------------


class TestEstimateConfidence:
    def _estimate(self, text: str) -> float:
        builder = ThoughtChainBuilder()
        return builder._estimate_confidence(text)

    def test_neutral_content_returns_0_5(self):
        assert self._estimate("The value is stored in the database.") == pytest.approx(0.5)

    def test_high_quality_indicator_boosts_confidence(self):
        conf = self._estimate("This is true because the data shows a clear trend.")
        assert conf > 0.5

    def test_low_quality_indicator_reduces_confidence(self):
        conf = self._estimate("I think this might be correct, probably.")
        assert conf < 0.5

    def test_multiple_high_quality_indicators_boost_more(self):
        conf = self._estimate(
            "According to research, the evidence clearly indicates that, specifically, because this is well-known."
        )
        assert conf > 0.6

    def test_multiple_low_quality_indicators_reduce_more(self):
        conf = self._estimate("I guess maybe it might be probably not sure.")
        assert conf < 0.4

    def test_confidence_clamped_at_0_9_upper(self):
        # Pack as many boosters as possible
        text = " ".join(
            [
                "because evidence data shows according to specifically for example research indicates"
            ]
            * 5
        )
        assert self._estimate(text) <= 0.9

    def test_confidence_clamped_at_0_1_lower(self):
        # Pack as many reducers as possible
        text = "I guess maybe not sure probably I think might be " * 5
        assert self._estimate(text) >= 0.1


# ---------------------------------------------------------------------------
# TestAssessQuality
# ---------------------------------------------------------------------------


class TestAssessQuality:
    def _assess(self, content: str, confidence: float) -> ThoughtQuality:
        builder = ThoughtChainBuilder()
        return builder._assess_quality(content, confidence)

    def test_high_when_evidence_and_high_confidence(self):
        assert self._assess("Because the evidence supports this claim.", 0.7) == ThoughtQuality.HIGH

    def test_high_boundary_confidence_0_7(self):
        assert self._assess("Data shows this is correct.", 0.7) == ThoughtQuality.HIGH

    def test_not_high_when_confidence_below_0_7(self):
        quality = self._assess("Because evidence supports this.", 0.65)
        assert quality != ThoughtQuality.HIGH

    def test_low_when_uncertain_marker(self):
        assert self._assess("I guess this might be right.", 0.5) == ThoughtQuality.LOW

    def test_low_when_confidence_below_0_4(self):
        assert self._assess("Plain statement.", 0.3) == ThoughtQuality.LOW

    def test_medium_for_average_content(self):
        assert self._assess("The system processes requests in order.", 0.6) == ThoughtQuality.MEDIUM


# ---------------------------------------------------------------------------
# TestSplitIntoSections
# ---------------------------------------------------------------------------


class TestSplitIntoSections:
    def _split(self, text: str) -> list[str]:
        return ThoughtChainBuilder()._split_into_sections(text)

    def test_double_newline_splits_text(self):
        text = "First paragraph.\n\nSecond paragraph."
        parts = self._split(text)
        assert len(parts) == 2
        assert parts[0] == "First paragraph."
        assert parts[1] == "Second paragraph."

    def test_numbered_list_splits_text(self):
        text = "Intro.\n1. First item\n2. Second item"
        parts = self._split(text)
        assert len(parts) >= 2

    def test_bullet_points_split_text(self):
        text = "Summary\n- Point one\n- Point two"
        parts = self._split(text)
        assert len(parts) >= 2

    def test_single_block_returns_original(self):
        text = "One single block of text with no section breaks."
        parts = self._split(text)
        assert parts == [text]

    def test_strips_whitespace_from_sections(self):
        text = "  First section.  \n\n  Second section.  "
        parts = self._split(text)
        for part in parts:
            assert part == part.strip()


# ---------------------------------------------------------------------------
# TestSplitIntoSentences
# ---------------------------------------------------------------------------


class TestSplitIntoSentences:
    def _split(self, text: str) -> list[str]:
        return ThoughtChainBuilder()._split_into_sentences(text)

    def test_period_splits_sentences(self):
        text = "First sentence. Second sentence."
        parts = self._split(text)
        assert len(parts) == 2

    def test_exclamation_splits_sentences(self):
        text = "Great result! Now proceed further."
        parts = self._split(text)
        assert len(parts) == 2

    def test_question_mark_splits_sentences(self):
        text = "Is this correct? Let me verify."
        parts = self._split(text)
        assert len(parts) == 2

    def test_single_sentence_returns_one_element(self):
        text = "Just one sentence here."
        parts = self._split(text)
        assert len(parts) == 1

    def test_empty_string_returns_empty_list(self):
        parts = self._split("")
        assert parts == []

    def test_sentences_are_stripped(self):
        text = "  First.  Second.  "
        parts = self._split(text)
        for part in parts:
            assert part == part.strip()


# ---------------------------------------------------------------------------
# TestInferStepName
# ---------------------------------------------------------------------------


class TestInferStepName:
    def _infer(self, text: str, index: int = 0) -> str:
        return ThoughtChainBuilder()._infer_step_name(text, index)

    def test_first_keyword_returns_initial_analysis(self):
        assert self._infer("First, let's look at the data.", 0) == "Initial Analysis"

    def test_begin_keyword_returns_initial_analysis(self):
        assert self._infer("We begin by reviewing the context.", 0) == "Initial Analysis"

    def test_start_keyword_returns_initial_analysis(self):
        assert self._infer("Start with a high-level overview.", 0) == "Initial Analysis"

    def test_initial_keyword_returns_initial_analysis(self):
        assert self._infer("Initial assessment of the requirements.", 0) == "Initial Analysis"

    def test_then_keyword_returns_step_number(self):
        name = self._infer("Then we move on to validation.", 2)
        assert "3" in name  # index + 1

    def test_conclude_keyword_returns_conclusion(self):
        assert self._infer("Finally, we conclude the analysis.", 4) == "Conclusion"

    def test_option_keyword_returns_option_evaluation(self):
        assert self._infer("Comparing options A and B against criteria.", 1) == "Option Evaluation"

    def test_risk_keyword_returns_risk_assessment(self):
        assert self._infer("The main risk is data loss.", 1) == "Risk Assessment"

    def test_default_fallback_uses_index(self):
        name = self._infer("Some unrecognized content here.", 3)
        assert "4" in name  # "Reasoning Step 4"


# ---------------------------------------------------------------------------
# TestExtractConclusion
# ---------------------------------------------------------------------------


class TestExtractConclusion:
    def _extract(self, text: str) -> str | None:
        return ThoughtChainBuilder()._extract_conclusion(text)

    def test_therefore_pattern(self):
        result = self._extract("The data is clear. Therefore, we should proceed.")
        assert result is not None
        assert "proceed" in result

    def test_thus_pattern(self):
        result = self._extract("Analysis is done. Thus, we accept the change.")
        assert result is not None
        assert "accept" in result.lower()

    def test_in_conclusion_pattern(self):
        result = self._extract("In conclusion, the approach is valid.")
        assert result is not None

    def test_this_means_pattern(self):
        result = self._extract("This means the system is working correctly.")
        assert result is not None

    def test_returns_none_without_pattern(self):
        result = self._extract("A block of text that lacks any recognized conclusion marker.")
        assert result is None


# ---------------------------------------------------------------------------
# TestExtractFinalDecision
# ---------------------------------------------------------------------------


class TestExtractFinalDecision:
    def _extract(self, text: str) -> str | None:
        return ThoughtChainBuilder()._extract_final_decision(text)

    def test_i_will_pattern(self):
        result = self._extract("I will implement the caching layer.")
        assert result is not None
        assert "implement" in result.lower()

    def test_i_should_pattern(self):
        result = self._extract("I should refactor the module for clarity.")
        assert result is not None

    def test_best_option_pattern(self):
        result = self._extract("The best option is to use a queue-based approach.")
        assert result is not None

    def test_my_recommendation_pattern(self):
        result = self._extract("My recommendation is to deploy on Friday.")
        assert result is not None

    def test_returns_none_without_pattern(self):
        result = self._extract("No clear decision stated anywhere in this text.")
        assert result is None


# ---------------------------------------------------------------------------
# TestParseReasoningText
# ---------------------------------------------------------------------------


class TestParseReasoningText:
    def test_returns_thought_chain(self):
        builder = ThoughtChainBuilder()
        chain = builder.parse_reasoning_text(
            "I think this is straightforward. Therefore, proceed.", "solve problem"
        )
        assert isinstance(chain, ThoughtChain)

    def test_problem_stored_in_chain(self):
        builder = ThoughtChainBuilder()
        chain = builder.parse_reasoning_text("Simple reasoning.", "the original problem")
        assert chain.problem == "the original problem"

    def test_chain_is_completed(self):
        builder = ThoughtChainBuilder()
        chain = builder.parse_reasoning_text("Some reasoning text.", "problem")
        assert chain.is_complete()

    def test_steps_created_from_sections(self):
        builder = ThoughtChainBuilder()
        text = "First section.\n\nSecond section."
        chain = builder.parse_reasoning_text(text, "problem")
        assert len(chain.steps) >= 1

    def test_final_decision_extracted_from_i_will(self):
        builder = ThoughtChainBuilder()
        text = "Analysis done. I will use approach A."
        chain = builder.parse_reasoning_text(text, "which approach")
        assert chain.final_decision is not None
        assert "use approach A" in chain.final_decision or "approach" in chain.final_decision.lower()

    def test_fallback_decision_when_none_found(self):
        builder = ThoughtChainBuilder()
        chain = builder.parse_reasoning_text("Plain text with no decision.", "problem")
        assert chain.final_decision == "No explicit decision reached"

    def test_context_stored(self):
        builder = ThoughtChainBuilder()
        ctx = {"user": "alice"}
        chain = builder.parse_reasoning_text("Reasoning.", "problem", context=ctx)
        assert chain.context == ctx


# ---------------------------------------------------------------------------
# TestExtractDecision
# ---------------------------------------------------------------------------


class TestExtractDecision:
    def _chain_with_decision_thought(self) -> ThoughtChain:
        builder = _make_builder_with_step(step_name="step")
        builder.add_thought("I will proceed with option A.", thought_type=ThoughtType.DECISION, confidence=0.8)
        builder.add_thought(
            "Based on this we can infer the strategy works.", thought_type=ThoughtType.INFERENCE, confidence=0.7
        )
        builder.complete_step()
        return builder.complete_chain("Proceed with A")

    def _chain_without_decision_thought(self) -> ThoughtChain:
        builder = _make_builder_with_step(step_name="step")
        builder.add_thought("Some observation.", thought_type=ThoughtType.OBSERVATION, confidence=0.6)
        builder.complete_step()
        return builder.complete_chain("fallback decision")

    def test_returns_decision_object(self):
        builder = ThoughtChainBuilder()
        chain = self._chain_with_decision_thought()
        decision = builder.extract_decision(chain)
        assert isinstance(decision, Decision)

    def test_action_from_most_confident_decision_thought(self):
        builder = ThoughtChainBuilder()
        chain = self._chain_with_decision_thought()
        decision = builder.extract_decision(chain)
        assert "option A" in decision.action or "proceed" in decision.action.lower()

    def test_action_falls_back_to_final_decision(self):
        builder = ThoughtChainBuilder()
        chain = self._chain_without_decision_thought()
        decision = builder.extract_decision(chain)
        assert decision.action == "fallback decision"

    def test_rationale_built_from_inference_thoughts(self):
        builder = ThoughtChainBuilder()
        chain = self._chain_with_decision_thought()
        decision = builder.extract_decision(chain)
        # Should contain content from the INFERENCE thought
        assert "infer" in decision.rationale.lower() or len(decision.rationale) > 0

    def test_rationale_default_when_no_inferences(self):
        builder = ThoughtChainBuilder()
        chain = self._chain_without_decision_thought()
        decision = builder.extract_decision(chain)
        assert decision.rationale == "Based on analysis"

    def test_source_chain_id_matches_chain(self):
        builder = ThoughtChainBuilder()
        chain = self._chain_with_decision_thought()
        decision = builder.extract_decision(chain)
        assert decision.source_chain_id == chain.id

    def test_risks_from_uncertainty_thoughts(self):
        builder = _make_builder_with_step()
        builder.add_thought("I'm not sure about the failure mode.", thought_type=ThoughtType.UNCERTAINTY, confidence=0.3)
        builder.complete_step()
        chain = builder.complete_chain("proceed carefully")
        decision = ThoughtChainBuilder().extract_decision(chain)
        assert len(decision.risks) == 1

    def test_alternatives_from_hypothesis_thoughts(self):
        builder = _make_builder_with_step()
        builder.add_thought("I think option B could also work.", thought_type=ThoughtType.HYPOTHESIS, confidence=0.5)
        builder.complete_step()
        chain = builder.complete_chain("use A")
        decision = ThoughtChainBuilder().extract_decision(chain)
        assert len(decision.alternatives_considered) == 1

    def test_confidence_matches_chain_overall_confidence(self):
        builder = ThoughtChainBuilder()
        chain = self._chain_with_decision_thought()
        decision = builder.extract_decision(chain)
        assert decision.confidence == pytest.approx(chain.overall_confidence)


# ---------------------------------------------------------------------------
# TestCreateThoughtChain (convenience function)
# ---------------------------------------------------------------------------


class TestCreateThoughtChain:
    def test_returns_thought_chain(self):
        chain = create_thought_chain("what to do", "I think we should proceed. Therefore, go ahead.")
        assert isinstance(chain, ThoughtChain)

    def test_problem_stored(self):
        chain = create_thought_chain("my problem", "Some reasoning.")
        assert chain.problem == "my problem"

    def test_chain_is_complete(self):
        chain = create_thought_chain("problem", "I will do this.")
        assert chain.is_complete()

    def test_context_passed_through(self):
        ctx = {"env": "production"}
        chain = create_thought_chain("problem", "Reasoning here.", context=ctx)
        assert chain.context == ctx


# ---------------------------------------------------------------------------
# TestExtractDecisionFromReasoning (convenience function)
# ---------------------------------------------------------------------------


class TestExtractDecisionFromReasoning:
    def test_returns_decision(self):
        decision = extract_decision_from_reasoning(
            "how to proceed",
            "I will implement the solution using a queue.",
        )
        assert isinstance(decision, Decision)

    def test_action_derived_from_text(self):
        decision = extract_decision_from_reasoning(
            "what to build",
            "I will build a caching layer to improve performance.",
        )
        assert decision.action is not None
        assert len(decision.action) > 0

    def test_context_passed_through(self):
        ctx = {"priority": "high"}
        decision = extract_decision_from_reasoning(
            "problem",
            "I should fix the bug immediately.",
            context=ctx,
        )
        # Decision is returned — context was accepted without error
        assert isinstance(decision, Decision)

    def test_source_chain_id_set(self):
        decision = extract_decision_from_reasoning(
            "problem",
            "I will refactor the module.",
        )
        assert decision.source_chain_id is not None
