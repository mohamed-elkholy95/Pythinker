"""Tests for ConfidenceCalibrator and related models.

Covers calibration logic, level thresholds, recommendation rules,
factor calculations, and historical accuracy tracking.
"""

import pytest

from app.domain.models.thought import (
    Decision,
    ReasoningStep,
    Thought,
    ThoughtChain,
    ThoughtType,
)
from app.domain.services.agents.reasoning.confidence import (
    ActionRecommendation,
    CalibratedConfidence,
    CalibrationFactors,
    ConfidenceCalibrator,
    ConfidenceLevel,
    get_confidence_calibrator,
    reset_calibrator,
)


@pytest.fixture
def calibrator():
    return ConfidenceCalibrator()


@pytest.fixture
def calibrator_historical():
    return ConfidenceCalibrator(enable_historical_calibration=True)


def _make_decision(
    confidence=0.7,
    action="Execute task",
    rationale="Based on analysis",
    risks=None,
    alternatives=None,
    prerequisites=None,
):
    return Decision(
        action=action,
        rationale=rationale,
        confidence=confidence,
        risks=risks or [],
        alternatives_considered=alternatives or [],
        prerequisites=prerequisites or [],
    )


def _make_chain(thoughts=None, steps_count=0, uncertainties=0):
    chain = ThoughtChain(problem="Test problem")
    for i in range(steps_count):
        step = ReasoningStep(name=f"Step {i + 1}")
        if thoughts:
            for t in thoughts:
                step.add_thought(t)
        chain.add_step(step)
    for _ in range(uncertainties):
        step = ReasoningStep(name="Uncertainty step")
        step.add_thought(Thought(type=ThoughtType.UNCERTAINTY, content="Uncertain about X", confidence=0.3))
        chain.add_step(step)
    return chain


# ─────────────────────────────────────────────────────────────
# CalibratedConfidence dataclass
# ─────────────────────────────────────────────────────────────


class TestCalibratedConfidence:
    def test_should_proceed(self):
        cc = CalibratedConfidence(
            raw_confidence=0.9,
            calibrated_confidence=0.9,
            level=ConfidenceLevel.HIGH,
            recommendation=ActionRecommendation.PROCEED,
            factors=CalibrationFactors(0.8, 0.8, 0.0, 0.0, 0.8),
            supporting_reasons=[],
            risk_factors=[],
        )
        assert cc.should_proceed() is True
        assert cc.needs_verification() is False
        assert cc.needs_user_input() is False

    def test_needs_verification(self):
        cc = CalibratedConfidence(
            raw_confidence=0.6,
            calibrated_confidence=0.6,
            level=ConfidenceLevel.MEDIUM,
            recommendation=ActionRecommendation.VERIFY,
            factors=CalibrationFactors(0.5, 0.5, 0.1, 0.0, 0.5),
            supporting_reasons=[],
            risk_factors=[],
        )
        assert cc.should_proceed() is False
        assert cc.needs_verification() is True
        assert cc.needs_user_input() is False

    def test_needs_user_input(self):
        cc = CalibratedConfidence(
            raw_confidence=0.3,
            calibrated_confidence=0.3,
            level=ConfidenceLevel.LOW,
            recommendation=ActionRecommendation.ASK_USER,
            factors=CalibrationFactors(0.3, 0.3, 0.3, -0.1, 0.3),
            supporting_reasons=[],
            risk_factors=[],
        )
        assert cc.should_proceed() is False
        assert cc.needs_verification() is False
        assert cc.needs_user_input() is True


# ─────────────────────────────────────────────────────────────
# Confidence level thresholds
# ─────────────────────────────────────────────────────────────


class TestConfidenceLevel:
    def test_high_threshold(self, calibrator):
        assert calibrator._get_confidence_level(0.9) == ConfidenceLevel.HIGH
        assert calibrator._get_confidence_level(0.8) == ConfidenceLevel.HIGH

    def test_medium_threshold(self, calibrator):
        assert calibrator._get_confidence_level(0.7) == ConfidenceLevel.MEDIUM
        assert calibrator._get_confidence_level(0.5) == ConfidenceLevel.MEDIUM

    def test_low_threshold(self, calibrator):
        assert calibrator._get_confidence_level(0.4) == ConfidenceLevel.LOW
        assert calibrator._get_confidence_level(0.0) == ConfidenceLevel.LOW

    def test_boundary_values(self, calibrator):
        assert calibrator._get_confidence_level(0.8) == ConfidenceLevel.HIGH
        assert calibrator._get_confidence_level(0.79) == ConfidenceLevel.MEDIUM
        assert calibrator._get_confidence_level(0.5) == ConfidenceLevel.MEDIUM
        assert calibrator._get_confidence_level(0.49) == ConfidenceLevel.LOW


