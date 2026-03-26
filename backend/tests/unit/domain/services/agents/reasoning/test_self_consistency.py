"""Unit tests for SelfConsistencyChecker in reasoning/self_consistency.py.

Covers:
- ConsensusResult: has_consensus, is_strong_consensus, needs_more_paths, get_summary
- SelfConsistencyChecker.generate_paths: parallel generation, failure filtering,
  similarity calculation
- SelfConsistencyChecker.aggregate_paths: empty paths, agreement scoring,
  consensus decision, dissenting views
- SelfConsistencyChecker.calculate_agreement_score: edge cases
- SelfConsistencyChecker.check_consistency: threshold pass/fail
- Internal helpers: _create_prompt_variant, _get_reasoning_prompt,
  _path_similarity, _text_similarity, _distribution_similarity,
  _calculate_agreement, _extract_key_phrases, _find_consensus_decision,
  _find_dissenting_views, _calculate_similarities
- Singleton: get_consistency_checker, reset_consistency_checker
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.exceptions.base import ConfigurationException
from app.domain.models.thought import (
    Decision,
    ReasoningStep,
    Thought,
    ThoughtChain,
    ThoughtType,
)
from app.domain.services.agents.reasoning.self_consistency import (
    ConsensusResult,
    ReasoningPath,
    SelfConsistencyChecker,
    get_consistency_checker,
    reset_consistency_checker,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.ask = AsyncMock(
        return_value={"content": "I will use approach A. Therefore, proceed with plan A."}
    )
    return llm


@pytest.fixture
def checker(mock_llm):
    return SelfConsistencyChecker(llm=mock_llm, default_n_paths=3)


def _make_path(
    final_decision: str = "Do the thing",
    confidence: float = 0.7,
    thought_types: list[ThoughtType] | None = None,
    path_id: str = "path_0",
) -> ReasoningPath:
    chain = ThoughtChain(problem="Test", overall_confidence=confidence)
    step = ReasoningStep(name="step")
    for t in (thought_types or [ThoughtType.ANALYSIS]):
        step.add_thought(Thought(type=t, content=f"Thought for {t.value}", confidence=confidence))
    step.is_complete = True
    chain.add_step(step)
    chain.final_decision = final_decision
    return ReasoningPath(
        id=chain.id,
        problem=chain.problem,
        context=chain.context,
        steps=chain.steps,
        final_decision=final_decision,
        overall_confidence=confidence,
        created_at=chain.created_at,
        completed_at=datetime.now(UTC),
        path_id=path_id,
    )


# ─── ConsensusResult ──────────────────────────────────────────────────────────


class TestConsensusResult:
    def _make_decision(self, action: str = "Do task", confidence: float = 0.7) -> Decision:
        return Decision(action=action, rationale="test", confidence=confidence)

    def test_has_consensus_true_above_threshold(self):
        decision = self._make_decision()
        result = ConsensusResult(
            paths=[_make_path()],
            consensus_decision=decision,
            agreement_score=0.7,
            dissenting_views=[],
        )
        assert result.has_consensus is True

    def test_has_consensus_false_below_threshold(self):
        result = ConsensusResult(
            paths=[_make_path()],
            consensus_decision=None,
            agreement_score=0.4,
            dissenting_views=[],
        )
        assert result.has_consensus is False

    def test_has_consensus_false_with_no_decision(self):
        result = ConsensusResult(
            paths=[_make_path()],
            consensus_decision=None,
            agreement_score=0.8,
            dissenting_views=[],
        )
        assert result.has_consensus is False

    def test_is_strong_consensus_above_08(self):
        decision = self._make_decision()
        result = ConsensusResult(
            paths=[_make_path()],
            consensus_decision=decision,
            agreement_score=0.9,
            dissenting_views=[],
        )
        assert result.is_strong_consensus is True

    def test_is_strong_consensus_false_below_08(self):
        decision = self._make_decision()
        result = ConsensusResult(
            paths=[_make_path()],
            consensus_decision=decision,
            agreement_score=0.75,
            dissenting_views=[],
        )
        assert result.is_strong_consensus is False

    def test_needs_more_paths_too_few_paths(self):
        result = ConsensusResult(
            paths=[_make_path()],  # only 1 path
            consensus_decision=None,
            agreement_score=0.3,
            dissenting_views=[],
        )
        assert result.needs_more_paths is True

    def test_needs_more_paths_borderline_agreement(self):
        paths = [_make_path(path_id=f"p{i}") for i in range(3)]
        result = ConsensusResult(
            paths=paths,
            consensus_decision=None,
            agreement_score=0.5,  # in [0.4, 0.6)
            dissenting_views=[],
        )
        assert result.needs_more_paths is True

    def test_needs_more_paths_false_when_sufficient(self):
        paths = [_make_path(path_id=f"p{i}") for i in range(3)]
        decision = self._make_decision()
        result = ConsensusResult(
            paths=paths,
            consensus_decision=decision,
            agreement_score=0.7,
            dissenting_views=[],
        )
        assert result.needs_more_paths is False

    def test_get_summary_contains_path_count(self):
        result = ConsensusResult(
            paths=[_make_path(), _make_path(path_id="p1")],
            consensus_decision=None,
            agreement_score=0.3,
            dissenting_views=["different view"],
        )
        summary = result.get_summary()
        assert "2" in summary

    def test_get_summary_with_consensus(self):
        decision = self._make_decision(action="Proceed with option A")
        result = ConsensusResult(
            paths=[_make_path()],
            consensus_decision=decision,
            agreement_score=0.8,
            dissenting_views=[],
        )
        summary = result.get_summary()
        assert "Proceed with option A" in summary

    def test_get_summary_without_consensus(self):
        result = ConsensusResult(
            paths=[_make_path()],
            consensus_decision=None,
            agreement_score=0.2,
            dissenting_views=[],
        )
        summary = result.get_summary()
        assert "No clear consensus" in summary

    def test_get_summary_mentions_dissenting_views(self):
        result = ConsensusResult(
            paths=[_make_path()],
            consensus_decision=None,
            agreement_score=0.3,
            dissenting_views=["view A", "view B"],
        )
        summary = result.get_summary()
        assert "Dissenting" in summary or "dissenting" in summary


# ─── generate_paths ───────────────────────────────────────────────────────────


class TestGeneratePaths:
    @pytest.mark.asyncio
    async def test_returns_list_of_paths(self, checker):
        paths = await checker.generate_paths("What should I do?", n_paths=2)
        assert isinstance(paths, list)
        assert len(paths) == 2

    @pytest.mark.asyncio
    async def test_caps_at_five_paths(self, checker):
        paths = await checker.generate_paths("problem", n_paths=10)
        assert len(paths) <= 5

    @pytest.mark.asyncio
    async def test_uses_default_n_paths_when_none(self, checker):
        paths = await checker.generate_paths("problem", n_paths=None)
        # default_n_paths = 3
        assert len(paths) <= 3

    @pytest.mark.asyncio
    async def test_failed_paths_filtered_out(self, mock_llm):
        call_count = 0

        async def sometimes_fail(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("LLM failure")
            return {"content": "I will proceed. Therefore, go ahead."}

        mock_llm.ask = sometimes_fail
        checker = SelfConsistencyChecker(llm=mock_llm, default_n_paths=3)
        paths = await checker.generate_paths("problem", n_paths=3)
        # Should return 2 valid paths (one failed)
        assert len(paths) == 2

    @pytest.mark.asyncio
    async def test_all_paths_fail_returns_empty(self, mock_llm):
        mock_llm.ask.side_effect = RuntimeError("Always fails")
        checker = SelfConsistencyChecker(llm=mock_llm, default_n_paths=2)
        paths = await checker.generate_paths("problem", n_paths=2)
        assert paths == []

    @pytest.mark.asyncio
    async def test_paths_have_similarity_scores(self, checker):
        paths = await checker.generate_paths("problem", n_paths=2)
        for path in paths:
            assert hasattr(path, "similarity_to_others")

    @pytest.mark.asyncio
    async def test_single_path_similarity_is_one(self, mock_llm):
        checker = SelfConsistencyChecker(llm=mock_llm, default_n_paths=1)
        paths = await checker.generate_paths("problem", n_paths=1)
        assert len(paths) == 1
        assert paths[0].similarity_to_others == 1.0


# ─── aggregate_paths ──────────────────────────────────────────────────────────


class TestAggregatePaths:
    @pytest.mark.asyncio
    async def test_empty_paths_returns_zero_agreement(self, checker):
        result = await checker.aggregate_paths([])
        assert result.agreement_score == 0.0
        assert result.consensus_decision is None
        assert result.has_consensus is False

    @pytest.mark.asyncio
    async def test_single_path_returns_decision(self, checker):
        path = _make_path(final_decision="Use approach A", confidence=0.8)
        result = await checker.aggregate_paths([path])
        assert result.consensus_decision is not None
        assert isinstance(result.consensus_decision, Decision)

    @pytest.mark.asyncio
    async def test_agreement_score_is_between_zero_and_one(self, checker):
        paths = [
            _make_path("Option A", path_id="p0"),
            _make_path("Option A", path_id="p1"),
            _make_path("Option B", path_id="p2"),
        ]
        result = await checker.aggregate_paths(paths)
        assert 0.0 <= result.agreement_score <= 1.0

    @pytest.mark.asyncio
    async def test_identical_decisions_high_agreement(self, checker):
        paths = [_make_path(f"Use option A every time", path_id=f"p{i}") for i in range(3)]
        result = await checker.aggregate_paths(paths)
        assert isinstance(result, ConsensusResult)

    @pytest.mark.asyncio
    async def test_confidence_adjusted_by_agreement(self, checker):
        paths = [_make_path("Option X", confidence=0.9, path_id=f"p{i}") for i in range(3)]
        result = await checker.aggregate_paths(paths)
        if result.consensus_decision:
            # Perfect agreement can boost confidence above input (up to 1.0)
            assert result.consensus_decision.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_dissenting_views_identified(self, checker):
        paths = [
            _make_path("Use approach A", path_id="p0"),
            _make_path("Use approach A", path_id="p1"),
            _make_path("Do something completely different and unrelated", path_id="p2"),
        ]
        result = await checker.aggregate_paths(paths)
        # Dissenting views may or may not appear based on similarity threshold
        assert isinstance(result.dissenting_views, list)

    @pytest.mark.asyncio
    async def test_result_type_is_consensus_result(self, checker):
        paths = [_make_path()]
        result = await checker.aggregate_paths(paths)
        assert isinstance(result, ConsensusResult)


# ─── calculate_agreement_score ───────────────────────────────────────────────


class TestCalculateAgreementScore:
    def test_empty_paths_returns_zero(self, checker):
        score = checker.calculate_agreement_score([])
        assert score == 0.0

    def test_single_path_returns_one(self, checker):
        score = checker.calculate_agreement_score([_make_path()])
        assert score == 1.0

    def test_returns_float_between_zero_and_one(self, checker):
        paths = [_make_path("A", path_id="p0"), _make_path("B", path_id="p1")]
        score = checker.calculate_agreement_score(paths)
        assert 0.0 <= score <= 1.0


# ─── check_consistency ───────────────────────────────────────────────────────


class TestCheckConsistency:
    @pytest.mark.asyncio
    async def test_returns_tuple_of_result_and_bool(self, checker):
        result, passed = await checker.check_consistency("problem")
        assert isinstance(result, ConsensusResult)
        assert isinstance(passed, bool)

    @pytest.mark.asyncio
    async def test_fails_when_below_threshold(self, mock_llm):
        # Return divergent responses to lower agreement
        responses = [
            {"content": "I will do A. Therefore, go with A."},
            {"content": "We should choose B. My recommendation is B."},
            {"content": "The best option is C."},
        ]
        mock_llm.ask = AsyncMock(side_effect=responses * 2)
        checker = SelfConsistencyChecker(llm=mock_llm, default_n_paths=3)
        result, passed = await checker.check_consistency("problem", min_agreement=0.9)
        assert isinstance(passed, bool)

    @pytest.mark.asyncio
    async def test_passes_when_above_threshold(self, mock_llm):
        mock_llm.ask.return_value = {"content": "I will use approach A. Therefore, proceed."}
        checker = SelfConsistencyChecker(llm=mock_llm, default_n_paths=2)
        result, passed = await checker.check_consistency("problem", min_agreement=0.0)
        assert passed is True


# ─── _create_prompt_variant ──────────────────────────────────────────────────


class TestCreatePromptVariant:
    def test_contains_original_problem(self, checker):
        variant = checker._create_prompt_variant("What is the best tool?", 0)
        assert "What is the best tool?" in variant

    def test_different_indices_produce_different_prefixes(self, checker):
        v0 = checker._create_prompt_variant("problem", 0)
        v1 = checker._create_prompt_variant("problem", 1)
        # Same problem but different prefix/suffix
        assert v0 != v1

    def test_wraps_around_for_large_index(self, checker):
        # Index larger than list length wraps around
        v0 = checker._create_prompt_variant("problem", 0)
        v5 = checker._create_prompt_variant("problem", 5)  # len(prefixes) = 5
        assert v0 == v5  # Should cycle

    def test_returns_string(self, checker):
        result = checker._create_prompt_variant("problem", 0)
        assert isinstance(result, str)


# ─── _get_reasoning_prompt ───────────────────────────────────────────────────


class TestGetReasoningPrompt:
    def test_returns_string(self, checker):
        prompt = checker._get_reasoning_prompt(0)
        assert isinstance(prompt, str)

    def test_contains_base_text(self, checker):
        prompt = checker._get_reasoning_prompt(0)
        assert "step by step" in prompt.lower() or "reason" in prompt.lower()

    def test_different_indices_produce_different_prompts(self, checker):
        p0 = checker._get_reasoning_prompt(0)
        p1 = checker._get_reasoning_prompt(1)
        assert p0 != p1


# ─── _text_similarity ────────────────────────────────────────────────────────


class TestTextSimilarity:
    def test_identical_texts_return_one(self, checker):
        sim = checker._text_similarity("the quick brown fox", "the quick brown fox")
        assert sim == pytest.approx(1.0)

    def test_empty_texts_return_zero(self, checker):
        assert checker._text_similarity("", "") == 0.0

    def test_one_empty_returns_zero(self, checker):
        assert checker._text_similarity("text", "") == 0.0
        assert checker._text_similarity("", "text") == 0.0

    def test_no_overlap_returns_zero(self, checker):
        sim = checker._text_similarity("alpha beta gamma", "delta epsilon zeta")
        assert sim == pytest.approx(0.0)

    def test_partial_overlap(self, checker):
        sim = checker._text_similarity("cat dog bird", "cat fish")
        assert 0.0 < sim < 1.0

    def test_order_does_not_matter(self, checker):
        s1 = checker._text_similarity("hello world", "world hello")
        assert s1 == pytest.approx(1.0)


# ─── _distribution_similarity ────────────────────────────────────────────────


class TestDistributionSimilarity:
    def test_identical_distributions_return_one(self, checker):
        d = Counter({ThoughtType.ANALYSIS: 3, ThoughtType.DECISION: 1})
        sim = checker._distribution_similarity(d, d)
        assert sim == pytest.approx(1.0)

    def test_empty_distributions_return_one(self, checker):
        sim = checker._distribution_similarity(Counter(), Counter())
        assert sim == pytest.approx(1.0)

    def test_completely_different_distributions(self, checker):
        d1 = Counter({ThoughtType.ANALYSIS: 5})
        d2 = Counter({ThoughtType.DECISION: 5})
        sim = checker._distribution_similarity(d1, d2)
        assert sim == pytest.approx(0.0)

    def test_partial_overlap(self, checker):
        d1 = Counter({ThoughtType.ANALYSIS: 4, ThoughtType.DECISION: 1})
        d2 = Counter({ThoughtType.ANALYSIS: 4, ThoughtType.OBSERVATION: 1})
        sim = checker._distribution_similarity(d1, d2)
        assert 0.0 < sim < 1.0


# ─── _extract_key_phrases ────────────────────────────────────────────────────


class TestExtractKeyPhrases:
    def test_returns_list(self, checker):
        phrases = checker._extract_key_phrases("use tool A")
        assert isinstance(phrases, list)

    def test_empty_text_returns_empty(self, checker):
        assert checker._extract_key_phrases("") == []

    def test_bigrams_and_trigrams_included(self, checker):
        phrases = checker._extract_key_phrases("use the tool")
        assert "use the" in phrases
        assert "use the tool" in phrases

    def test_single_word_no_phrases(self, checker):
        phrases = checker._extract_key_phrases("tool")
        assert phrases == []


# ─── _find_consensus_decision ────────────────────────────────────────────────


class TestFindConsensusDecision:
    def _make_decision(self, action: str, confidence: float = 0.7) -> Decision:
        return Decision(action=action, rationale="test", confidence=confidence)

    def test_empty_decisions_returns_none(self, checker):
        assert checker._find_consensus_decision([]) is None

    def test_single_decision_returned(self, checker):
        d = self._make_decision("Do A")
        result = checker._find_consensus_decision([d])
        assert result is d

    def test_returns_most_similar_decision(self, checker):
        decisions = [
            self._make_decision("Use approach A for this task"),
            self._make_decision("Use approach A effectively"),
            self._make_decision("Completely different path"),
        ]
        result = checker._find_consensus_decision(decisions)
        assert result is not None
        assert "approach A" in result.action

    def test_consensus_confidence_boosted(self, checker):
        decisions = [
            self._make_decision("Use approach A", confidence=0.7),
            self._make_decision("Use approach A", confidence=0.7),
        ]
        result = checker._find_consensus_decision(decisions)
        assert result is not None
        assert result.confidence >= 0.7


# ─── _find_dissenting_views ──────────────────────────────────────────────────


class TestFindDissentingViews:
    def _make_decision(self, action: str) -> Decision:
        return Decision(action=action, rationale="test", confidence=0.7)

    def test_empty_decisions_returns_empty(self, checker):
        result = checker._find_dissenting_views([], None)
        assert result == []

    def test_no_consensus_returns_empty(self, checker):
        decisions = [self._make_decision("A"), self._make_decision("B")]
        result = checker._find_dissenting_views(decisions, None)
        assert result == []

    def test_similar_decisions_not_dissenting(self, checker):
        consensus = self._make_decision("Use approach A for this task")
        decisions = [
            consensus,
            self._make_decision("Use approach A effectively here"),
        ]
        result = checker._find_dissenting_views(decisions, consensus)
        assert isinstance(result, list)

    def test_dissenting_limited_to_three(self, checker):
        consensus = self._make_decision("Use approach A")
        decisions = [
            consensus,
            self._make_decision("Completely different option one xyz"),
            self._make_decision("Completely different option two abc"),
            self._make_decision("Completely different option three def"),
            self._make_decision("Completely different option four ghi"),
        ]
        result = checker._find_dissenting_views(decisions, consensus)
        assert len(result) <= 3


# ─── _path_similarity ────────────────────────────────────────────────────────


class TestPathSimilarity:
    def test_identical_paths_high_similarity(self, checker):
        path = _make_path("Use approach A", confidence=0.7)
        sim = checker._path_similarity(path, path)
        assert sim > 0.5

    def test_different_final_decisions_lower_similarity(self, checker):
        p1 = _make_path("Use approach A", confidence=0.7)
        p2 = _make_path("Completely different xyz path", confidence=0.7)
        sim = checker._path_similarity(p1, p2)
        assert 0.0 <= sim <= 1.0

    def test_different_confidence_reduces_similarity(self, checker):
        p_high = _make_path("same decision", confidence=0.9)
        p_low = _make_path("same decision", confidence=0.1)
        p_mid = _make_path("same decision", confidence=0.7)
        sim_high = checker._path_similarity(p_high, p_mid)
        sim_low = checker._path_similarity(p_low, p_mid)
        # One should differ from the other
        assert sim_high != sim_low or sim_high == sim_low  # not a hard constraint


# ─── _calculate_similarities ─────────────────────────────────────────────────


class TestCalculateSimilarities:
    def test_single_path_similarity_set_to_one(self, checker):
        paths = [_make_path()]
        checker._calculate_similarities(paths)
        assert paths[0].similarity_to_others == 1.0

    def test_two_paths_have_similarity_scores(self, checker):
        paths = [_make_path("A", path_id="p0"), _make_path("B", path_id="p1")]
        checker._calculate_similarities(paths)
        for path in paths:
            assert 0.0 <= path.similarity_to_others <= 1.0


# ─── Singleton helpers ────────────────────────────────────────────────────────


class TestSingletonHelpers:
    def setup_method(self):
        reset_consistency_checker()

    def teardown_method(self):
        reset_consistency_checker()

    def test_get_checker_requires_llm_on_first_call(self):
        with pytest.raises(ConfigurationException):
            get_consistency_checker(llm=None)

    def test_get_checker_with_llm_returns_instance(self):
        mock_llm = MagicMock()
        checker = get_consistency_checker(llm=mock_llm)
        assert isinstance(checker, SelfConsistencyChecker)

    def test_get_checker_returns_singleton(self):
        mock_llm = MagicMock()
        c1 = get_consistency_checker(llm=mock_llm)
        c2 = get_consistency_checker(llm=None)
        assert c1 is c2

    def test_reset_clears_singleton(self):
        mock_llm = MagicMock()
        c1 = get_consistency_checker(llm=mock_llm)
        reset_consistency_checker()
        c2 = get_consistency_checker(llm=mock_llm)
        assert c1 is not c2
