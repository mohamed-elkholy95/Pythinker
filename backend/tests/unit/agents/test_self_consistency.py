"""Tests for SelfConsistencyChecker — dataclasses, normalization, consistency analysis."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.agents.self_consistency import (
    ClaimConsistency,
    ConsistencyLevel,
    SelfConsistencyChecker,
    SelfConsistencyResult,
    check_self_consistency,
)

# ---------------------------------------------------------------------------
# ClaimConsistency dataclass
# ---------------------------------------------------------------------------


class TestClaimConsistency:
    def test_is_consistent_above_threshold(self):
        c = ClaimConsistency(claim="X", occurrences=3, total_samples=5, consistency_ratio=0.6)
        assert c.is_consistent is True

    def test_is_consistent_at_boundary(self):
        c = ClaimConsistency(claim="X", occurrences=2, total_samples=4, consistency_ratio=0.5)
        assert c.is_consistent is True

    def test_is_not_consistent_below_threshold(self):
        c = ClaimConsistency(claim="X", occurrences=1, total_samples=5, consistency_ratio=0.2)
        assert c.is_consistent is False

    def test_is_strongly_consistent(self):
        c = ClaimConsistency(claim="X", occurrences=4, total_samples=5, consistency_ratio=0.8)
        assert c.is_strongly_consistent is True

    def test_is_not_strongly_consistent(self):
        c = ClaimConsistency(claim="X", occurrences=3, total_samples=5, consistency_ratio=0.6)
        assert c.is_strongly_consistent is False

    def test_variants_stored(self):
        c = ClaimConsistency(
            claim="Paris is the capital",
            occurrences=2,
            total_samples=3,
            consistency_ratio=0.67,
            variants=["Paris is the capital", "The capital is Paris"],
        )
        assert len(c.variants) == 2


# ---------------------------------------------------------------------------
# SelfConsistencyResult dataclass
# ---------------------------------------------------------------------------


class TestSelfConsistencyResult:
    def _make_result(self, **overrides):
        defaults = {
            "query": "test",
            "num_samples": 3,
            "consensus_answer": "answer",
            "confidence_score": 0.9,
            "consistency_level": ConsistencyLevel.STRONG,
            "claim_consistencies": [],
            "all_responses": ["r1", "r2", "r3"],
        }
        defaults.update(overrides)
        return SelfConsistencyResult(**defaults)

    def test_is_high_confidence_true(self):
        r = self._make_result(confidence_score=0.9, consistency_level=ConsistencyLevel.UNANIMOUS)
        assert r.is_high_confidence is True

    def test_is_high_confidence_strong(self):
        r = self._make_result(confidence_score=0.85, consistency_level=ConsistencyLevel.STRONG)
        assert r.is_high_confidence is True

    def test_is_high_confidence_false_low_score(self):
        r = self._make_result(confidence_score=0.5, consistency_level=ConsistencyLevel.STRONG)
        assert r.is_high_confidence is False

    def test_is_high_confidence_false_moderate(self):
        r = self._make_result(confidence_score=0.9, consistency_level=ConsistencyLevel.MODERATE)
        assert r.is_high_confidence is False

    def test_has_conflicts_true(self):
        cc = [ClaimConsistency(claim="A", occurrences=1, total_samples=3, consistency_ratio=0.33)]
        r = self._make_result(claim_consistencies=cc)
        assert r.has_conflicts is True

    def test_has_conflicts_false(self):
        cc = [ClaimConsistency(claim="A", occurrences=3, total_samples=3, consistency_ratio=1.0)]
        r = self._make_result(claim_consistencies=cc)
        assert r.has_conflicts is False

    def test_get_consistent_claims(self):
        cc = [
            ClaimConsistency(claim="A", occurrences=3, total_samples=3, consistency_ratio=1.0),
            ClaimConsistency(claim="B", occurrences=1, total_samples=3, consistency_ratio=0.33),
        ]
        r = self._make_result(claim_consistencies=cc)
        assert r.get_consistent_claims() == ["A"]

    def test_get_inconsistent_claims(self):
        cc = [
            ClaimConsistency(claim="A", occurrences=3, total_samples=3, consistency_ratio=1.0),
            ClaimConsistency(claim="B", occurrences=1, total_samples=3, consistency_ratio=0.33),
        ]
        r = self._make_result(claim_consistencies=cc)
        inconsistent = r.get_inconsistent_claims()
        assert len(inconsistent) == 1
        assert inconsistent[0].claim == "B"

    def test_get_summary_contains_level(self):
        r = self._make_result(
            consistency_level=ConsistencyLevel.STRONG,
            confidence_score=0.85,
            claim_consistencies=[
                ClaimConsistency(claim="A", occurrences=3, total_samples=3, consistency_ratio=1.0),
            ],
        )
        summary = r.get_summary()
        assert "strong" in summary
        assert "0.85" in summary
        assert "1/1" in summary


# ---------------------------------------------------------------------------
# SelfConsistencyChecker — normalize, analyze, levels, confidence
# ---------------------------------------------------------------------------


class TestSelfConsistencyCheckerPureMethods:
    """Tests for pure/sync methods on SelfConsistencyChecker."""

    @pytest.fixture()
    def checker(self):
        llm = MagicMock()
        json_parser = MagicMock()
        return SelfConsistencyChecker(llm, json_parser, num_samples=3)

    # -- num_samples clamping -------------------------------------------
    def test_num_samples_clamped_min(self):
        c = SelfConsistencyChecker(MagicMock(), MagicMock(), num_samples=0)
        assert c.num_samples == 2

    def test_num_samples_clamped_max(self):
        c = SelfConsistencyChecker(MagicMock(), MagicMock(), num_samples=99)
        assert c.num_samples == 5

    def test_num_samples_normal(self):
        c = SelfConsistencyChecker(MagicMock(), MagicMock(), num_samples=4)
        assert c.num_samples == 4

    # -- _normalize_claim ------------------------------------------------
    def test_normalize_claim_lowercases(self, checker):
        assert checker._normalize_claim("The Sky IS Blue") == "sky blue"

    def test_normalize_claim_removes_fillers(self, checker):
        result = checker._normalize_claim("It has been a great achievement")
        # "the", "a", "an", "is", "are", "was", "were", "has", "have", "been" are fillers
        assert "has" not in result.split()
        assert "been" not in result.split()
        assert "a" not in result.split()
        assert "great" in result

    def test_normalize_claim_strips_punctuation(self, checker):
        result = checker._normalize_claim("Paris is the capital of France.")
        assert not result.endswith(".")

    def test_normalize_claim_collapses_whitespace(self, checker):
        result = checker._normalize_claim("  too   much   space  ")
        assert "  " not in result

    # -- _analyze_consistency -------------------------------------------
    def test_analyze_consistency_empty(self, checker):
        assert checker._analyze_consistency([]) == []

    def test_analyze_consistency_single_sample(self, checker):
        result = checker._analyze_consistency([["claim A", "claim B"]])
        assert len(result) == 2
        for cc in result:
            assert cc.consistency_ratio == 1.0

    def test_analyze_consistency_all_agree(self, checker):
        claims = [["Paris is the capital"], ["Paris is the capital"], ["Paris is the capital"]]
        result = checker._analyze_consistency(claims)
        assert len(result) == 1
        assert result[0].occurrences == 3
        assert result[0].consistency_ratio == 1.0

    def test_analyze_consistency_partial(self, checker):
        claims = [["claim A", "claim B"], ["claim A"], ["claim C"]]
        result = checker._analyze_consistency(claims)
        # claim A should appear 2 times
        claim_a = next(cc for cc in result if "claim" in cc.claim.lower() and "a" in cc.claim.lower())
        assert claim_a.occurrences == 2

    def test_analyze_consistency_sorted_by_ratio(self, checker):
        claims = [["rare"], ["common", "rare"], ["common"]]
        result = checker._analyze_consistency(claims)
        # First result should have highest ratio
        assert result[0].consistency_ratio >= result[-1].consistency_ratio

    # -- _calculate_consistency_level ------------------------------------
    def test_consistency_level_unanimous(self, checker):
        ccs = [ClaimConsistency(claim="A", occurrences=3, total_samples=3, consistency_ratio=1.0)]
        assert checker._calculate_consistency_level(ccs) == ConsistencyLevel.UNANIMOUS

    def test_consistency_level_strong(self, checker):
        ccs = [
            ClaimConsistency(claim="A", occurrences=3, total_samples=3, consistency_ratio=1.0),
            ClaimConsistency(claim="B", occurrences=2, total_samples=3, consistency_ratio=0.67),
        ]
        level = checker._calculate_consistency_level(ccs)
        assert level == ConsistencyLevel.STRONG

    def test_consistency_level_moderate(self, checker):
        ccs = [
            ClaimConsistency(claim="A", occurrences=2, total_samples=3, consistency_ratio=0.67),
            ClaimConsistency(claim="B", occurrences=1, total_samples=3, consistency_ratio=0.33),
        ]
        level = checker._calculate_consistency_level(ccs)
        assert level == ConsistencyLevel.MODERATE

    def test_consistency_level_weak(self, checker):
        ccs = [
            ClaimConsistency(claim="A", occurrences=1, total_samples=3, consistency_ratio=0.33),
        ]
        level = checker._calculate_consistency_level(ccs)
        assert level == ConsistencyLevel.WEAK

    def test_consistency_level_conflicting(self, checker):
        ccs = [
            ClaimConsistency(claim="A", occurrences=1, total_samples=5, consistency_ratio=0.2),
            ClaimConsistency(claim="B", occurrences=1, total_samples=5, consistency_ratio=0.2),
        ]
        level = checker._calculate_consistency_level(ccs)
        assert level == ConsistencyLevel.CONFLICTING

    def test_consistency_level_empty(self, checker):
        assert checker._calculate_consistency_level([]) == ConsistencyLevel.WEAK

    # -- _calculate_confidence -------------------------------------------
    def test_confidence_empty(self, checker):
        assert checker._calculate_confidence([], ConsistencyLevel.WEAK) == 0.5

    def test_confidence_unanimous_boost(self, checker):
        ccs = [ClaimConsistency(claim="A", occurrences=3, total_samples=3, consistency_ratio=1.0)]
        conf = checker._calculate_confidence(ccs, ConsistencyLevel.UNANIMOUS)
        assert conf > 1.0 - 0.01  # 1.0 + 0.2 clamped to 1.0

    def test_confidence_conflicting_penalty(self, checker):
        ccs = [ClaimConsistency(claim="A", occurrences=1, total_samples=5, consistency_ratio=0.2)]
        conf = checker._calculate_confidence(ccs, ConsistencyLevel.CONFLICTING)
        assert conf == 0.0  # 0.2 - 0.2 = 0.0

    def test_confidence_clamped_to_unit_range(self, checker):
        ccs = [ClaimConsistency(claim="A", occurrences=3, total_samples=3, consistency_ratio=1.0)]
        conf = checker._calculate_confidence(ccs, ConsistencyLevel.UNANIMOUS)
        assert 0.0 <= conf <= 1.0

    # -- stats -----------------------------------------------------------
    def test_initial_stats(self, checker):
        stats = checker.get_stats()
        assert stats["total_checks"] == 0
        assert stats["high_confidence_rate"] == "N/A"

    def test_reset_stats(self, checker):
        checker._stats["total_checks"] = 10
        checker.reset_stats()
        assert checker.get_stats()["total_checks"] == 0


# --- Fallback result -------------------------------------------------------


class TestSelfConsistencyCheckerFallback:
    def test_fallback_with_responses(self):
        checker = SelfConsistencyChecker(MagicMock(), MagicMock())
        import time

        result = checker._create_fallback_result("q", ["resp1"], time.time())
        assert result.consensus_answer == "resp1"
        assert result.confidence_score == 0.5
        assert result.consistency_level == ConsistencyLevel.WEAK

    def test_fallback_empty_responses(self):
        checker = SelfConsistencyChecker(MagicMock(), MagicMock())
        import time

        result = checker._create_fallback_result("q", [], time.time())
        assert result.consensus_answer == ""
        assert result.num_samples == 0


# --- Async check_consistency -----------------------------------------------


class TestSelfConsistencyCheckerAsync:
    @pytest.fixture()
    def mock_llm(self):
        return AsyncMock()

    @pytest.fixture()
    def mock_json_parser(self):
        return AsyncMock()

    @pytest.mark.asyncio()
    async def test_check_consistency_not_enough_samples(self, mock_llm, mock_json_parser):
        """When LLM returns only empty responses, should fallback."""
        mock_llm.ask = AsyncMock(return_value={"content": ""})
        checker = SelfConsistencyChecker(mock_llm, mock_json_parser, num_samples=3)
        result = await checker.check_consistency("test query")
        assert result.confidence_score == 0.5
        assert result.consistency_level == ConsistencyLevel.WEAK

    @pytest.mark.asyncio()
    async def test_check_consistency_all_agree(self, mock_llm, mock_json_parser):
        """When all samples return same claims, confidence should be high."""
        mock_llm.ask = AsyncMock(
            side_effect=[
                {"content": "Paris is the capital of France."},
                {"content": "Paris is the capital of France."},
                {"content": "Paris is the capital of France."},
                # Claim extraction calls
                {"content": '{"claims": ["Paris is the capital of France"], "main_answer": "Paris"}'},
                {"content": '{"claims": ["Paris is the capital of France"], "main_answer": "Paris"}'},
                {"content": '{"claims": ["Paris is the capital of France"], "main_answer": "Paris"}'},
                # Consolidation call
                {"content": "Paris is the capital of France."},
            ],
        )
        mock_json_parser.parse = AsyncMock(
            return_value={"claims": ["Paris is the capital of France"], "main_answer": "Paris"},
        )
        checker = SelfConsistencyChecker(mock_llm, mock_json_parser, num_samples=3)
        result = await checker.check_consistency("What is the capital of France?")
        assert result.confidence_score >= 0.8
        assert result.num_samples == 3

    @pytest.mark.asyncio()
    async def test_check_with_context(self, mock_llm, mock_json_parser):
        """Context should be included in messages."""
        calls = []

        async def capture_ask(**kwargs):
            calls.append(kwargs)
            return {"content": "response"}

        mock_llm.ask = capture_ask
        mock_json_parser.parse = AsyncMock(return_value={"claims": [], "main_answer": ""})
        checker = SelfConsistencyChecker(mock_llm, mock_json_parser, num_samples=2, consolidate_output=False)
        await checker.check_consistency("query", context="some context")
        # First calls are sample generation, which should include context
        first_call = calls[0]
        user_msg = first_call["messages"][-1]["content"]
        assert "some context" in user_msg

    @pytest.mark.asyncio()
    async def test_check_with_system_prompt(self, mock_llm, mock_json_parser):
        """System prompt should be included."""
        calls = []

        async def capture_ask(**kwargs):
            calls.append(kwargs)
            return {"content": "response"}

        mock_llm.ask = capture_ask
        mock_json_parser.parse = AsyncMock(return_value={"claims": [], "main_answer": ""})
        checker = SelfConsistencyChecker(mock_llm, mock_json_parser, num_samples=2, consolidate_output=False)
        await checker.check_consistency("query", system_prompt="Be helpful")
        first_call = calls[0]
        assert first_call["messages"][0]["role"] == "system"
        assert first_call["messages"][0]["content"] == "Be helpful"


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


class TestConvenienceFunction:
    @pytest.mark.asyncio()
    async def test_check_self_consistency_returns_result(self):
        llm = AsyncMock()
        llm.ask = AsyncMock(return_value={"content": ""})
        jp = AsyncMock()
        result = await check_self_consistency(llm, jp, "query", num_samples=2)
        assert isinstance(result, SelfConsistencyResult)
