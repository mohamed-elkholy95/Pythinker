"""Tests for ThresholdCalibrator."""

from __future__ import annotations

import pytest

from app.domain.services.prediction.threshold_calibrator import ThresholdCalibrator


class TestThresholdCalibratorInit:
    def test_default_threshold(self) -> None:
        calibrator = ThresholdCalibrator()
        assert calibrator.get_threshold() == 0.7

    def test_custom_threshold(self) -> None:
        calibrator = ThresholdCalibrator(threshold=0.5)
        assert calibrator.get_threshold() == 0.5


class TestThresholdCalibratorUpdate:
    def test_update_in_range(self) -> None:
        calibrator = ThresholdCalibrator()
        calibrator.update(0.8)
        assert calibrator.get_threshold() == pytest.approx(0.8)

    def test_update_clamps_below_minimum(self) -> None:
        calibrator = ThresholdCalibrator()
        calibrator.update(0.0)
        assert calibrator.get_threshold() == pytest.approx(0.1)

    def test_update_clamps_above_maximum(self) -> None:
        calibrator = ThresholdCalibrator()
        calibrator.update(1.0)
        assert calibrator.get_threshold() == pytest.approx(0.95)

    def test_update_to_exact_lower_boundary(self) -> None:
        calibrator = ThresholdCalibrator()
        calibrator.update(0.1)
        assert calibrator.get_threshold() == pytest.approx(0.1)

    def test_update_to_exact_upper_boundary(self) -> None:
        calibrator = ThresholdCalibrator()
        calibrator.update(0.95)
        assert calibrator.get_threshold() == pytest.approx(0.95)

    def test_update_negative_value_clamps_to_minimum(self) -> None:
        calibrator = ThresholdCalibrator()
        calibrator.update(-5.0)
        assert calibrator.get_threshold() == pytest.approx(0.1)
