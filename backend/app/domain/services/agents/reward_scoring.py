"""Reward scoring with gaming detection (log-only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.services.agents.gaming_detector import GamingDetector, GamingSignal


@dataclass
class RewardScore:
    """Reward scoring result with gaming signals."""

    overall: float
    violation: bool
    signals: list[GamingSignal] = field(default_factory=list)
    subscores: dict[str, float] = field(default_factory=dict)


class RewardScorer:
    """Compute a heuristic reward score and detect gaming patterns."""

    def __init__(self, detector: GamingDetector | None = None) -> None:
        self._detector = detector or GamingDetector()

    def score_output(
        self,
        output: str,
        user_request: str,
        recent_actions: list[dict[str, Any]] | None = None,
        tool_traces: list[Any] | None = None,
    ) -> RewardScore:
        signals = self._detector.detect(
            output=output,
            user_request=user_request,
            recent_actions=recent_actions,
            tool_traces=tool_traces,
        )

        overall = 1.0
        for signal in signals:
            if signal.severity == "high":
                overall -= 0.4
            elif signal.severity == "medium":
                overall -= 0.2
            else:
                overall -= 0.1

        overall = max(0.0, min(1.0, overall))
        violation = any(signal.severity == "high" for signal in signals)

        subscores = {
            "correctness": 1.0,
            "reasoning": 1.0 - (0.2 * len(signals)),
            "completeness": 1.0,
            "presentation": 1.0,
        }
        subscores = {k: max(0.0, min(1.0, v)) for k, v in subscores.items()}

        return RewardScore(overall=overall, violation=violation, signals=signals, subscores=subscores)
