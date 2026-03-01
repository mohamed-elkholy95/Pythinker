"""Sliding-window health scoring for LLM providers (domain layer).

Tracks latency and error rate per provider in a fixed-size circular window
and exposes a 0.0-1.0 health score.  Used by ``UniversalLLM`` to choose
the healthiest provider from the fallback chain.

Design decisions:
- **No external deps** — pure Python, no Redis.  Single-process only; good
  enough for the typical deployment where one process handles all LLM calls.
- **Shadow mode aware** — when ``feature_llm_health_scoring=True`` but
  ``feature_llm_provider_fallback=False``, scoring runs but never influences
  routing.  Logged for observability.
- **Thread/async safe** — uses ``threading.Lock``; callers from async code
  should call ``record`` from the same thread (fine for asyncio single-thread
  event loop).

Usage::

    tracker = get_provider_health_tracker()
    tracker.record("anthropic", latency_ms=340.0, success=True)
    score = tracker.score("anthropic")          # 0.0-1.0
    best = tracker.best_provider(["anthropic", "openai"])
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ─────────────────────────── Data ────────────────────────────────────────────


@dataclass
class _Sample:
    latency_ms: float
    success: bool


# ─────────────────────────── Tracker ─────────────────────────────────────────


class ProviderHealthTracker:
    """Sliding-window health scoring for multiple LLM providers.

    Args:
        window_size: Number of recent calls tracked per provider.
        latency_percentile_weight: How much latency contributes to the
            health score relative to the error rate.  Default 0.3 means
            latency = 30 %, error-rate = 70 %.
        max_good_latency_ms: Latency considered "perfect" (contributes
            full latency score).  Calls above this are scaled down.
    """

    def __init__(
        self,
        window_size: int = 100,
        latency_percentile_weight: float = 0.3,
        max_good_latency_ms: float = 10_000.0,
    ) -> None:
        self._window_size = window_size
        self._latency_weight = latency_percentile_weight
        self._max_good_latency_ms = max_good_latency_ms
        # provider → circular buffer of samples
        self._windows: dict[str, deque[_Sample]] = {}
        self._lock = threading.Lock()

    def record(self, provider: str, latency_ms: float, success: bool) -> None:
        """Record one call result for a provider.

        Args:
            provider: Provider name (e.g. ``"anthropic"``, ``"openai"``).
            latency_ms: Wall-clock time of the call in milliseconds.
            success: Whether the call succeeded without error.
        """
        with self._lock:
            if provider not in self._windows:
                self._windows[provider] = deque(maxlen=self._window_size)
            self._windows[provider].append(_Sample(latency_ms=latency_ms, success=success))

        logger.debug(
            "Health recorded: provider=%s latency_ms=%.0f success=%s",
            provider,
            latency_ms,
            success,
        )

    def score(self, provider: str) -> float:
        """Return a health score in [0.0, 1.0] for a provider.

        A score of 1.0 means all recent calls succeeded with low latency.
        A score of 0.0 means all recent calls failed.

        Providers with no recorded samples return 1.0 (optimistic default
        so unknown providers are tried rather than skipped).
        """
        with self._lock:
            samples = list(self._windows.get(provider, []))

        if not samples:
            return 1.0  # optimistic: never tried → assume healthy

        success_rate = sum(1 for s in samples if s.success) / len(samples)

        # Latency component: ratio of good-latency calls (≤ max_good_latency_ms)
        good_latency = sum(
            1 for s in samples if s.success and s.latency_ms <= self._max_good_latency_ms
        )
        latency_score = good_latency / len(samples)

        health = (
            (1.0 - self._latency_weight) * success_rate
            + self._latency_weight * latency_score
        )
        return round(max(0.0, min(1.0, health)), 4)

    def best_provider(self, candidates: list[str]) -> str:
        """Return the candidate provider with the highest health score.

        Args:
            candidates: Non-empty list of provider names.

        Returns:
            The provider name with the best health score.  Ties are broken
            by list order (earlier = preferred).

        Raises:
            ValueError: If ``candidates`` is empty.
        """
        if not candidates:
            raise ValueError("candidates must not be empty")

        scores = {p: self.score(p) for p in candidates}
        best = max(scores, key=lambda p: (scores[p], -candidates.index(p)))

        logger.debug("best_provider: %s (scores=%s)", best, scores)
        return best

    def status_report(self) -> dict[str, float]:
        """Return a {provider: score} dict for all tracked providers."""
        with self._lock:
            providers = list(self._windows.keys())
        return {p: self.score(p) for p in providers}


# ─────────────────────────── Singleton ───────────────────────────────────────

_tracker_instance: ProviderHealthTracker | None = None
_tracker_lock = threading.Lock()


def get_provider_health_tracker() -> ProviderHealthTracker:
    """Return the process-level singleton ProviderHealthTracker."""
    global _tracker_instance
    if _tracker_instance is not None:
        return _tracker_instance

    with _tracker_lock:
        if _tracker_instance is not None:
            return _tracker_instance

        try:
            from app.core.config import get_settings

            settings = get_settings()
            window_size: int = getattr(settings, "llm_health_window_size", 100)
        except Exception:
            window_size = 100

        _tracker_instance = ProviderHealthTracker(window_size=window_size)
        return _tracker_instance


def reset_provider_health_tracker() -> None:
    """Reset the singleton (for testing)."""
    global _tracker_instance
    with _tracker_lock:
        _tracker_instance = None
