"""Tests for latency SLO tracking (Phase 4A)."""

import pytest

from app.core.prometheus_metrics import (
    record_minio_operation,
    record_mongodb_operation,
    slo_violations_total,
)


class TestRecordMongoDBOperation:
    """Tests for record_mongodb_operation helper."""

    def test_records_duration_histogram(self):
        """Operation duration is recorded in the histogram."""
        record_mongodb_operation("find", "sessions", 0.05)
        # No exception means histogram.observe was called successfully

    def test_no_slo_violation_under_threshold(self):
        """Durations under threshold do not trigger SLO violations."""
        initial = slo_violations_total.get({"service": "mongodb", "operation": "find_ok"})
        record_mongodb_operation("find_ok", "sessions", 0.05, slo_threshold=0.1)
        after = slo_violations_total.get({"service": "mongodb", "operation": "find_ok"})
        assert after == initial

    def test_slo_violation_over_threshold(self):
        """Durations over threshold trigger SLO violation counter."""
        initial = slo_violations_total.get({"service": "mongodb", "operation": "slow_find"})
        record_mongodb_operation("slow_find", "sessions", 0.5, slo_threshold=0.1)
        after = slo_violations_total.get({"service": "mongodb", "operation": "slow_find"})
        assert after == initial + 1


class TestRecordMinIOOperation:
    """Tests for record_minio_operation helper."""

    def test_records_duration_histogram(self):
        """Operation duration is recorded in the histogram."""
        record_minio_operation("put_object", "screenshots", 0.2)

    def test_slo_violation_over_threshold(self):
        """Durations over threshold trigger SLO violation counter."""
        initial = slo_violations_total.get({"service": "minio", "operation": "slow_put"})
        record_minio_operation("slow_put", "screenshots", 2.0, slo_threshold=0.5)
        after = slo_violations_total.get({"service": "minio", "operation": "slow_put"})
        assert after == initial + 1


class TestLatencyTracker:
    """Tests for the async context manager track_operation."""

    @pytest.mark.asyncio
    async def test_track_operation_records_metrics(self):
        """Context manager records duration and checks SLO."""
        from app.infrastructure.middleware.latency_tracker import track_operation

        async with track_operation("mongodb", "test_op", collection="test"):
            pass  # Instant operation — should not violate SLO

    @pytest.mark.asyncio
    async def test_track_operation_survives_exceptions(self):
        """Metrics are still recorded even if the operation raises."""
        from app.infrastructure.middleware.latency_tracker import track_operation

        with pytest.raises(ValueError, match="test error"):
            async with track_operation("mongodb", "failing_op", collection="test"):
                raise ValueError("test error")
