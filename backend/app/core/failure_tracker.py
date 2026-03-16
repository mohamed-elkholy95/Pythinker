"""Track failures for adaptive circuit breaker thresholds."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass
class FailureEvent:
    timestamp: datetime
    error_type: str
    detail: str | None = None


@dataclass
class FailureStats:
    total: int
    recent: int
    failure_rate: float
    error_types: dict[str, int] = field(default_factory=dict)


class FailureTracker:
    """Track failure events for a named operation."""

    def __init__(self, window_seconds: int = 300, history_limit: int = 200) -> None:
        self._window = timedelta(seconds=window_seconds)
        self._history_limit = history_limit
        self._events: dict[str, list[FailureEvent]] = {}
        self._successes: dict[str, list[datetime]] = {}

    def record_failure(self, name: str, error_type: str, detail: str | None = None) -> None:
        events = self._events.setdefault(name, [])
        events.append(FailureEvent(timestamp=datetime.now(UTC), error_type=error_type, detail=detail))
        if len(events) > self._history_limit:
            self._events[name] = events[-self._history_limit :]

    def record_success(self, name: str) -> None:
        successes = self._successes.setdefault(name, [])
        successes.append(datetime.now(UTC))
        if len(successes) > self._history_limit:
            self._successes[name] = successes[-self._history_limit :]

    def get_stats(self, name: str) -> FailureStats:
        now = datetime.now(UTC)
        events = self._events.get(name, [])
        successes = self._successes.get(name, [])

        recent_events = [e for e in events if now - e.timestamp <= self._window]
        recent_successes = [s for s in successes if now - s <= self._window]

        total_recent = len(recent_events) + len(recent_successes)
        failure_rate = len(recent_events) / total_recent if total_recent else 0.0

        error_types: dict[str, int] = {}
        for event in recent_events:
            error_types[event.error_type] = error_types.get(event.error_type, 0) + 1

        return FailureStats(
            total=len(events),
            recent=len(recent_events),
            failure_rate=failure_rate,
            error_types=error_types,
        )

    def get_recent_errors(self, name: str, limit: int = 5) -> list[FailureEvent]:
        return self._events.get(name, [])[-limit:]

    def reset(self, name: str) -> None:
        self._events.pop(name, None)
        self._successes.pop(name, None)