# ─────────────────────────────────────────────────────────────
# Recommendation logic
# ─────────────────────────────────────────────────────────────


class TestRecommendation:
    def test_high_no_risks_proceeds(self, calibrator):
        decision = _make_decision(risks=[])
        rec = calibrator._get_recommendation(ConfidenceLevel.HIGH, decision)
        assert rec == ActionRecommendation.PROCEED

    def test_high_with_risks_verifies(self, calibrator):
        decision = _make_decision(risks=["data loss", "timeout"])
        rec = calibrator._get_recommendation(ConfidenceLevel.HIGH, decision)
        assert rec == ActionRecommendation.VERIFY

    def test_high_single_risk_proceeds(self, calibrator):
        decision = _make_decision(risks=["minor risk"])
        rec = calibrator._get_recommendation(ConfidenceLevel.HIGH, decision)
        assert rec == ActionRecommendation.PROCEED

    def test_medium_verifies(self, calibrator):
        decision = _make_decision()
        rec = calibrator._get_recommendation(ConfidenceLevel.MEDIUM, decision)
        assert rec == ActionRecommendation.VERIFY

    def test_low_asks_user(self, calibrator):
        decision = _make_decision()
        rec = calibrator._get_recommendation(ConfidenceLevel.LOW, decision)
        assert rec == ActionRecommendation.ASK_USER


# ─────────────────────────────────────────────────────────────
# Evidence score calculation
# ─────────────────────────────────────────────────────────────


class TestEvidenceScore:
    def test_base_score(self, calibrator):
        decision = _make_decision()
        score = calibrator._calculate_evidence_score(decision, None)
        assert score == 0.5

    def test_prerequisites_boost(self, calibrator):
        decision = _make_decision(prerequisites=["dep1"])
        score = calibrator._calculate_evidence_score(decision, None)
        assert score > 0.5

    def test_alternatives_boost(self, calibrator):
        decision = _make_decision(alternatives=["alt1", "alt2"])
        score = calibrator._calculate_evidence_score(decision, None)
        assert score > 0.5

    def test_chain_with_evidence(self, calibrator):
        thought = Thought(
            type=ThoughtType.ANALYSIS,
            content="Analyzed the data",
            supporting_evidence=["source1"],
        )
        chain = _make_chain(thoughts=[thought], steps_count=1)
        decision = _make_decision()
        score = calibrator._calculate_evidence_score(decision, chain)
        assert score > 0.5

    def test_chain_without_evidence(self, calibrator):
        thought = Thought(
            type=ThoughtType.ANALYSIS,
            content="Just a guess",
        )
        chain = _make_chain(thoughts=[thought], steps_count=1)
        decision = _make_decision()
        score = calibrator._calculate_evidence_score(decision, chain)
        assert score == 0.5


# ─────────────────────────────────────────────────────────────
# Consistency score calculation
# ─────────────────────────────────────────────────────────────


class TestConsistencyScore:
    def test_no_chain_neutral(self, calibrator):
        assert calibrator._calculate_consistency_score(None) == 0.5

    def test_no_contradictions_high(self, calibrator):
        thought = Thought(type=ThoughtType.ANALYSIS, content="Analysis")
        chain = _make_chain(thoughts=[thought], steps_count=3)
        score = calibrator._calculate_consistency_score(chain)
        assert score >= 0.8

    def test_contradictions_reduce_score(self, calibrator):
        thought = Thought(
            type=ThoughtType.ANALYSIS,
            content="Contradicted",
            contradicting_evidence=["counterpoint"],
        )
        chain = _make_chain(thoughts=[thought], steps_count=1)
        score = calibrator._calculate_consistency_score(chain)
        assert score < 0.8

    def test_few_steps_moderate(self, calibrator):
        thought = Thought(type=ThoughtType.ANALYSIS, content="Simple")
        chain = _make_chain(thoughts=[thought], steps_count=2)
        score = calibrator._calculate_consistency_score(chain)
        assert score == 0.6


# ─────────────────────────────────────────────────────────────
# Uncertainty penalty
# ─────────────────────────────────────────────────────────────


