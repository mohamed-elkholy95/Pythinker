"""MongoDB slow query profiler — polls system.profile for slow operations.

When enabled via ``mongodb_profiler_enabled=True``, a background task:
1. Enables MongoDB profiling level 1 (slow queries only) with the configured threshold.
2. Periodically polls ``db.system.profile`` for new slow queries.
3. Emits them as Prometheus counters for observability.

Usage:
    Wired into lifespan via ``start_mongo_profiler()`` / ``stop_mongo_profiler()``.
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.prometheus_metrics import mongodb_collscan_total, mongodb_slow_queries_total

logger = logging.getLogger(__name__)

_profiler_task: asyncio.Task | None = None


async def _enable_profiling(db: AsyncIOMotorDatabase, threshold_ms: int) -> None:
    """Enable MongoDB profiling level 1 (log slow queries only)."""
    try:
        await db.command("profile", 1, slowms=threshold_ms)
        logger.info("MongoDB profiling enabled (level 1, slowms=%d)", threshold_ms)
    except Exception as e:
        logger.warning("Failed to enable MongoDB profiling: %s", e)


async def _poll_slow_queries(
    db: AsyncIOMotorDatabase,
    poll_interval: float = 60.0,
) -> None:
    """Periodically poll system.profile for slow queries and emit metrics."""
    last_check = datetime.now(UTC)
    # Wait for system to stabilize
    await asyncio.sleep(30)

    while True:
        try:
            now = datetime.now(UTC)
            cursor = (
                db.system.profile.find(
                    {"ts": {"$gt": last_check}},
                    {"ns": 1, "op": 1, "millis": 1, "ts": 1},
                )
                .sort("ts", 1)
                .limit(100)
            )

            count = 0
            collscan_count = 0
            async for doc in cursor:
                ns = doc.get("ns", "unknown")
                # Extract collection name from namespace (db.collection)
                collection = ns.split(".")[-1] if "." in ns else ns
                op = doc.get("op", "unknown")
                mongodb_slow_queries_total.inc({"collection": collection, "operation": op})
                count += 1

                # Detect COLLSCAN (full table scan) — indicates missing index
                plan_summary = doc.get("planSummary", "")
                if "COLLSCAN" in plan_summary:
                    mongodb_collscan_total.inc({"collection": collection, "operation": op})
                    collscan_count += 1
                    logger.warning(
                        "COLLSCAN detected: collection=%s op=%s millis=%s",
                        collection,
                        op,
                        doc.get("millis", "?"),
                    )

            if count > 0:
                logger.info(
                    "Profiler detected %d slow queries (%d COLLSCAN)",
                    count,
                    collscan_count,
                )

            last_check = now
        except Exception as e:
            logger.debug("Slow query profiler poll failed: %s", e)

        await asyncio.sleep(poll_interval)


async def start_mongo_profiler(
    db: AsyncIOMotorDatabase,
    threshold_ms: int = 100,
) -> asyncio.Task:
    """Start the MongoDB slow query profiler background task."""
    global _profiler_task

    await _enable_profiling(db, threshold_ms)
    _profiler_task = asyncio.create_task(_poll_slow_queries(db))
    logger.info("MongoDB slow query profiler started (threshold: %dms)", threshold_ms)
    return _profiler_task


async def stop_mongo_profiler() -> None:
    """Stop the profiler background task."""
    global _profiler_task
    if _profiler_task is not None:
        _profiler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _profiler_task
        _profiler_task = None
        logger.info("MongoDB slow query profiler stopped")
