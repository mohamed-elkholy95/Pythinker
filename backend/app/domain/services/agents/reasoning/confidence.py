"""
Confidence Calibration for agent decisions.

This module provides calibrated confidence scores for decisions
with appropriate action thresholds based on uncertainty.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.domain.models.thought import Decision, ThoughtChain

logger = logging.getLogger(__name__)


class ConfidenceLevel(str, Enum):
    """Confidence levels with action implications."""

    HIGH = "high"  # >0.8: Proceed autonomously
    MEDIUM = "medium"  # 0.5-0.8: Verify before action
    LOW = "low"  # <0.5: Ask user for clarification


class ActionRecommendation(str, Enum):
    """Recommended action based on confidence."""

    PROCEED = "proceed"  # Safe to proceed autonomously
    VERIFY = "verify"  # Should verify before proceeding
    ASK_USER = "ask_user"  # Should ask user for input


@dataclass
class CalibrationFactors:
    """Factors used in confidence calibration."""

    evidence_score: float  # Based on supporting evidence
    consistency_score: float  # Based on reasoning consistency
    uncertainty_penalty: float  # Penalty for acknowledged uncertainties
    complexity_adjustment: float  # Adjustment for task complexity
    source_quality_score: float  # Based on information source quality


@dataclass
class CalibratedConfidence:
    """Result of confidence calibration."""

    raw_confidence: float
    calibrated_confidence: float
    level: ConfidenceLevel
    recommendation: ActionRecommendation
    factors: CalibrationFactors
    supporting_reasons: list[str]
    risk_factors: list[str]

    def should_proceed(self) -> bool:
        """Check if the action should proceed without verification."""
        return self.recommendation == ActionRecommendation.PROCEED

    def needs_verification(self) -> bool:
        """Check if verification is needed."""
        return self.recommendation == ActionRecommendation.VERIFY

    def needs_user_input(self) -> bool:
        """Check if user input is needed."""
        return self.recommendation == ActionRecommendation.ASK_USER


class ConfidenceCalibrator:
    """Calibrator for agent decision confidence.

    Provides calibrated confidence scores that account for:
    - Evidence quality and quantity
    - Reasoning consistency
    - Acknowledged uncertainties
    - Task complexity
    - Historical accuracy (when available)
    """

    # Thresholds for confidence levels
    HIGH_THRESHOLD = 0.8
    MEDIUM_THRESHOLD = 0.5

    # Calibration weights
    EVIDENCE_WEIGHT = 0.25
    CONSISTENCY_WEIGHT = 0.25
    UNCERTAINTY_WEIGHT = 0.2
    COMPLEXITY_WEIGHT = 0.15
    SOURCE_QUALITY_WEIGHT = 0.15

    def __init__(
        self,
        enable_historical_calibration: bool = False,
    ) -> None:
        """Initialize the confidence calibrator.

        Args:
            enable_historical_calibration: Whether to use historical data
        """
        self.enable_historical_calibration = enable_historical_calibration
        self._historical_accuracy: dict[str, float] = {}

    def calibrate(
        self,
        decision: Decision,
        chain: ThoughtChain | None = None,
        context: dict[str, Any] | None = None,
    ) -> CalibratedConfidence:
        """Calibrate confidence for a decision.

        Args:
            decision: The decision to calibrate
            chain: Optional thought chain for reasoning analysis
            context: Optional context for additional factors

        Returns:
            Calibrated confidence with recommendation
        """
        # Calculate individual factors
        evidence_score = self._calculate_evidence_score(decision, chain)
        consistency_score = self._calculate_consistency_score(chain)
        uncertainty_penalty = self._calculate_uncertainty_penalty(chain)
        complexity_adjustment = self._calculate_complexity_adjustment(decision, context)
        source_quality_score = self._calculate_source_quality(decision)

        factors = CalibrationFactors(
            evidence_score=evidence_score,
            consistency_score=consistency_score,
            uncertainty_penalty=uncertainty_penalty,
            complexity_adjustment=complexity_adjustment,
            source_quality_score=source_quality_score,
        )

        # Calculate calibrated confidence
        raw_confidence = decision.confidence
        calibrated = self._compute_calibrated_confidence(raw_confidence, factors)

        # Determine level and recommendation
        level = self._get_confidence_level(calibrated)
        recommendation = self._get_recommendation(level, decision)

        # Gather supporting and risk factors
        supporting = self._get_supporting_reasons(factors, decision)
        risks = self._get_risk_factors(factors, decision)

        result = CalibratedConfidence(
            raw_confidence=raw_confidence,
            calibrated_confidence=calibrated,
            level=level,
            recommendation=recommendation,
            factors=factors,
            supporting_reasons=supporting,
            risk_factors=risks,
        )

        logger.debug(
            f"Calibrated confidence: {raw_confidence:.2f} -> {calibrated:.2f} "
            f"(level={level.value}, recommendation={recommendation.value})"
        )

        return result

    def calibrate_tool_selection(
        self,
        tool_name: str,
        confidence: float,
        task_context: str,
    ) -> CalibratedConfidence:
        """Calibrate confidence for tool selection decisions.

        Args:
            tool_name: The selected tool
            confidence: Raw confidence in the selection
            task_context: Description of the task

        Returns:
            Calibrated confidence for the tool selection
        """
        # Create a simple decision for calibration
        decision = Decision(
            action=f"Use tool: {tool_name}",
            rationale=f"Selected for task: {task_context[:100]}",
            confidence=confidence,
        )

        return self.calibrate(decision, context={"tool": tool_name, "task": task_context})

    def update_historical_accuracy(
        self,
        decision_type: str,
        predicted_confidence: float,
        actual_success: bool,
    ) -> None:
        """Update historical accuracy for calibration improvement.

        Args:
            decision_type: Type of decision (e.g., "tool_selection", "plan_step")
            predicted_confidence: The confidence that was predicted
            actual_success: Whether the decision was actually successful
        """
        if not self.enable_historical_calibration:
            return

        key = f"{decision_type}_{int(predicted_confidence * 10)}"

        if key not in self._historical_accuracy:
            self._historical_accuracy[key] = {"correct": 0, "total": 0}

        self._historical_accuracy[key]["total"] += 1
        if actual_success:
            self._historical_accuracy[key]["correct"] += 1

    def _calculate_evidence_score(
        self,
        decision: Decision,
        chain: ThoughtChain | None,
    ) -> float:
        """Calculate score based on evidence quality."""
        score = 0.5  # Base score

        # Check decision prerequisites
        if decision.prerequisites:
            score += 0.1

        # Check alternatives considered
        if decision.alternatives_considered:
            score += 0.1

        # Check chain evidence if available
        if chain:
            thoughts_with_evidence = sum(1 for t in chain.get_all_thoughts() if t.has_evidence())
            total_thoughts = len(chain.get_all_thoughts())
            if total_thoughts > 0:
                evidence_ratio = thoughts_with_evidence / total_thoughts
                score += evidence_ratio * 0.3

        return min(1.0, score)

    def _calculate_consistency_score(self, chain: ThoughtChain | None) -> float:
        """Calculate score based on reasoning consistency."""
        if not chain:
            return 0.5  # Neutral without chain

        # Check for contradictions
        all_thoughts = chain.get_all_thoughts()
        contested_count = sum(1 for t in all_thoughts if t.is_contested())

        if contested_count > 0:
            return max(0.2, 0.8 - contested_count * 0.1)

        # Check step progression
        if len(chain.steps) >= 3:
            # Good structured reasoning
            return 0.8

        return 0.6

    def _calculate_uncertainty_penalty(self, chain: ThoughtChain | None) -> float:
        """Calculate penalty for acknowledged uncertainties."""
        if not chain:
            return 0.0  # No penalty without chain

        uncertainties = chain.get_uncertainties()
        if not uncertainties:
            return 0.0

        # Penalty increases with number and severity of uncertainties
        penalty = 0.0
        for u in uncertainties:
            # Lower confidence uncertainties = higher penalty
            penalty += (1.0 - u.confidence) * 0.1

        return min(0.4, penalty)  # Cap at 40% penalty

    def _calculate_complexity_adjustment(
        self,
        decision: Decision,
        context: dict[str, Any] | None,
    ) -> float:
        """Calculate adjustment based on task complexity."""
        # Base adjustment is neutral
        adjustment = 0.0

        # Check for complexity indicators in decision
        complex_indicators = ["multiple", "complex", "various", "several", "many"]
        simple_indicators = ["simple", "single", "basic", "straightforward", "quick"]

        action_lower = decision.action.lower()

        if any(ind in action_lower for ind in complex_indicators):
            adjustment -= 0.1  # Reduce confidence for complex tasks
        elif any(ind in action_lower for ind in simple_indicators):
            adjustment += 0.1  # Increase for simple tasks

        # Check risks
        if len(decision.risks) > 2:
            adjustment -= 0.1

        return adjustment

    def _calculate_source_quality(self, decision: Decision) -> float:
        """Calculate score based on information source quality."""
        # Check rationale for quality indicators
        rationale_lower = decision.rationale.lower()

        high_quality = ["verified", "confirmed", "tested", "documented", "official"]
        low_quality = ["assume", "guess", "maybe", "unclear", "unknown"]

        if any(ind in rationale_lower for ind in high_quality):
            return 0.9
        if any(ind in rationale_lower for ind in low_quality):
            return 0.3

        return 0.6  # Neutral

    def _compute_calibrated_confidence(
        self,
        raw: float,
        factors: CalibrationFactors,
    ) -> float:
        """Compute the final calibrated confidence score."""
        # Base is raw confidence
        calibrated = raw

        # Apply weighted factors
        calibrated += (factors.evidence_score - 0.5) * self.EVIDENCE_WEIGHT
        calibrated += (factors.consistency_score - 0.5) * self.CONSISTENCY_WEIGHT
        calibrated -= factors.uncertainty_penalty * self.UNCERTAINTY_WEIGHT
        calibrated += factors.complexity_adjustment * self.COMPLEXITY_WEIGHT
        calibrated += (factors.source_quality_score - 0.5) * self.SOURCE_QUALITY_WEIGHT

        # Clamp to valid range
        return max(0.0, min(1.0, calibrated))

    def _get_confidence_level(self, confidence: float) -> ConfidenceLevel:
        """Determine confidence level from score."""
        if confidence >= self.HIGH_THRESHOLD:
            return ConfidenceLevel.HIGH
        if confidence >= self.MEDIUM_THRESHOLD:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    def _get_recommendation(
        self,
        level: ConfidenceLevel,
        decision: Decision,
    ) -> ActionRecommendation:
        """Determine action recommendation based on level and decision."""
        # High confidence and no major risks -> proceed
        if level == ConfidenceLevel.HIGH and len(decision.risks) <= 1:
            return ActionRecommendation.PROCEED

        # Low confidence -> ask user
        if level == ConfidenceLevel.LOW:
            return ActionRecommendation.ASK_USER

        # Medium confidence or high with risks -> verify
        return ActionRecommendation.VERIFY

    def _get_supporting_reasons(
        self,
        factors: CalibrationFactors,
        decision: Decision,
    ) -> list[str]:
        """Get supporting reasons for the confidence level."""
        reasons = []

        if factors.evidence_score >= 0.7:
            reasons.append("Strong supporting evidence")

        if factors.consistency_score >= 0.7:
            reasons.append("Consistent reasoning process")

        if factors.source_quality_score >= 0.7:
            reasons.append("High-quality information sources")

        if decision.alternatives_considered:
            reasons.append(f"Considered {len(decision.alternatives_considered)} alternatives")

        return reasons

    def _get_risk_factors(
        self,
        factors: CalibrationFactors,
        decision: Decision,
    ) -> list[str]:
        """Get risk factors affecting confidence."""
        risks = list(decision.risks)  # Start with decision risks

        if factors.uncertainty_penalty > 0.2:
            risks.append("High uncertainty in reasoning")

        if factors.evidence_score < 0.4:
            risks.append("Limited supporting evidence")

        if factors.consistency_score < 0.4:
            risks.append("Inconsistencies in reasoning")

        return risks


# Global instance
_calibrator: ConfidenceCalibrator | None = None


def get_confidence_calibrator(
    enable_historical: bool = False,
) -> ConfidenceCalibrator:
    """Get or create the global confidence calibrator."""
    global _calibrator
    if _calibrator is None:
        _calibrator = ConfidenceCalibrator(enable_historical)
    return _calibrator


def reset_calibrator() -> None:
    """Reset the global calibrator."""
    global _calibrator
    _calibrator = None
