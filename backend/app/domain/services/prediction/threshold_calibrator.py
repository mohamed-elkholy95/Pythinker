"""Threshold calibration for failure prediction."""

from __future__ import annotations


class ThresholdCalibrator:
    """Simple threshold calibrator (rule-based)."""

    def __init__(self, threshold: float = 0.7) -> None:
        self._threshold = threshold

    def get_threshold(self) -> float:
        return self._threshold

    def update(self, new_threshold: float) -> None:
        self._threshold = max(0.1, min(0.95, new_threshold))
