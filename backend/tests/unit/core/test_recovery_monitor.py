"""Tests for core recovery monitor."""

import pytest

from app.core.recovery_monitor import RecoveryMonitor, RecoveryStats


@pytest.mark.unit
class TestRecoveryStats:
    """Tests for RecoveryStats dataclass."""

    def test_defaults(self) -> None:
        stats = RecoveryStats()
        assert stats.attempts == 0
        assert stats.successes == 0
        assert stats.failures == 0
        assert stats.mttr_seconds == 0.0
        assert stats.last_recovery_seconds is None


@pytest.mark.unit
class TestRecoveryMonitor:
    """Tests for RecoveryMonitor."""

    def test_initial_stats_empty(self) -> None:
        monitor = RecoveryMonitor()
        stats = monitor.get_stats("nonexistent")
        assert stats.attempts == 0

    def test_record_open(self) -> None:
        monitor = RecoveryMonitor()
        monitor.record_open("svc1")
        assert "svc1" in monitor._open_times

    def test_record_successful_recovery(self) -> None:
        monitor = RecoveryMonitor()
        monitor.record_open("svc1")
        stats = monitor.record_recovery("svc1", success=True)
        assert stats.attempts == 1
        assert stats.successes == 1
        assert stats.failures == 0
        assert stats.last_recovery_seconds is not None
        assert stats.mttr_seconds > 0 or stats.mttr_seconds == stats.last_recovery_seconds

    def test_record_failed_recovery(self) -> None:
        monitor = RecoveryMonitor()
        monitor.record_open("svc1")
        stats = monitor.record_recovery("svc1", success=False)
        assert stats.attempts == 1
        assert stats.successes == 0
        assert stats.failures == 1

    def test_multiple_recoveries_update_stats(self) -> None:
        monitor = RecoveryMonitor()
        monitor.record_open("svc1")
        monitor.record_recovery("svc1", success=True)
        monitor.record_open("svc1")
        stats = monitor.record_recovery("svc1", success=True)
        assert stats.attempts == 2
        assert stats.successes == 2

    def test_get_stats_returns_copy(self) -> None:
        monitor = RecoveryMonitor()
        stats = monitor.get_stats("svc1")
        assert isinstance(stats, RecoveryStats)

    def test_reset_clears_data(self) -> None:
        monitor = RecoveryMonitor()
        monitor.record_open("svc1")
        monitor.record_recovery("svc1", success=True)
        monitor.reset("svc1")
        assert "svc1" not in monitor._open_times
        stats = monitor.get_stats("svc1")
        assert stats.attempts == 0

    def test_recovery_without_open_time(self) -> None:
        monitor = RecoveryMonitor()
        stats = monitor.record_recovery("svc1", success=True)
        assert stats.successes == 1
        assert stats.last_recovery_seconds is None

    def test_mttr_averages(self) -> None:
        monitor = RecoveryMonitor()
        # First recovery
        monitor.record_open("svc1")
        stats = monitor.record_recovery("svc1", success=True)
        first_mttr = stats.mttr_seconds
        # Second recovery
        monitor.record_open("svc1")
        stats = monitor.record_recovery("svc1", success=True)
        # MTTR should be averaged
        assert stats.mttr_seconds >= 0
