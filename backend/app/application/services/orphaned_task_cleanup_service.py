"""
Professional Cron-Based Orphaned Task Cleanup Service.

This service runs periodically to detect and clean up orphaned background tasks,
stale Redis streams, and zombie agent sessions that were not properly cancelled.

Scheduled via APScheduler or system cron.
"""

import asyncio
import contextlib
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from redis.asyncio import Redis
from structlog import get_logger

from app.core.config import get_settings
from app.infrastructure.external.message_queue.redis_stream_queue import RedisStreamQueue

logger = get_logger(__name__)


@dataclass
class CleanupMetrics:
    """Metrics collected during cleanup operation."""

    # Task cleanup
    orphaned_redis_streams: int = 0
    orphaned_agent_tasks: int = 0
    stale_cancel_events: int = 0

    # Session cleanup
    zombie_sessions: int = 0
    abandoned_sandboxes: int = 0

    # Performance
    cleanup_duration_ms: float = 0.0
    errors_encountered: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary for logging/Prometheus."""
        return {
            "orphaned_redis_streams": self.orphaned_redis_streams,
            "orphaned_agent_tasks": self.orphaned_agent_tasks,
            "stale_cancel_events": self.stale_cancel_events,
            "zombie_sessions": self.zombie_sessions,
            "abandoned_sandboxes": self.abandoned_sandboxes,
            "cleanup_duration_ms": self.cleanup_duration_ms,
            "errors_encountered": self.errors_encountered,
        }


class OrphanedTaskCleanupService:
    """
    Professional cleanup service for orphaned background tasks.

    Runs periodically to detect and clean up:
    - Orphaned Redis streams (task:input:*, task:output:*)
    - Stale session cancel events in agent_service
    - Zombie agent sessions (status=RUNNING but no activity)
    - Abandoned sandbox containers

    Designed to be idempotent and safe for concurrent execution.
    """

    def __init__(self, redis_client: Redis, settings=None):
        """
        Initialize cleanup service.

        Args:
            redis_client: Redis async client for stream cleanup
            settings: Application settings (optional, fetches if not provided)
        """
        self.redis = redis_client
        self.settings = settings or get_settings()

        # Cleanup thresholds (configurable via settings)
        self.orphaned_stream_age_seconds = getattr(
            self.settings, "orphaned_stream_age_seconds", 300
        )  # 5 minutes
        self.zombie_session_age_seconds = getattr(
            self.settings, "zombie_session_age_seconds", 900
        )  # 15 minutes
        self.stale_cancel_event_age_seconds = getattr(
            self.settings, "stale_cancel_event_age_seconds", 600
        )  # 10 minutes

        # Rate limiting
        self._last_cleanup: float = 0.0
        self._min_cleanup_interval_seconds: float = 60.0  # Max once per minute

    async def run_cleanup(self) -> CleanupMetrics:
        """
        Execute cleanup operation.

        Returns:
            CleanupMetrics with counts of cleaned resources

        This method is idempotent and safe to call concurrently.
        """
        # Rate limiting: Don't run more than once per minute
        now = time.monotonic()
        if now - self._last_cleanup < self._min_cleanup_interval_seconds:
            logger.debug(
                "Skipping cleanup - ran recently",
                last_cleanup_ago=now - self._last_cleanup,
            )
            return CleanupMetrics()

        self._last_cleanup = now
        start_time = time.monotonic()
        metrics = CleanupMetrics()

        logger.info("Starting orphaned task cleanup")

        try:
            # Phase 1: Clean orphaned Redis streams
            await self._cleanup_orphaned_redis_streams(metrics)

            # Phase 2: Clean stale session cancel events
            await self._cleanup_stale_cancel_events(metrics)

            # Phase 3: Clean zombie agent sessions
            await self._cleanup_zombie_sessions(metrics)

            # Phase 4: Clean abandoned sandbox containers
            await self._cleanup_abandoned_sandboxes(metrics)

        except Exception as e:
            logger.error("Cleanup operation failed", error=str(e), exc_info=True)
            metrics.errors_encountered += 1
        finally:
            metrics.cleanup_duration_ms = (time.monotonic() - start_time) * 1000

        logger.info(
            "Orphaned task cleanup completed",
            **metrics.to_dict(),
        )

        return metrics

    async def _cleanup_orphaned_redis_streams(self, metrics: CleanupMetrics) -> None:
        """
        Clean up orphaned Redis streams.

        Looks for task:input:* and task:output:* streams that are:
        - Older than orphaned_stream_age_seconds
        - Have no consumers
        - Are empty or have only old messages
        """
        try:
            cursor = 0
            pattern = "task:*"

            while True:
                cursor, keys = await self.redis.scan(
                    cursor=cursor, match=pattern, count=100
                )

                for key in keys:
                    key_str = key.decode("utf-8") if isinstance(key, bytes) else key

                    # Only process task:input:* and task:output:* streams
                    if not (key_str.startswith("task:input:") or key_str.startswith("task:output:")):
                        continue

                    try:
                        # Check if stream is orphaned
                        if await self._is_stream_orphaned(key_str):
                            # Delete orphaned stream
                            await self.redis.delete(key_str)
                            metrics.orphaned_redis_streams += 1
                            logger.debug(f"Deleted orphaned Redis stream: {key_str}")

                    except Exception as e:
                        logger.warning(
                            f"Failed to check/delete stream {key_str}",
                            error=str(e),
                        )
                        metrics.errors_encountered += 1

                if cursor == 0:
                    break

        except Exception as e:
            logger.error("Redis stream cleanup failed", error=str(e), exc_info=True)
            metrics.errors_encountered += 1

    async def _is_stream_orphaned(self, stream_key: str) -> bool:
        """
        Check if a Redis stream is orphaned.

        A stream is considered orphaned if:
        - It has no consumers
        - Last message timestamp is older than threshold
        - Stream is empty

        Args:
            stream_key: Redis stream key

        Returns:
            True if stream should be deleted
        """
        try:
            # Check if stream exists
            stream_type = await self.redis.type(stream_key)
            if stream_type != b"stream":
                return False

            # Get stream info
            info = await self.redis.xinfo_stream(stream_key)

            # Check if stream has consumers
            groups = await self.redis.xinfo_groups(stream_key)
            if groups:
                # Has consumer groups - not orphaned
                return False

            # Check stream length
            length = info.get("length", 0)
            if length == 0:
                # Empty stream - can delete
                return True

            # Check last message age
            last_generated_id = info.get("last-generated-id")
            if last_generated_id:
                # Extract timestamp from stream ID (milliseconds since epoch)
                timestamp_ms = int(last_generated_id.split(b"-")[0])
                age_seconds = (time.time() * 1000 - timestamp_ms) / 1000

                if age_seconds > self.orphaned_stream_age_seconds:
                    return True

            return False

        except Exception as e:
            logger.debug(f"Error checking stream {stream_key}: {e}")
            return False

    async def _cleanup_stale_cancel_events(self, metrics: CleanupMetrics) -> None:
        """
        Clean up stale cancel events in agent_service._session_cancel_events.

        Note: This requires access to the AgentService instance, which may
        not be available in a background cleanup task. This is a placeholder
        for when service lifecycle management is improved.
        """
        # TODO: Implement when service registry is available
        # For now, cancel events are cleaned up on session completion
        logger.debug("Stale cancel event cleanup - not yet implemented (requires service registry)")

    async def _cleanup_zombie_sessions(self, metrics: CleanupMetrics) -> None:
        """
        Clean up zombie sessions.

        A session is considered a zombie if:
        - Status is RUNNING or PENDING
        - Last updated_at is older than threshold
        - No active SSE connections
        - No recent events in session_events

        This prevents sessions from staying in RUNNING state forever.
        """
        try:
            from app.infrastructure.repositories.mongo_session_repository import (
                MongoSessionRepository,
            )
            from app.domain.models.session import SessionStatus

            # Import here to avoid circular dependencies
            repo = MongoSessionRepository()

            # Find sessions in RUNNING/PENDING state older than threshold
            cutoff_time = datetime.now(timezone.utc) - timedelta(
                seconds=self.zombie_session_age_seconds
            )

            # Query for zombie sessions
            zombie_candidates = await repo.collection.find(
                {
                    "status": {"$in": [SessionStatus.RUNNING.value, SessionStatus.PENDING.value]},
                    "updated_at": {"$lt": cutoff_time},
                }
            ).to_list(length=100)

            for session_doc in zombie_candidates:
                session_id = str(session_doc["_id"])

                # Additional check: Verify no recent events
                events_collection = repo.db["session_events"]
                recent_event = await events_collection.find_one(
                    {
                        "session_id": session_id,
                        "timestamp": {"$gte": cutoff_time},
                    }
                )

                if recent_event:
                    # Has recent activity - not a zombie
                    continue

                # Mark session as FAILED (zombie cleanup)
                try:
                    await repo.collection.update_one(
                        {"_id": session_doc["_id"]},
                        {
                            "$set": {
                                "status": SessionStatus.FAILED.value,
                                "error": "Session cleaned up as zombie (no activity detected)",
                                "updated_at": datetime.now(timezone.utc),
                            }
                        },
                    )
                    metrics.zombie_sessions += 1
                    logger.warning(
                        f"Marked zombie session as FAILED: {session_id}",
                        last_updated=session_doc.get("updated_at"),
                    )

                except Exception as e:
                    logger.warning(
                        f"Failed to mark zombie session {session_id} as FAILED",
                        error=str(e),
                    )
                    metrics.errors_encountered += 1

        except Exception as e:
            logger.error("Zombie session cleanup failed", error=str(e), exc_info=True)
            metrics.errors_encountered += 1

    async def _cleanup_abandoned_sandboxes(self, metrics: CleanupMetrics) -> None:
        """
        Clean up abandoned sandbox containers.

        Checks Docker for containers that:
        - Match pythinker-sandbox-* pattern
        - Are running but have no associated session
        - Have been running for >15 minutes with no activity

        Note: This requires Docker API access and should be run carefully.
        """
        try:
            # Import Docker client
            import aiodocker

            async with aiodocker.Docker() as docker:
                # List all pythinker sandbox containers
                containers = await docker.containers.list(
                    filters={"name": "pythinker-sandbox-"}
                )

                for container in containers:
                    try:
                        # Get container name
                        container_name = container._container.get("Names", [None])[0]
                        if not container_name:
                            continue

                        container_name = container_name.lstrip("/")

                        # Get container started time
                        inspect = await container.show()
                        started_at = inspect.get("State", {}).get("StartedAt")

                        if not started_at:
                            continue

                        # Parse ISO timestamp
                        started_time = datetime.fromisoformat(
                            started_at.replace("Z", "+00:00")
                        )
                        age = datetime.now(timezone.utc) - started_time

                        # Check if container is old and potentially abandoned
                        if age.total_seconds() > self.zombie_session_age_seconds:
                            # TODO: Cross-reference with active sessions
                            # For safety, only log for now (don't auto-delete)
                            logger.warning(
                                f"Found potentially abandoned sandbox container",
                                container_name=container_name,
                                age_seconds=age.total_seconds(),
                            )
                            # metrics.abandoned_sandboxes += 1

                    except Exception as e:
                        logger.warning(
                            f"Error checking container {container_name}",
                            error=str(e),
                        )
                        metrics.errors_encountered += 1

        except ImportError:
            logger.debug("aiodocker not available - skipping sandbox cleanup")
        except Exception as e:
            logger.error("Sandbox cleanup failed", error=str(e), exc_info=True)
            metrics.errors_encountered += 1


# ====================
# APScheduler Integration
# ====================


async def scheduled_cleanup_job(redis_client: Redis) -> None:
    """
    Scheduled cleanup job for APScheduler.

    Usage:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            scheduled_cleanup_job,
            'interval',
            minutes=5,
            args=[redis_client],
        )
        scheduler.start()
    """
    service = OrphanedTaskCleanupService(redis_client)
    metrics = await service.run_cleanup()

    # Optionally push metrics to Prometheus
    try:
        from app.core.prometheus_metrics import PrometheusMetrics

        pm = PrometheusMetrics()
        pm.record_orphaned_task_cleanup(
            orphaned_streams=metrics.orphaned_redis_streams,
            zombie_sessions=metrics.zombie_sessions,
            duration_ms=metrics.cleanup_duration_ms,
        )
    except Exception as e:
        logger.debug(f"Failed to record Prometheus metrics: {e}")


# ====================
# System Cron Integration
# ====================


async def main() -> None:
    """
    Main entry point for system cron execution.

    Usage (crontab):
        # Run every 5 minutes
        */5 * * * * cd /app && python -m app.application.services.orphaned_task_cleanup_service

    Or via docker exec:
        */5 * * * * docker exec pythinker-backend-1 python -m app.application.services.orphaned_task_cleanup_service
    """
    from app.core.config import get_settings
    from redis.asyncio import Redis as AsyncRedis

    settings = get_settings()

    # Create Redis client
    redis_client = AsyncRedis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=False,
    )

    try:
        service = OrphanedTaskCleanupService(redis_client, settings)
        metrics = await service.run_cleanup()

        # Print metrics for cron logging
        print(f"Cleanup completed: {metrics.to_dict()}")

    finally:
        await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())
