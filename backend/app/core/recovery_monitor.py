"""Track recovery attempts and mean time to recovery for circuit breakers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class RecoveryStats:
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    mttr_seconds: float = 0.0
    last_recovery_seconds: float | None = None


class RecoveryMonitor:
    """Monitor recovery attempts for circuit breakers."""

    def __init__(self, history_limit: int = 100) -> None:
        self._open_times: dict[str, datetime] = {}
        self._stats: dict[str, RecoveryStats] = {}
        self._history_limit = history_limit

    def record_open(self, name: str) -> None:
        self._open_times[name] = datetime.now(UTC)

    def record_recovery(self, name: str, success: bool) -> RecoveryStats:
        stats = self._stats.setdefault(name, RecoveryStats())
        stats.attempts += 1
        if success:
            stats.successes += 1
        else:
            stats.failures += 1

        opened_at = self._open_times.get(name)
        if opened_at and success:
            delta = (datetime.now(UTC) - opened_at).total_seconds()
            stats.last_recovery_seconds = delta
            # Incremental MTTR average
            if stats.mttr_seconds == 0.0:
                stats.mttr_seconds = delta
            else:
                stats.mttr_seconds = (stats.mttr_seconds + delta) / 2
            self._open_times.pop(name, None)

        return stats

    def get_stats(self, name: str) -> RecoveryStats:
        return self._stats.get(name, RecoveryStats())

    def reset(self, name: str) -> None:
        self._open_times.pop(name, None)
        self._stats.pop(name, None)
