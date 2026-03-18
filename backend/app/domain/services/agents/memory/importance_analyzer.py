"""Importance scoring for context optimization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass
class ImportanceScore:
    """Score with rationale for a message's importance."""

    score: float
    reasons: list[str] = field(default_factory=list)


class ImportanceAnalyzer:
    """Heuristic importance scoring for message compression decisions."""

    _ROLE_BASE: ClassVar[dict[str, float]] = {
        "system": 0.9,
        "user": 0.85,
        "assistant": 0.6,
        "tool": 0.3,
    }

    _HIGH_SIGNAL_KEYWORDS = (
        "decision",
        "plan",
        "goal",
        "blocked",
        "dependency",
        "result",
        "summary",
        "error",
        "failed",
        "success",
        "verification",
    )

    def score_message(
        self, message: dict[str, Any], index: int, total: int, preserve_recent: int = 10
    ) -> ImportanceScore:
        role = message.get("role", "assistant")
        score = self._ROLE_BASE.get(role, 0.5)
        reasons = [f"role:{role}"]

        # Recent messages are more important to preserve.
        if index >= max(0, total - preserve_recent):
            score = max(score, 0.8)
            reasons.append("recent")

        content = str(message.get("content", ""))
        lowered = content.lower()
        for keyword in self._HIGH_SIGNAL_KEYWORDS:
            if keyword in lowered:
                score += 0.05
                reasons.append(f"kw:{keyword}")

        score = min(score, 1.0)
        return ImportanceScore(score=score, reasons=reasons)

    @staticmethod
    def is_low_importance(score: float, threshold: float = 0.5) -> bool:
        return score < threshold