class TestUncertaintyPenalty:
    def test_no_chain_no_penalty(self, calibrator):
        assert calibrator._calculate_uncertainty_penalty(None) == 0.0

    def test_no_uncertainties_no_penalty(self, calibrator):
        chain = ThoughtChain(problem="test")
        step = ReasoningStep(name="Clear step")
        step.add_thought(Thought(type=ThoughtType.ANALYSIS, content="Clear"))
        chain.add_step(step)
        assert calibrator._calculate_uncertainty_penalty(chain) == 0.0

    def test_uncertainties_add_penalty(self, calibrator):
        chain = _make_chain(uncertainties=2)
        penalty = calibrator._calculate_uncertainty_penalty(chain)
        assert penalty > 0.0

    def test_penalty_capped_at_04(self, calibrator):
        chain = _make_chain(uncertainties=10)
        penalty = calibrator._calculate_uncertainty_penalty(chain)
        assert penalty <= 0.4


# ─────────────────────────────────────────────────────────────
# Complexity adjustment
# ─────────────────────────────────────────────────────────────


class TestComplexityAdjustment:
    def test_complex_indicators_reduce(self, calibrator):
        decision = _make_decision(action="Execute multiple complex tasks")
        adj = calibrator._calculate_complexity_adjustment(decision, None)
        assert adj < 0.0

    def test_simple_indicators_increase(self, calibrator):
        decision = _make_decision(action="Run a simple check")
        adj = calibrator._calculate_complexity_adjustment(decision, None)
        assert adj > 0.0

    def test_many_risks_reduce(self, calibrator):
        decision = _make_decision(action="Do task", risks=["r1", "r2", "r3"])
        adj = calibrator._calculate_complexity_adjustment(decision, None)
        assert adj < 0.0

    def test_neutral_task(self, calibrator):
        decision = _make_decision(action="Execute task")
        adj = calibrator._calculate_complexity_adjustment(decision, None)
        assert adj == 0.0


# ─────────────────────────────────────────────────────────────
# Source quality
# ─────────────────────────────────────────────────────────────


class TestSourceQuality:
    def test_high_quality_rationale(self, calibrator):
        decision = _make_decision(rationale="Verified through official docs")
        score = calibrator._calculate_source_quality(decision)
        assert score == 0.9

    def test_low_quality_rationale(self, calibrator):
        decision = _make_decision(rationale="I assume this will work")
        score = calibrator._calculate_source_quality(decision)
        assert score == 0.3

    def test_neutral_rationale(self, calibrator):
        decision = _make_decision(rationale="Based on analysis")
        score = calibrator._calculate_source_quality(decision)
        assert score == 0.6


# ─────────────────────────────────────────────────────────────
# Full calibrate flow
# ─────────────────────────────────────────────────────────────


class TestCalibrateFlow:
    def test_high_confidence_decision(self, calibrator):
        decision = _make_decision(
            confidence=0.9,
            rationale="Verified through official testing",
            alternatives=["alt1"],
            prerequisites=["dep1"],
        )
        result = calibrator.calibrate(decision)
        assert result.calibrated_confidence > 0.7
        assert result.level in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)

    def test_low_confidence_decision(self, calibrator):
        decision = _make_decision(
            confidence=0.2,
            rationale="I guess this might work",
            risks=["data loss", "timeout", "corruption"],
        )
        result = calibrator.calibrate(decision)
        assert result.calibrated_confidence < 0.5
        assert result.level == ConfidenceLevel.LOW

    def test_calibrate_with_chain(self, calibrator):
        thought = Thought(
            type=ThoughtType.ANALYSIS,
            content="Thorough analysis",
            supporting_evidence=["evidence1"],
        )
        chain = _make_chain(thoughts=[thought], steps_count=3)
        decision = _make_decision(confidence=0.75)
        result = calibrator.calibrate(decision, chain=chain)
        assert isinstance(result, CalibratedConfidence)
        assert 0.0 <= result.calibrated_confidence <= 1.0

    def test_calibrated_confidence_clamped(self, calibrator):
        # Very high raw + all positive factors should still be <= 1.0
        decision = _make_decision(
            confidence=0.99,
            rationale="Verified confirmed tested",
            alternatives=["a"],
            prerequisites=["p"],
        )
        result = calibrator.calibrate(decision)
        assert result.calibrated_confidence <= 1.0

    def test_calibrated_confidence_floor(self, calibrator):
        decision = _make_decision(
            confidence=0.01,
            rationale="Unknown guess maybe unclear",
            risks=["r1", "r2", "r3", "r4"],
        )
        chain = _make_chain(uncertainties=5)
        result = calibrator.calibrate(decision, chain=chain)
        assert result.calibrated_confidence >= 0.0


