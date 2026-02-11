"""In-memory and file-backed analytics for typo correction feedback."""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from threading import Lock
from typing import Any

from app.domain.services.flows.prompt_quick_validator import CorrectionEvent

logger = logging.getLogger(__name__)


class TypoCorrectionAnalytics:
    """Tracks correction events and feedback for continuous tuning."""

    def __init__(
        self,
        *,
        storage_path: Path,
        min_feedback_occurrences: int = 3,
    ) -> None:
        self._storage_path = storage_path
        self._min_feedback_occurrences = min_feedback_occurrences
        self._lock = Lock()

        self._correction_counts: Counter[tuple[str, str]] = Counter()
        self._method_counts: Counter[str] = Counter()
        self._feedback_overrides: Counter[tuple[str, str]] = Counter()
        self._feedback_rejections: Counter[tuple[str, str]] = Counter()

        self._load_feedback()

    def record_event(self, event: CorrectionEvent) -> None:
        with self._lock:
            key = (event.original.lower(), event.corrected.lower())
            self._correction_counts[key] += 1
            self._method_counts[event.method] += 1

    def record_feedback(
        self,
        *,
        original: str,
        corrected: str,
        user_override: str,
    ) -> None:
        normalized_original = original.lower().strip()
        normalized_corrected = corrected.lower().strip()
        normalized_override = user_override.lower().strip()

        if not normalized_original or not normalized_override:
            return

        with self._lock:
            if normalized_override != normalized_corrected:
                self._feedback_overrides[(normalized_original, normalized_override)] += 1
                self._feedback_rejections[(normalized_original, normalized_corrected)] += 1
            self._save_feedback()

    def get_feedback_override(self, word: str) -> str | None:
        normalized_word = word.lower().strip()
        if not normalized_word:
            return None

        with self._lock:
            candidates = [
                (pair, count)
                for pair, count in self._feedback_overrides.items()
                if pair[0] == normalized_word and count >= self._min_feedback_occurrences
            ]
            if not candidates:
                return None

            best, _ = max(candidates, key=lambda item: item[1])
            return best[1]

    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            top_corrections = [
                {"original": original, "corrected": corrected, "count": count}
                for (original, corrected), count in self._correction_counts.most_common(20)
            ]
            top_feedback_overrides = [
                {"original": original, "override": override, "count": count}
                for (original, override), count in self._feedback_overrides.most_common(20)
            ]
            return {
                "total_corrections": int(sum(self._correction_counts.values())),
                "methods": dict(self._method_counts),
                "top_corrections": top_corrections,
                "top_feedback_overrides": top_feedback_overrides,
            }

    def _load_feedback(self) -> None:
        if not self._storage_path.exists():
            return

        try:
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
            overrides = payload.get("overrides", {})
            rejections = payload.get("rejections", {})
            self._feedback_overrides = Counter({tuple(k.split("|", 1)): int(v) for k, v in overrides.items()})
            self._feedback_rejections = Counter({tuple(k.split("|", 1)): int(v) for k, v in rejections.items()})
        except (ValueError, OSError) as exc:
            logger.warning("Failed to load typo correction feedback store: %s", exc)

    def _save_feedback(self) -> None:
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "overrides": {"|".join(k): v for k, v in self._feedback_overrides.items()},
                "rejections": {"|".join(k): v for k, v in self._feedback_rejections.items()},
            }
            self._storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to persist typo correction feedback store: %s", exc)


_typo_correction_analytics: TypoCorrectionAnalytics | None = None


def get_typo_correction_analytics() -> TypoCorrectionAnalytics:
    global _typo_correction_analytics
    if _typo_correction_analytics is None:
        from app.core.config import get_settings

        settings = get_settings()
        _typo_correction_analytics = TypoCorrectionAnalytics(
            storage_path=Path(settings.typo_correction_feedback_store_path),
            min_feedback_occurrences=settings.typo_correction_feedback_min_occurrences,
        )
    return _typo_correction_analytics
