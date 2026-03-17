"""Sliding-window provider health ranker for dynamic search chain reordering.

Records per-provider success/429/error events in a 5-minute sliding window
and computes a composite health score. Providers with poor health are
automatically sorted toward the back of the fallback chain.

Stateless (no Redis), process-scoped singleton. Score changes are also
exported as Prometheus metrics.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field

from app.core.prometheus_metrics import search_provider_health_score

logger = logging.getLogger(__name__)

# Sliding window duration in seconds
WINDOW_SECONDS: float = 300.0

# Weight of each factor in the composite score
_429_WEIGHT: float = 0.70  # 429 rate is the dominant signal
_ERROR_WEIGHT: float = 0.30  # General error rate (5xx, timeout, etc.)

# Threshold above which a provider is considered degraded
DEGRADED_429_RATIO: float = 0.30


@dataclass
class _ProviderStats:
    """Per-provider sliding-window event log."""

    events: deque = field(default_factory=deque)  # deque of (timestamp, event_type)


class ProviderHealthRanker:
    """Sliding-window health scorer for search providers.

    Usage:
        ranker = get_provider_health_ranker()
        ranker.record_success("serper")
        ranker.record_429("tavily")
        ordered = ranker.rank(["serper", "tavily", "brave", "exa"])
    """

    def __init__(self) -> None:
        self._stats: dict[str, _ProviderStats] = {}

    def _get_stats(self, provider: str) -> _ProviderStats:
        if provider not in self._stats:
            self._stats[provider] = _ProviderStats()
        return self._stats[provider]

    def _prune(self, stats: _ProviderStats) -> None:
        """Remove events older than WINDOW_SECONDS."""
        cutoff = time.monotonic() - WINDOW_SECONDS
        while stats.events and stats.events[0][0] < cutoff:
            stats.events.popleft()

    def record_success(self, provider: str) -> None:
        """Record a successful search request."""
        stats = self._get_stats(provider)
        stats.events.append((time.monotonic(), "success"))
        self._prune(stats)
        self._update_metric(provider)

    def record_429(self, provider: str) -> None:
        """Record a 429 rate-limit response."""
        stats = self._get_stats(provider)
        stats.events.append((time.monotonic(), "429"))
        self._prune(stats)
        self._update_metric(provider)

    def record_error(self, provider: str) -> None:
        """Record a non-429 error (5xx, timeout, etc.)."""
        stats = self._get_stats(provider)
        stats.events.append((time.monotonic(), "error"))
        self._prune(stats)
        self._update_metric(provider)

    def health_score(self, provider: str) -> float:
        """Compute composite health score in [0.0, 1.0] for a provider.

        1.0 = fully healthy (no 429s, no errors in window)
        0.0 = fully degraded (all requests failing)
        """
        stats = self._get_stats(provider)
        self._prune(stats)
        if not stats.events:
            return 1.0  # No data = assume healthy

        total = len(stats.events)
        count_429 = sum(1 for _, t in stats.events if t == "429")
        count_error = sum(1 for _, t in stats.events if t == "error")

        ratio_429 = count_429 / total
        ratio_error = count_error / total

        penalty = ratio_429 * _429_WEIGHT + ratio_error * _ERROR_WEIGHT
        return max(0.0, 1.0 - penalty)

    def rank(self, chain: list[str]) -> list[str]:
        """Return providers sorted by health score (healthiest first).

        Preserves original order for providers with equal scores.
        """
        return sorted(chain, key=lambda p: -self.health_score(p))

    def _update_metric(self, provider: str) -> None:
        """Export health score to Prometheus."""
        try:
            score = self.health_score(provider)
            search_provider_health_score.set({"provider": provider}, score)
        except Exception as exc:
            # Never let metric export break core search logic
            logger.debug("Failed to export health metric for %s: %s", provider, exc)


# Process-scoped singleton
_ranker: ProviderHealthRanker | None = None


def get_provider_health_ranker() -> ProviderHealthRanker:
    """Return the process-scoped singleton ProviderHealthRanker."""
    global _ranker
    if _ranker is None:
        _ranker = ProviderHealthRanker()
    return _ranker