# ─────────────────────────────────────────────────────────────
# calibrate_tool_selection
# ─────────────────────────────────────────────────────────────


class TestCalibrateToolSelection:
    def test_returns_calibrated_confidence(self, calibrator):
        result = calibrator.calibrate_tool_selection(
            tool_name="shell_execute",
            confidence=0.8,
            task_context="Run a simple command",
        )
        assert isinstance(result, CalibratedConfidence)
        assert 0.0 <= result.calibrated_confidence <= 1.0


# ─────────────────────────────────────────────────────────────
# Historical accuracy tracking
# ─────────────────────────────────────────────────────────────


class TestHistoricalAccuracy:
    def test_disabled_by_default(self, calibrator):
        calibrator.update_historical_accuracy("tool_selection", 0.8, True)
        assert calibrator._historical_accuracy == {}

    def test_enabled_tracks_accuracy(self, calibrator_historical):
        calibrator_historical.update_historical_accuracy("tool_selection", 0.8, True)
        calibrator_historical.update_historical_accuracy("tool_selection", 0.8, False)
        assert len(calibrator_historical._historical_accuracy) > 0

    def test_increments_totals(self, calibrator_historical):
        calibrator_historical.update_historical_accuracy("test", 0.7, True)
        calibrator_historical.update_historical_accuracy("test", 0.7, True)
        calibrator_historical.update_historical_accuracy("test", 0.7, False)
        key = "test_7"
        assert calibrator_historical._historical_accuracy[key]["total"] == 3
        assert calibrator_historical._historical_accuracy[key]["correct"] == 2


# ─────────────────────────────────────────────────────────────
# Supporting reasons and risk factors
# ─────────────────────────────────────────────────────────────


class TestSupportingReasons:
    def test_strong_evidence_reason(self, calibrator):
        factors = CalibrationFactors(0.8, 0.8, 0.0, 0.0, 0.8)
        decision = _make_decision(alternatives=["alt1"])
        reasons = calibrator._get_supporting_reasons(factors, decision)
        assert "Strong supporting evidence" in reasons
        assert "Consistent reasoning process" in reasons
        assert any("alternatives" in r.lower() for r in reasons)

    def test_no_reasons_for_weak_factors(self, calibrator):
        factors = CalibrationFactors(0.3, 0.3, 0.3, -0.1, 0.3)
        decision = _make_decision()
        reasons = calibrator._get_supporting_reasons(factors, decision)
        assert len(reasons) == 0


class TestRiskFactors:
    def test_includes_decision_risks(self, calibrator):
        factors = CalibrationFactors(0.5, 0.5, 0.0, 0.0, 0.5)
        decision = _make_decision(risks=["data loss"])
        risks = calibrator._get_risk_factors(factors, decision)
        assert "data loss" in risks

    def test_high_uncertainty_risk(self, calibrator):
        factors = CalibrationFactors(0.5, 0.5, 0.3, 0.0, 0.5)
        decision = _make_decision()
        risks = calibrator._get_risk_factors(factors, decision)
        assert any("uncertainty" in r.lower() for r in risks)

    def test_low_evidence_risk(self, calibrator):
        factors = CalibrationFactors(0.3, 0.5, 0.0, 0.0, 0.5)
        decision = _make_decision()
        risks = calibrator._get_risk_factors(factors, decision)
        assert any("evidence" in r.lower() for r in risks)

    def test_low_consistency_risk(self, calibrator):
        factors = CalibrationFactors(0.5, 0.3, 0.0, 0.0, 0.5)
        decision = _make_decision()
        risks = calibrator._get_risk_factors(factors, decision)
        assert any("inconsistencies" in r.lower() for r in risks)


# ─────────────────────────────────────────────────────────────
# Global singleton functions
# ─────────────────────────────────────────────────────────────


class TestGlobalFunctions:
    def test_get_calibrator_singleton(self):
        reset_calibrator()
        c1 = get_confidence_calibrator()
        c2 = get_confidence_calibrator()
        assert c1 is c2

    def test_reset_calibrator(self):
        reset_calibrator()
        c1 = get_confidence_calibrator()
        reset_calibrator()
        c2 = get_confidence_calibrator()
        assert c1 is not c2
