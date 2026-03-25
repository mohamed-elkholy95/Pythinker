"""Tests for reflection domain models."""

import pytest

from app.domain.models.reflection import (
    ReflectionDecision,
    ReflectionTrigger,
    ReflectionTriggerType,
)


@pytest.mark.unit
class TestReflectionTriggerTypeEnum:
    def test_basic_triggers(self) -> None:
        for val in ("step_interval", "after_error", "low_confidence", "progress_stall", "high_error_rate", "explicit"):
            assert ReflectionTriggerType(val)

    def test_enhanced_triggers(self) -> None:
        for val in ("plan_divergence", "pattern_change", "confidence_decay", "user_requested", "quality_degradation"):
            assert ReflectionTriggerType(val)


@pytest.mark.unit
class TestReflectionDecisionEnum:
    def test_all_values(self) -> None:
        expected = {"continue", "adjust", "replan", "escalate", "abort"}
        assert {d.value for d in ReflectionDecision} == expected


@pytest.mark.unit
class TestReflectionTrigger:
    def test_defaults(self) -> None:
        trigger = ReflectionTrigger()
        assert trigger.step_interval == 2
        assert trigger.min_steps_before_first == 1
        assert trigger.reflect_after_error is True
        assert trigger.error_rate_threshold == 0.5
        assert trigger.confidence_threshold == 0.6
        assert trigger.stall_detection is True

    def test_step_interval_trigger(self) -> None:
        trigger = ReflectionTrigger(step_interval=2, min_steps_before_first=1)
        result = trigger.should_trigger(
            steps_completed=2, error_count=0, total_attempts=2,
        )
        assert result == ReflectionTriggerType.STEP_INTERVAL

    def test_no_trigger_before_min_steps(self) -> None:
        trigger = ReflectionTrigger(step_interval=2, min_steps_before_first=3)
        result = trigger.should_trigger(
            steps_completed=2, error_count=0, total_attempts=2,
        )
        assert result is None

    def test_after_error_trigger(self) -> None:
        trigger = ReflectionTrigger(step_interval=100)  # Avoid step trigger
        result = trigger.should_trigger(
            steps_completed=1, error_count=1, total_attempts=1, last_had_error=True,
        )
        assert result == ReflectionTriggerType.AFTER_ERROR

    def test_after_error_disabled(self) -> None:
        trigger = ReflectionTrigger(reflect_after_error=False, step_interval=100)
        result = trigger.should_trigger(
            steps_completed=1, error_count=0, total_attempts=1, last_had_error=True,
        )
        assert result is None

    def test_high_error_rate_trigger(self) -> None:
        trigger = ReflectionTrigger(
            step_interval=100, reflect_after_error=False,
            error_rate_threshold=0.5,
        )
        result = trigger.should_trigger(
            steps_completed=1, error_count=6, total_attempts=10,
        )
        assert result == ReflectionTriggerType.HIGH_ERROR_RATE

    def test_low_confidence_trigger(self) -> None:
        trigger = ReflectionTrigger(
            step_interval=100, reflect_after_error=False,
            confidence_threshold=0.6,
        )
        result = trigger.should_trigger(
            steps_completed=1, error_count=0, total_attempts=5, confidence=0.3,
        )
        assert result == ReflectionTriggerType.LOW_CONFIDENCE

    def test_stall_trigger(self) -> None:
        trigger = ReflectionTrigger(
            step_interval=100, reflect_after_error=False,
        )
        result = trigger.should_trigger(
            steps_completed=1, error_count=0, total_attempts=5, is_stalled=True,
        )
        assert result == ReflectionTriggerType.PROGRESS_STALL

    def test_stall_detection_disabled(self) -> None:
        trigger = ReflectionTrigger(
            step_interval=100, reflect_after_error=False, stall_detection=False,
        )
        result = trigger.should_trigger(
            steps_completed=1, error_count=0, total_attempts=5, is_stalled=True,
        )
        assert result is None

    def test_no_trigger_when_ok(self) -> None:
        trigger = ReflectionTrigger(step_interval=100)
        result = trigger.should_trigger(
            steps_completed=1, error_count=0, total_attempts=5, confidence=0.9,
        )
        assert result is None

    def test_record_confidence(self) -> None:
        trigger = ReflectionTrigger()
        for c in [0.9, 0.85, 0.8]:
            trigger.record_confidence(c)
        assert len(trigger._confidence_history) == 3

    def test_confidence_history_capped(self) -> None:
        trigger = ReflectionTrigger()
        for _i in range(15):
            trigger.record_confidence(0.5)
        assert len(trigger._confidence_history) == 10

    def test_confidence_decay_detection(self) -> None:
        trigger = ReflectionTrigger(
            step_interval=100, reflect_after_error=False,
            detect_confidence_decay=True, confidence_decay_threshold=0.1,
        )
        # Simulate decaying confidence
        for c in [0.9, 0.85, 0.8, 0.7, 0.6, 0.5]:
            trigger.record_confidence(c)
        assert trigger._detect_confidence_decay() is True

    def test_no_confidence_decay_with_stable_values(self) -> None:
        trigger = ReflectionTrigger()
        for c in [0.8, 0.81, 0.79, 0.8, 0.82, 0.8]:
            trigger.record_confidence(c)
        assert trigger._detect_confidence_decay() is False


@pytest.mark.unit
class TestReflectionTriggerEnhanced:
    def test_user_requested_highest_priority(self) -> None:
        trigger = ReflectionTrigger(step_interval=100)
        result = trigger.should_trigger_enhanced(
            steps_completed=1, error_count=0, total_attempts=1,
            user_requested=True,
        )
        assert result == ReflectionTriggerType.USER_REQUESTED

    def test_plan_divergence_trigger(self) -> None:
        trigger = ReflectionTrigger(step_interval=100)
        result = trigger.should_trigger_enhanced(
            steps_completed=1, error_count=0, total_attempts=1,
            plan_divergence=0.5,
        )
        assert result == ReflectionTriggerType.PLAN_DIVERGENCE

    def test_pattern_change_trigger(self) -> None:
        trigger = ReflectionTrigger(step_interval=100)
        result = trigger.should_trigger_enhanced(
            steps_completed=1, error_count=0, total_attempts=1,
            pattern_change_detected=True,
        )
        assert result == ReflectionTriggerType.PATTERN_CHANGE

    def test_falls_back_to_basic(self) -> None:
        trigger = ReflectionTrigger(step_interval=2)
        result = trigger.should_trigger_enhanced(
            steps_completed=2, error_count=0, total_attempts=2,
        )
        assert result == ReflectionTriggerType.STEP_INTERVAL
