"""
APScheduler integration for orphaned task cleanup.

This module sets up automated cleanup jobs using APScheduler.
Integrates with FastAPI lifespan for automatic startup/shutdown.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from redis.asyncio import Redis
from structlog import get_logger

from app.application.services.orphaned_task_cleanup_service import (
    OrphanedTaskCleanupService,
)
from app.core.config import get_settings

logger = get_logger(__name__)


class CleanupScheduler:
    """
    Manages scheduled cleanup jobs.

    Runs orphaned task cleanup at configurable intervals.
    """

    def __init__(self, redis_client: Redis):
        """
        Initialize cleanup scheduler.

        Args:
            redis_client: Redis async client
        """
        self.redis = redis_client
        self.settings = get_settings()
        self.scheduler = AsyncIOScheduler()

        # Get cleanup interval from settings (default: 5 minutes)
        self.cleanup_interval_minutes = getattr(
            self.settings, "cleanup_interval_minutes", 5
        )

        # Create cleanup service
        self.cleanup_service = OrphanedTaskCleanupService(redis_client, self.settings)

    def start(self) -> None:
        """Start the scheduler."""
        # Add cleanup job
        self.scheduler.add_job(
            self._run_cleanup,
            trigger=IntervalTrigger(minutes=self.cleanup_interval_minutes),
            id="orphaned_task_cleanup",
            name="Orphaned Task Cleanup",
            replace_existing=True,
            max_instances=1,  # Prevent concurrent execution
        )

        self.scheduler.start()
        logger.info(
            "Cleanup scheduler started",
            interval_minutes=self.cleanup_interval_minutes,
        )

    def shutdown(self) -> None:
        """Shutdown the scheduler gracefully."""
        logger.info("Shutting down cleanup scheduler")
        self.scheduler.shutdown(wait=True)

    async def _run_cleanup(self) -> None:
        """Internal method to run cleanup and handle errors."""
        try:
            metrics = await self.cleanup_service.run_cleanup()

            # Record metrics in Prometheus
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

        except Exception as e:
            logger.error("Scheduled cleanup job failed", error=str(e), exc_info=True)


# ====================
# FastAPI Lifespan Integration
# ====================


@asynccontextmanager
async def cleanup_scheduler_lifespan(redis_client: Redis) -> AsyncGenerator[CleanupScheduler, None]:
    """
    FastAPI lifespan context manager for cleanup scheduler.

    Usage in main.py:
        from app.application.services.cleanup_scheduler import cleanup_scheduler_lifespan

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # ... other startup ...
            async with cleanup_scheduler_lifespan(redis_client) as scheduler:
                yield {"cleanup_scheduler": scheduler}
            # ... shutdown ...

    Args:
        redis_client: Redis async client

    Yields:
        CleanupScheduler instance
    """
    scheduler = CleanupScheduler(redis_client)

    # Start scheduler
    scheduler.start()

    try:
        yield scheduler
    finally:
        # Shutdown scheduler on app shutdown
        scheduler.shutdown()
