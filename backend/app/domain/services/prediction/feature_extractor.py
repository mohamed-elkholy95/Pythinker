"""Extract features for failure prediction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.models.reflection import ProgressMetrics


@dataclass
class FailureFeatures:
    error_rate: float
    error_count: int
    stalled: bool
    recent_failure_rate: float
    consecutive_failures: int
    token_usage_pct: float | None = None
    stuck_confidence: float = 0.0


def extract_features(
    progress: ProgressMetrics | None,
    recent_actions: list[dict[str, Any]] | None = None,
    stuck_analysis: Any | None = None,
    token_usage_pct: float | None = None,
) -> FailureFeatures:
    actions = recent_actions or []

    error_count = progress.error_count if progress else 0
    total_actions = (progress.successful_actions + progress.failed_actions) if progress else len(actions)
    error_rate = (progress.failed_actions / total_actions) if progress and total_actions else 0.0

    stalled = progress.is_stalled if progress else False

    recent_slice = actions[-5:]
    recent_failures = [a for a in recent_slice if not a.get("success", True)]
    recent_failure_rate = len(recent_failures) / max(1, len(recent_slice))

    consecutive_failures = 0
    for action in reversed(actions):
        if action.get("success", True):
            break
        consecutive_failures += 1

    stuck_confidence = 0.0
    if stuck_analysis is not None:
        try:
            stuck_confidence = float(getattr(stuck_analysis, "confidence", 0.0))
        except Exception:
            stuck_confidence = 0.0

    return FailureFeatures(
        error_rate=error_rate,
        error_count=error_count,
        stalled=stalled,
        recent_failure_rate=recent_failure_rate,
        consecutive_failures=consecutive_failures,
        token_usage_pct=token_usage_pct,
        stuck_confidence=stuck_confidence,
    )
