"""Recommended interventions for predicted failures."""

from __future__ import annotations

from collections.abc import Iterable


def recommend_intervention(probability: float, factors: Iterable[str]) -> str:
    factors = set(factors)

    if probability >= 0.85:
        if "stuck_pattern" in factors or "high_error_rate" in factors:
            return "replan"
        if "token_pressure" in factors:
            return "compress_context"
        return "escalate"

    if probability >= 0.7:
        if "recent_failures" in factors:
            return "reflect"
        if "stalled" in factors:
            return "adjust_strategy"
        return "monitor"

    return "monitor"
