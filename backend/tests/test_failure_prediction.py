from app.domain.models.reflection import ProgressMetrics
from app.domain.services.prediction.failure_predictor import FailurePredictor


def test_failure_prediction_flags_high_error_rate():
    progress = ProgressMetrics(steps_completed=0, steps_remaining=3, total_steps=3)
    progress.failed_actions = 4
    progress.successful_actions = 2

    predictor = FailurePredictor()
    prediction = predictor.predict(progress=progress, recent_actions=[{"success": False}] * 4)

    assert prediction.probability >= 0.5
    assert prediction.will_fail
    assert "high_error_rate" in prediction.factors


def test_failure_prediction_stuck_increases_risk():
    progress = ProgressMetrics(steps_completed=1, steps_remaining=2, total_steps=3)
    progress.actions_since_progress = 5

    predictor = FailurePredictor()
    prediction = predictor.predict(progress=progress, recent_actions=[{"success": True}] * 3)

    assert prediction.probability >= 0.2
    assert "stalled" in prediction.factors


def test_failure_prediction_token_pressure():
    progress = ProgressMetrics(steps_completed=1, steps_remaining=2, total_steps=3)
    predictor = FailurePredictor()

    prediction = predictor.predict(progress=progress, recent_actions=[], token_usage_pct=0.9)

    assert "token_pressure" in prediction.factors
    assert prediction.probability >= 0.15
