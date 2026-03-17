"""Rule-based failure predictor for proactive intervention."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.services.prediction.feature_extractor import FailureFeatures, extract_features
from app.domain.services.prediction.interventions import recommend_intervention
from app.domain.services.prediction.threshold_calibrator import ThresholdCalibrator


@dataclass
class FailurePrediction:
    will_fail: bool
    probability: float
    factors: list[str] = field(default_factory=list)
    recommended_action: str = "monitor"


def _score_features(features: FailureFeatures) -> tuple[float, list[str]]:
    probability = 0.0
    factors: list[str] = []

    if features.error_rate >= 0.5 or features.error_count >= 3:
        probability += 0.3
        factors.append("high_error_rate")

    if features.stalled:
        probability += 0.2
        factors.append("stalled")

    if features.recent_failure_rate >= 0.6:
        probability += 0.2
        factors.append("recent_failures")

    if features.consecutive_failures >= 3:
        probability += 0.2
        factors.append("consecutive_failures")

    if features.token_usage_pct is not None and features.token_usage_pct >= 0.85:
        probability += 0.15
        factors.append("token_pressure")

    if features.stuck_confidence >= 0.7:
        probability += 0.3
        factors.append("stuck_pattern")

    probability = min(1.0, probability)
    return probability, factors


class FailurePredictor:
    """Rule-based failure predictor (shadow mode ready)."""

    def __init__(self, calibrator: ThresholdCalibrator | None = None) -> None:
        self._calibrator = calibrator or ThresholdCalibrator()

    def predict(
        self,
        progress,
        recent_actions=None,
        stuck_analysis=None,
        token_usage_pct: float | None = None,
    ) -> FailurePrediction:
        features = extract_features(
            progress=progress,
            recent_actions=recent_actions,
            stuck_analysis=stuck_analysis,
            token_usage_pct=token_usage_pct,
        )
        probability, factors = _score_features(features)
        threshold = self._calibrator.get_threshold()
        will_fail = probability >= threshold
        recommended_action = recommend_intervention(probability, factors)

        return FailurePrediction(
            will_fail=will_fail,
            probability=probability,
            factors=factors,
            recommended_action=recommended_action,
        )
