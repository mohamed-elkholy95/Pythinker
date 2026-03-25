"""Tests for OrphanedTaskCleanupService and CleanupMetrics.

Covers:
- CleanupMetrics: default values and to_dict() serialisation
- run_cleanup: rate limiting skips redundant runs
- run_cleanup: orchestrates all four cleanup phases
- run_cleanup: catches top-level exceptions and records in metrics
- run_cleanup: duration_ms is always set in the finally block
- run_cleanup: rate-limit resets after _min_cleanup_interval_seconds
- _is_stream_orphaned: returns False for non-stream key types
- _is_stream_orphaned: returns False when consumer groups exist
- _is_stream_orphaned: returns True for empty streams (length == 0)
- _is_stream_orphaned: returns True for old streams (age > threshold)
- _is_stream_orphaned: returns False for young streams (age < threshold)
- _is_stream_orphaned: returns False when last-generated-id is absent
- _is_stream_orphaned: returns False on Redis errors (conservative)
- _cleanup_orphaned_redis_streams: deletes orphaned task:input:* and task:output:* streams
- _cleanup_orphaned_redis_streams: ignores non-task keys
- _cleanup_orphaned_redis_streams: handles per-stream errors without aborting
- _cleanup_orphaned_redis_streams: iterates multiple scan pages (cursor != 0)
- _cleanup_orphaned_redis_streams: handles top-level scan failure gracefully
- _cleanup_stale_cancel_events: skips sessions without a cancel signal
- _cleanup_stale_cancel_events: marks RUNNING sessions with stale cancel as FAILED
- _cleanup_zombie_sessions: skips sessions with recent events
- _cleanup_zombie_sessions: marks stale RUNNING sessions with no events as FAILED
- _is_sandbox_orphaned: returns False when an active session references the container
- _is_sandbox_orphaned: returns False via suffix match for pythinker-sandbox- prefix
- _is_sandbox_orphaned: returns True when no active session references it
- _is_sandbox_orphaned: returns False on DB errors (conservative)
- scheduled_cleanup_job: instantiates the service and calls run_cleanup
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.services.orphaned_task_cleanup_service import (
    CleanupMetrics,
    OrphanedTaskCleanupService,
    scheduled_cleanup_job,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis() -> AsyncMock:
    """Return a fully-mocked Redis async client with safe defaults."""
    redis = AsyncMock()
    # scan returns (cursor=0, []) by default — caller overrides as needed
    redis.scan.return_value = (0, [])
    redis.type.return_value = b"stream"
    redis.xinfo_stream.return_value = {"length": 0, "last-generated-id": None}
    redis.xinfo_groups.return_value = []
    redis.delete.return_value = 1
    redis.exists.return_value = 0
    return redis


def _make_settings(
    orphaned_stream_age_seconds: int = 300,
    zombie_session_age_seconds: int = 900,
    stale_cancel_event_age_seconds: int = 600,
) -> MagicMock:
    settings = MagicMock()
    settings.orphaned_stream_age_seconds = orphaned_stream_age_seconds
    settings.zombie_session_age_seconds = zombie_session_age_seconds
    settings.stale_cancel_event_age_seconds = stale_cancel_event_age_seconds
    return settings


def _make_service(
    redis: AsyncMock | None = None,
    settings: MagicMock | None = None,
) -> OrphanedTaskCleanupService:
    return OrphanedTaskCleanupService(
        redis_client=redis or _make_redis(),
        settings=settings or _make_settings(),
    )


# ---------------------------------------------------------------------------
# CleanupMetrics
# ---------------------------------------------------------------------------


class TestCleanupMetrics:
    def test_default_values_are_zero(self) -> None:
        m = CleanupMetrics()
        assert m.orphaned_redis_streams == 0
        assert m.orphaned_agent_tasks == 0
        assert m.stale_cancel_events == 0
        assert m.zombie_sessions == 0
        assert m.abandoned_sandboxes == 0
        assert m.cleanup_duration_ms == 0.0
        assert m.errors_encountered == 0

    def test_to_dict_contains_all_keys(self) -> None:
        m = CleanupMetrics(
            orphaned_redis_streams=3,
            orphaned_agent_tasks=1,
            stale_cancel_events=2,
            zombie_sessions=4,
            abandoned_sandboxes=5,
            cleanup_duration_ms=123.45,
            errors_encountered=6,
        )
        d = m.to_dict()
        assert d["orphaned_redis_streams"] == 3
        assert d["orphaned_agent_tasks"] == 1
        assert d["stale_cancel_events"] == 2
        assert d["zombie_sessions"] == 4
        assert d["abandoned_sandboxes"] == 5
        assert d["cleanup_duration_ms"] == 123.45
        assert d["errors_encountered"] == 6

    def test_to_dict_returns_dict_type(self) -> None:
        assert isinstance(CleanupMetrics().to_dict(), dict)

    def test_to_dict_zero_metrics(self) -> None:
        d = CleanupMetrics().to_dict()
        assert all(v == 0 or v == 0.0 for v in d.values())


# ---------------------------------------------------------------------------
# run_cleanup — rate limiting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRunCleanupRateLimiting:
    async def test_skips_when_called_within_min_interval(self) -> None:
        svc = _make_service()
        # Pretend cleanup ran 10 seconds ago
        svc._last_cleanup = time.monotonic() - 10

        result = await svc.run_cleanup()

        # All counts should be zero — cleanup was skipped
        assert result.orphaned_redis_streams == 0
        assert result.zombie_sessions == 0
        assert result.errors_encountered == 0

    async def test_skips_returns_clean_metrics_instance(self) -> None:
        svc = _make_service()
        svc._last_cleanup = time.monotonic() - 5

        result = await svc.run_cleanup()

        assert isinstance(result, CleanupMetrics)

    async def test_runs_when_last_cleanup_is_zero(self) -> None:
        """First run (last_cleanup == 0.0) must always proceed."""
        redis = _make_redis()
        svc = _make_service(redis=redis)
        # last_cleanup starts at 0.0 — far in the past relative to monotonic()

        with (
            patch.object(svc, "_cleanup_orphaned_redis_streams", new_callable=AsyncMock) as m1,
            patch.object(svc, "_cleanup_stale_cancel_events", new_callable=AsyncMock) as m2,
            patch.object(svc, "_cleanup_zombie_sessions", new_callable=AsyncMock) as m3,
            patch.object(svc, "_cleanup_abandoned_sandboxes", new_callable=AsyncMock) as m4,
        ):
            await svc.run_cleanup()

        m1.assert_awaited_once()
        m2.assert_awaited_once()
        m3.assert_awaited_once()
        m4.assert_awaited_once()

    async def test_runs_after_interval_has_elapsed(self) -> None:
        """Should run when last_cleanup is older than the minimum interval."""
        svc = _make_service()
        svc._last_cleanup = time.monotonic() - (svc._min_cleanup_interval_seconds + 5)

        with (
            patch.object(svc, "_cleanup_orphaned_redis_streams", new_callable=AsyncMock) as m1,
            patch.object(svc, "_cleanup_stale_cancel_events", new_callable=AsyncMock) as m2,
            patch.object(svc, "_cleanup_zombie_sessions", new_callable=AsyncMock) as m3,
            patch.object(svc, "_cleanup_abandoned_sandboxes", new_callable=AsyncMock) as m4,
        ):
            await svc.run_cleanup()

        m1.assert_awaited_once()
        m2.assert_awaited_once()
        m3.assert_awaited_once()
        m4.assert_awaited_once()

    async def test_last_cleanup_updated_after_run(self) -> None:
        svc = _make_service()
        before = time.monotonic()

        with (
            patch.object(svc, "_cleanup_orphaned_redis_streams", new_callable=AsyncMock),
            patch.object(svc, "_cleanup_stale_cancel_events", new_callable=AsyncMock),
            patch.object(svc, "_cleanup_zombie_sessions", new_callable=AsyncMock),
            patch.object(svc, "_cleanup_abandoned_sandboxes", new_callable=AsyncMock),
        ):
            await svc.run_cleanup()

        assert svc._last_cleanup >= before


# ---------------------------------------------------------------------------
# run_cleanup — orchestration and metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRunCleanupOrchestration:
    async def test_all_four_phases_are_called(self) -> None:
        svc = _make_service()

        with (
            patch.object(svc, "_cleanup_orphaned_redis_streams", new_callable=AsyncMock) as m1,
            patch.object(svc, "_cleanup_stale_cancel_events", new_callable=AsyncMock) as m2,
            patch.object(svc, "_cleanup_zombie_sessions", new_callable=AsyncMock) as m3,
            patch.object(svc, "_cleanup_abandoned_sandboxes", new_callable=AsyncMock) as m4,
        ):
            await svc.run_cleanup()

        m1.assert_awaited_once()
        m2.assert_awaited_once()
        m3.assert_awaited_once()
        m4.assert_awaited_once()

    async def test_duration_ms_is_positive(self) -> None:
        svc = _make_service()

        with (
            patch.object(svc, "_cleanup_orphaned_redis_streams", new_callable=AsyncMock),
            patch.object(svc, "_cleanup_stale_cancel_events", new_callable=AsyncMock),
            patch.object(svc, "_cleanup_zombie_sessions", new_callable=AsyncMock),
            patch.object(svc, "_cleanup_abandoned_sandboxes", new_callable=AsyncMock),
        ):
            result = await svc.run_cleanup()

        assert result.cleanup_duration_ms >= 0

    async def test_top_level_exception_increments_errors_and_sets_duration(self) -> None:
        svc = _make_service()

        with patch.object(
            svc,
            "_cleanup_orphaned_redis_streams",
            new_callable=AsyncMock,
            side_effect=RuntimeError("redis exploded"),
        ):
            result = await svc.run_cleanup()

        assert result.errors_encountered == 1
        assert result.cleanup_duration_ms >= 0

    async def test_returns_cleanup_metrics_instance(self) -> None:
        svc = _make_service()

        with (
            patch.object(svc, "_cleanup_orphaned_redis_streams", new_callable=AsyncMock),
            patch.object(svc, "_cleanup_stale_cancel_events", new_callable=AsyncMock),
            patch.object(svc, "_cleanup_zombie_sessions", new_callable=AsyncMock),
            patch.object(svc, "_cleanup_abandoned_sandboxes", new_callable=AsyncMock),
        ):
            result = await svc.run_cleanup()

        assert isinstance(result, CleanupMetrics)


# ---------------------------------------------------------------------------
# _is_stream_orphaned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestIsStreamOrphaned:
    async def test_returns_false_for_non_stream_key_type(self) -> None:
        redis = _make_redis()
        redis.type.return_value = b"string"
        svc = _make_service(redis=redis)

        assert await svc._is_stream_orphaned("task:input:abc") is False

    async def test_returns_false_when_consumer_groups_exist(self) -> None:
        redis = _make_redis()
        redis.type.return_value = b"stream"
        redis.xinfo_stream.return_value = {"length": 5, "last-generated-id": b"0-0"}
        redis.xinfo_groups.return_value = [{"name": "workers"}]
        svc = _make_service(redis=redis)

        assert await svc._is_stream_orphaned("task:output:abc") is False

    async def test_returns_true_for_empty_stream_no_groups(self) -> None:
        redis = _make_redis()
        redis.type.return_value = b"stream"
        redis.xinfo_stream.return_value = {"length": 0, "last-generated-id": None}
        redis.xinfo_groups.return_value = []
        svc = _make_service(redis=redis)

        assert await svc._is_stream_orphaned("task:input:empty") is True

    async def test_returns_true_for_old_stream(self) -> None:
        redis = _make_redis()
        redis.type.return_value = b"stream"

        # Timestamp 1 hour ago
        old_ts_ms = int((time.time() - 3600) * 1000)
        redis.xinfo_stream.return_value = {
            "length": 3,
            "last-generated-id": f"{old_ts_ms}-0".encode(),
        }
        redis.xinfo_groups.return_value = []
        svc = _make_service(redis=redis, settings=_make_settings(orphaned_stream_age_seconds=300))

        assert await svc._is_stream_orphaned("task:input:old") is True

    async def test_returns_false_for_young_stream(self) -> None:
        redis = _make_redis()
        redis.type.return_value = b"stream"

        # Timestamp 10 seconds ago (well within 300s threshold)
        young_ts_ms = int((time.time() - 10) * 1000)
        redis.xinfo_stream.return_value = {
            "length": 2,
            "last-generated-id": f"{young_ts_ms}-0".encode(),
        }
        redis.xinfo_groups.return_value = []
        svc = _make_service(redis=redis, settings=_make_settings(orphaned_stream_age_seconds=300))

        assert await svc._is_stream_orphaned("task:output:young") is False

    async def test_returns_false_when_last_generated_id_missing(self) -> None:
        redis = _make_redis()
        redis.type.return_value = b"stream"
        redis.xinfo_stream.return_value = {"length": 1}  # no last-generated-id key
        redis.xinfo_groups.return_value = []
        svc = _make_service(redis=redis)

        assert await svc._is_stream_orphaned("task:input:noid") is False

    async def test_returns_false_on_redis_exception(self) -> None:
        redis = _make_redis()
        redis.type.side_effect = ConnectionError("Redis down")
        svc = _make_service(redis=redis)

        # Should not raise; conservative — assume not orphaned
        assert await svc._is_stream_orphaned("task:input:err") is False


# ---------------------------------------------------------------------------
# _cleanup_orphaned_redis_streams
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCleanupOrphanedRedisStreams:
    async def test_deletes_orphaned_task_input_stream(self) -> None:
        redis = _make_redis()
        redis.scan.return_value = (0, [b"task:input:abc123"])
        svc = _make_service(redis=redis)

        with patch.object(svc, "_is_stream_orphaned", new_callable=AsyncMock, return_value=True):
            metrics = CleanupMetrics()
            await svc._cleanup_orphaned_redis_streams(metrics)

        redis.delete.assert_awaited_once_with("task:input:abc123")
        assert metrics.orphaned_redis_streams == 1

    async def test_deletes_orphaned_task_output_stream(self) -> None:
        redis = _make_redis()
        redis.scan.return_value = (0, [b"task:output:xyz789"])
        svc = _make_service(redis=redis)

        with patch.object(svc, "_is_stream_orphaned", new_callable=AsyncMock, return_value=True):
            metrics = CleanupMetrics()
            await svc._cleanup_orphaned_redis_streams(metrics)

        redis.delete.assert_awaited_once_with("task:output:xyz789")
        assert metrics.orphaned_redis_streams == 1

    async def test_ignores_non_task_keys(self) -> None:
        redis = _make_redis()
        # session:cancel:* should be ignored by the stream cleanup phase
        redis.scan.return_value = (0, [b"session:cancel:abc", b"task:liveness:abc"])
        svc = _make_service(redis=redis)

        with patch.object(svc, "_is_stream_orphaned", new_callable=AsyncMock, return_value=True) as mock_check:
            metrics = CleanupMetrics()
            await svc._cleanup_orphaned_redis_streams(metrics)

        mock_check.assert_not_awaited()
        redis.delete.assert_not_awaited()
        assert metrics.orphaned_redis_streams == 0

    async def test_does_not_delete_live_stream(self) -> None:
        redis = _make_redis()
        redis.scan.return_value = (0, [b"task:input:live"])
        svc = _make_service(redis=redis)

        with patch.object(svc, "_is_stream_orphaned", new_callable=AsyncMock, return_value=False):
            metrics = CleanupMetrics()
            await svc._cleanup_orphaned_redis_streams(metrics)

        redis.delete.assert_not_awaited()
        assert metrics.orphaned_redis_streams == 0

    async def test_per_stream_error_increments_errors_continues(self) -> None:
        redis = _make_redis()
        redis.scan.return_value = (0, [b"task:input:bad", b"task:output:good"])
        svc = _make_service(redis=redis)

        async def check_side_effect(key: str) -> bool:
            if "bad" in key:
                raise RuntimeError("xinfo failed")
            return True

        with patch.object(svc, "_is_stream_orphaned", side_effect=check_side_effect):
            metrics = CleanupMetrics()
            await svc._cleanup_orphaned_redis_streams(metrics)

        # The good stream was still deleted
        assert metrics.orphaned_redis_streams == 1
        # The bad stream incremented errors
        assert metrics.errors_encountered == 1

    async def test_multi_page_scan_iterates_all_pages(self) -> None:
        redis = _make_redis()
        # First call returns cursor=1 (more pages), second call returns cursor=0
        redis.scan.side_effect = [
            (1, [b"task:input:page1"]),
            (0, [b"task:input:page2"]),
        ]
        svc = _make_service(redis=redis)

        with patch.object(svc, "_is_stream_orphaned", new_callable=AsyncMock, return_value=True):
            metrics = CleanupMetrics()
            await svc._cleanup_orphaned_redis_streams(metrics)

        assert metrics.orphaned_redis_streams == 2
        assert redis.scan.await_count == 2

    async def test_top_level_scan_failure_increments_errors(self) -> None:
        redis = _make_redis()
        redis.scan.side_effect = ConnectionError("Redis unavailable")
        svc = _make_service(redis=redis)

        metrics = CleanupMetrics()
        await svc._cleanup_orphaned_redis_streams(metrics)

        assert metrics.errors_encountered == 1

    async def test_handles_string_keys_as_well_as_bytes(self) -> None:
        """Keys returned as plain str (not bytes) are handled correctly."""
        redis = _make_redis()
        redis.scan.return_value = (0, ["task:input:str-key"])  # str, not bytes
        svc = _make_service(redis=redis)

        with patch.object(svc, "_is_stream_orphaned", new_callable=AsyncMock, return_value=True):
            metrics = CleanupMetrics()
            await svc._cleanup_orphaned_redis_streams(metrics)

        redis.delete.assert_awaited_once_with("task:input:str-key")
        assert metrics.orphaned_redis_streams == 1


# ---------------------------------------------------------------------------
# _cleanup_stale_cancel_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCleanupStaleCancelEvents:
    def _make_mongo_collection(self, docs: list[dict]) -> AsyncMock:
        collection = MagicMock()
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=docs)
        # collection.find() is synchronous in motor — returns cursor
        collection.find = MagicMock(return_value=cursor)
        collection.find_one = AsyncMock(return_value=None)
        collection.update_one = AsyncMock()
        return collection

    async def test_skips_session_without_cancel_signal(self) -> None:
        redis = _make_redis()
        redis.exists.return_value = 0  # no cancel key
        redis.scan.return_value = (0, [])

        session_doc = {"_id": "session-abc", "status": "running"}
        collection = self._make_mongo_collection([session_doc])

        svc = _make_service(redis=redis)

        with patch("app.infrastructure.repositories.mongo_session_repository.MongoSessionRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.collection = collection
            metrics = CleanupMetrics()
            await svc._cleanup_stale_cancel_events(metrics)

        collection.update_one.assert_not_awaited()
        assert metrics.stale_cancel_events == 0

    async def test_marks_session_as_failed_when_cancel_signal_exists(self) -> None:
        redis = _make_redis()
        redis.exists.return_value = 1  # cancel key present
        redis.scan.return_value = (0, [])

        session_doc = {"_id": "session-abc", "status": "running"}
        collection = self._make_mongo_collection([session_doc])

        svc = _make_service(redis=redis)

        with patch("app.infrastructure.repositories.mongo_session_repository.MongoSessionRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.collection = collection
            metrics = CleanupMetrics()
            await svc._cleanup_stale_cancel_events(metrics)

        collection.update_one.assert_awaited_once()
        redis.delete.assert_awaited()
        assert metrics.stale_cancel_events == 1


# ---------------------------------------------------------------------------
# _cleanup_zombie_sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCleanupZombieSessions:
    def _make_mongo_collection_with_events(
        self,
        session_docs: list[dict],
        recent_event: dict | None = None,
    ) -> tuple[MagicMock, AsyncMock]:
        collection = MagicMock()
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=session_docs)
        # collection.find() is synchronous in motor — returns cursor
        collection.find = MagicMock(return_value=cursor)
        collection.update_one = AsyncMock()

        events_collection = AsyncMock()
        events_collection.find_one = AsyncMock(return_value=recent_event)

        # repo.db["session_events"] is accessed inside the method
        return collection, events_collection

    async def test_skips_session_with_recent_event(self) -> None:
        redis = _make_redis()
        session_doc = {"_id": "s1", "status": "running"}
        collection, events_coll = self._make_mongo_collection_with_events(
            [session_doc], recent_event={"session_id": "s1", "type": "progress"}
        )

        svc = _make_service(redis=redis)

        with patch("app.infrastructure.repositories.mongo_session_repository.MongoSessionRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.collection = collection
            instance.db = {"session_events": events_coll}
            metrics = CleanupMetrics()
            await svc._cleanup_zombie_sessions(metrics)

        collection.update_one.assert_not_awaited()
        assert metrics.zombie_sessions == 0

    async def test_marks_zombie_session_as_failed(self) -> None:
        redis = _make_redis()
        session_doc = {"_id": "s2", "status": "running"}
        collection, events_coll = self._make_mongo_collection_with_events(
            [session_doc],
            recent_event=None,  # no recent events
        )

        svc = _make_service(redis=redis)

        with patch("app.infrastructure.repositories.mongo_session_repository.MongoSessionRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.collection = collection
            instance.db = {"session_events": events_coll}
            metrics = CleanupMetrics()
            await svc._cleanup_zombie_sessions(metrics)

        collection.update_one.assert_awaited_once()
        assert metrics.zombie_sessions == 1

    async def test_zombie_cleanup_exception_increments_errors(self) -> None:
        redis = _make_redis()
        session_doc = {"_id": "s3", "status": "running"}
        collection, events_coll = self._make_mongo_collection_with_events([session_doc], recent_event=None)
        collection.update_one.side_effect = RuntimeError("mongo unavailable")

        svc = _make_service(redis=redis)

        with patch("app.infrastructure.repositories.mongo_session_repository.MongoSessionRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.collection = collection
            instance.db = {"session_events": events_coll}
            metrics = CleanupMetrics()
            await svc._cleanup_zombie_sessions(metrics)

        assert metrics.errors_encountered == 1
        assert metrics.zombie_sessions == 0


# ---------------------------------------------------------------------------
# _is_sandbox_orphaned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestIsSandboxOrphaned:
    async def test_returns_false_when_active_session_matches_full_name(self) -> None:
        svc = _make_service()

        with patch("app.infrastructure.repositories.mongo_session_repository.MongoSessionRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.collection = AsyncMock()
            # Full-name match
            instance.collection.find_one = AsyncMock(return_value={"_id": "s1", "sandbox_id": "my-container"})

            result = await svc._is_sandbox_orphaned("my-container")

        assert result is False

    async def test_returns_false_via_suffix_match_for_pythinker_prefix(self) -> None:
        svc = _make_service()
        container_name = "pythinker-sandbox-abc123"

        with patch("app.infrastructure.repositories.mongo_session_repository.MongoSessionRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.collection = AsyncMock()
            # First call (full name) → no match; second call (suffix) → match
            instance.collection.find_one = AsyncMock(side_effect=[None, {"_id": "s2", "sandbox_id": "abc123"}])

            result = await svc._is_sandbox_orphaned(container_name)

        assert result is False

    async def test_returns_true_when_no_active_session_found(self) -> None:
        svc = _make_service()
        container_name = "pythinker-sandbox-orphan"

        with patch("app.infrastructure.repositories.mongo_session_repository.MongoSessionRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.collection = AsyncMock()
            instance.collection.find_one = AsyncMock(return_value=None)

            result = await svc._is_sandbox_orphaned(container_name)

        assert result is True

    async def test_returns_false_on_db_exception_conservative(self) -> None:
        svc = _make_service()

        with patch("app.infrastructure.repositories.mongo_session_repository.MongoSessionRepository") as mock_repo:
            instance = mock_repo.return_value
            instance.collection = AsyncMock()
            instance.collection.find_one = AsyncMock(side_effect=ConnectionError("Mongo down"))

            result = await svc._is_sandbox_orphaned("pythinker-sandbox-err")

        # Conservative: assume NOT orphaned to avoid destroying active sandbox
        assert result is False


# ---------------------------------------------------------------------------
# scheduled_cleanup_job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestScheduledCleanupJob:
    async def test_creates_service_and_calls_run_cleanup(self) -> None:
        redis = _make_redis()

        with patch("app.application.services.orphaned_task_cleanup_service.OrphanedTaskCleanupService") as mock_service:
            instance = mock_service.return_value
            instance.run_cleanup = AsyncMock(return_value=CleanupMetrics())

            await scheduled_cleanup_job(redis)

        mock_service.assert_called_once_with(redis)
        instance.run_cleanup.assert_awaited_once()

    async def test_prometheus_failure_does_not_raise(self) -> None:
        """Prometheus recording failure must be swallowed gracefully."""
        redis = _make_redis()

        with patch("app.application.services.orphaned_task_cleanup_service.OrphanedTaskCleanupService") as mock_service:
            instance = mock_service.return_value
            instance.run_cleanup = AsyncMock(return_value=CleanupMetrics(orphaned_redis_streams=2))

            with patch(
                "app.application.services.orphaned_task_cleanup_service.PrometheusMetrics",
                side_effect=ImportError("no prometheus"),
                create=True,
            ):
                # Should not raise even if Prometheus is unavailable
                await scheduled_cleanup_job(redis)
